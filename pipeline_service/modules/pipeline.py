from __future__ import annotations

import base64
import io
import time
from datetime import datetime
from typing import Optional

from PIL import Image
import pyspz
import torch
import gc
import numpy as np

from config import Settings, settings
from logger_config import logger
from schemas import (
    GenerateRequest,
    GenerateResponse,
    TrellisParams,
    TrellisRequest,
    TrellisResult,
)
from modules.image_edit.qwen_edit_module import QwenEditModule
from modules.background_removal.rmbg_manager import BackgroundRemovalService
from modules.gs_generator.trellis_manager import TrellisService
from modules.utils import (
    secure_randint,
    set_random_seed,
    decode_image,
    to_png_base64,
    save_files,
)


class GenerationPipeline:
    def __init__(self, settings: Settings = settings):
        self.settings = settings

        # Initialize modules
        self.qwen_edit = QwenEditModule(settings)
        self.rmbg = BackgroundRemovalService(settings)
        self.trellis = TrellisService(settings)

    async def startup(self) -> None:
        """Initialize all pipeline components."""
        logger.info("Starting pipeline")
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)

        await self.qwen_edit.startup()
        await self.rmbg.startup()
        await self.trellis.startup()

        logger.info("Warming up generator...")
        await self.warmup_generator()
        self._clean_gpu_memory()

        logger.success("Warmup is complete. Pipeline ready to work.")

    async def shutdown(self) -> None:
        """Shutdown all pipeline components."""
        logger.info("Closing pipeline")

        # Shutdown all modules
        await self.qwen_edit.shutdown()
        await self.rmbg.shutdown()
        await self.trellis.shutdown()

        logger.info("Pipeline closed.")

    def _clean_gpu_memory(self) -> None:
        """
        Clean the GPU memory.
        """
        gc.collect()
        torch.cuda.empty_cache()
    
    def _enhance_image_quality(self, image: Image.Image) -> Image.Image:
        """
        Enhance image quality while preserving original features.
        
        Args:
            image: Input PIL Image
            
        Returns:
            Enhanced PIL Image
        """
        from PIL import ImageEnhance, ImageFilter
        
        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # 1. Mild denoising to reduce artifacts without losing detail
        image = image.filter(ImageFilter.MedianFilter(size=3))
        
        # 2. Enhance sharpness slightly to preserve fine details
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.15)  # Mild sharpening
        
        # 3. Enhance contrast slightly for better feature definition
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.1)  # Mild contrast boost
        
        # 4. Enhance color saturation slightly (preserves original colors)
        enhancer = ImageEnhance.Color(image)
        image = enhancer.enhance(1.05)  # Very mild saturation boost
        
        logger.info(f"Enhanced image quality: {image.size}")
        return image
    
    def _calibrate_colors(self, original: Image.Image, edited: Image.Image) -> Image.Image:
        """
        Calibrate edited image colors to match original image.
        This ensures exact color preservation across all generated views.
        
        Args:
            original: Original input image (reference)
            edited: Edited image that may have color drift
            
        Returns:
            Color-calibrated image matching original
        """
        from PIL import ImageStat
        
        try:
            # Get color statistics from both images
            orig_stat = ImageStat.Stat(original)
            edit_stat = ImageStat.Stat(edited)
            
            # Calculate correction factors for each RGB channel
            corrections = []
            for i in range(3):  # RGB channels
                if edit_stat.mean[i] > 0:
                    correction = orig_stat.mean[i] / edit_stat.mean[i]
                    # Limit correction to reasonable range to avoid artifacts
                    correction = max(0.8, min(1.2, correction))
                else:
                    correction = 1.0
                corrections.append(correction)
            
            # Apply color corrections
            edited_array = np.array(edited).astype(float)
            for i in range(3):  # RGB
                edited_array[:,:,i] *= corrections[i]
            
            # Clip values to valid range
            edited_array = np.clip(edited_array, 0, 255).astype(np.uint8)
            calibrated = Image.fromarray(edited_array)
            
            logger.info(f"Color calibration applied - Corrections: R={corrections[0]:.3f}, G={corrections[1]:.3f}, B={corrections[2]:.3f}")
            return calibrated
            
        except Exception as e:
            logger.warning(f"Color calibration failed: {e}, using original edited image")
            return edited
    
    def _normalize_lighting(self, images: list[Image.Image]) -> list[Image.Image]:
        """
        Normalize lighting across all views for consistency.
        This helps Trellis understand 3D structure better.
        
        Args:
            images: List of images from different views
            
        Returns:
            List of lighting-normalized images
        """
        from PIL import ImageStat, ImageEnhance
        
        try:
            # Calculate brightness for each image (average of RGB channels)
            brightness_values = []
            for img in images:
                stat = ImageStat.Stat(img)
                avg_brightness = sum(stat.mean[:3]) / 3  # RGB average
                brightness_values.append(avg_brightness)
            
            # Calculate target brightness (median to avoid outliers)
            target_brightness = sorted(brightness_values)[len(brightness_values) // 2]
            
            # Normalize each image
            normalized = []
            for img, current_brightness in zip(images, brightness_values):
                if current_brightness > 0:
                    factor = target_brightness / current_brightness
                    # Limit adjustment to avoid overexposure/underexposure
                    factor = max(0.8, min(1.2, factor))
                    
                    enhancer = ImageEnhance.Brightness(img)
                    normalized_img = enhancer.enhance(factor)
                    normalized.append(normalized_img)
                else:
                    normalized.append(img)
            
            logger.info(f"Lighting normalization applied - Target brightness: {target_brightness:.1f}")
            return normalized
            
        except Exception as e:
            logger.warning(f"Lighting normalization failed: {e}, using original images")
            return images
    
    def _validate_view_consistency(self, views: list[Image.Image], original: Image.Image) -> bool:
        """
        Validate that generated views are consistent with each other and the original.
        Checks color consistency to ensure all views show the same object.
        
        Args:
            views: List of generated view images
            original: Original input image for reference
            
        Returns:
            True if views are consistent, False otherwise
        """
        from PIL import ImageStat
        
        try:
            # Get color statistics for all views
            color_stats = [ImageStat.Stat(view) for view in views]
            orig_stat = ImageStat.Stat(original)
            
            # Check color consistency across views
            for channel in range(3):  # RGB channels
                channel_values = [stat.mean[channel] for stat in color_stats]
                original_value = orig_stat.mean[channel]
                
                # Calculate variance from original
                max_diff = max(abs(val - original_value) for val in channel_values)
                
                # Threshold: views shouldn't differ from original by more than 50 units
                if max_diff > 50:
                    logger.warning(f"High color variance in channel {channel}: {max_diff:.1f} units from original")
                    return False
            
            # Check contrast consistency
            contrasts = [stat.stddev[0] if stat.stddev else 0 for stat in color_stats]
            contrast_variance = max(contrasts) - min(contrasts)
            
            if contrast_variance > 40:
                logger.warning(f"High contrast variance: {contrast_variance:.1f}")
                return False
            
            logger.info("✓ View consistency validation passed")
            return True
            
        except Exception as e:
            logger.warning(f"View consistency validation failed: {e}, proceeding anyway")
            return True  # Don't block generation on validation failure

    async def warmup_generator(self) -> None:
        """Function for warming up the generator"""

        temp_image = Image.new("RGB", (64, 64), color=(128, 128, 128))
        buffer = io.BytesIO()
        temp_image.save(buffer, format="PNG")
        temp_imge_bytes = buffer.getvalue()
        await self.generate_from_upload(temp_imge_bytes, seed=42)

    async def generate_from_upload(self, image_bytes: bytes, seed: int) -> bytes:
        """
        Generate 3D model from uploaded image file and return PLY as bytes.

        Args:
            image_bytes: Raw image bytes from uploaded file

        Returns:
            PLY file as bytes
        """
        # Encode to base64
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # Create request
        request = GenerateRequest(
            prompt_image=image_base64, prompt_type="image", seed=seed
        )

        # Generate
        response = await self.generate_gs(request)

        # Return binary PLY
        if not response.ply_file_base64:
            raise ValueError("PLY generation failed")

        return response.ply_file_base64  # bytes

    async def generate_gs(self, request: GenerateRequest) -> GenerateResponse:
        """
        Execute full generation pipeline.

        Args:
            request: Generation request with prompt and settings

        Returns:
            GenerateResponse with generated assets
        """
        t1 = time.time()
        logger.info(f"New generation request")

        # Set seed
        if request.seed < 0:
            request.seed = secure_randint(0, 10000)
            set_random_seed(request.seed)
        else:
            set_random_seed(request.seed)

        # Decode input image
        image = decode_image(request.prompt_image)
        
        # Enhance the original image quality
        image_enhanced = self._enhance_image_quality(image)
        
        # Strategy: Use original image as primary view + generate complementary views
        # This preserves the exact colors, shape, and details from the input
        
        if self.settings.use_original_as_primary:
            # Use the original (enhanced) image directly as the primary view
            logger.info("Using original image as primary view to preserve accuracy")
            image_primary = self.qwen_edit.edit_image(
                prompt_image=image_enhanced,
                seed=request.seed,
                prompt="Preserve exact colors, shapes, and all details. Only improve image quality and remove background with neutral solid color. Keep the same viewing angle",
            )
            image_without_background_primary = self.rmbg.remove_background(image_primary)
        else:
            # Legacy: edit the image
            image_without_background_primary = self.rmbg.remove_background(image_enhanced)

        # Generate complementary views with 3D rotation (around vertical Y-axis)
        # Left three-quarters view - 45° rotation around vertical axis (Y-axis)
        image_edited_left = self.qwen_edit.edit_image(
            prompt_image=image,
            seed=request.seed,
            prompt="Rotate object 45 degrees counterclockwise around vertical axis (Y-axis) to show left three-quarter view. Preserve exact colors, textures, proportions, and all details. Clean neutral background. Maintain 3D depth and volume",
        )
        # Apply color calibration to match original
        image_edited_left = self._calibrate_colors(image, image_edited_left)
        image_without_background_left = self.rmbg.remove_background(image_edited_left)

        # Right three-quarters view - 45° rotation around vertical axis (Y-axis)
        image_edited_right = self.qwen_edit.edit_image(
            prompt_image=image,
            seed=request.seed,
            prompt="Rotate object 45 degrees clockwise around vertical axis (Y-axis) to show right three-quarter view. Preserve exact colors, textures, proportions, and all details. Clean neutral background. Maintain 3D depth and volume",
        )
        # Apply color calibration to match original
        image_edited_right = self._calibrate_colors(image, image_edited_right)
        image_without_background_right = self.rmbg.remove_background(image_edited_right)

        # Back view - 180° rotation around vertical axis (Y-axis)
        image_edited_back = self.qwen_edit.edit_image(
            prompt_image=image,
            seed=request.seed,
            prompt="Rotate object 180 degrees around vertical axis (Y-axis) to show back view. Preserve exact colors, textures, proportions, and all details. Clean neutral background. Maintain 3D depth and volume",
        )
        # Apply color calibration to match original
        image_edited_back = self._calibrate_colors(image, image_edited_back)
        image_without_background_back = self.rmbg.remove_background(image_edited_back)

        trellis_result: Optional[TrellisResult] = None

        # Resolve Trellis parameters from request
        trellis_params: TrellisParams = request.trellis_params

        # Collect all views
        all_views = [
            image_without_background_primary,  # Primary view (original)
            image_without_background_left,      # Left 3/4 view
            image_without_background_right,     # Right 3/4 view
            image_without_background_back,      # Back view
        ]
        
        # Quick Win #3: Validate view consistency
        if not self._validate_view_consistency(all_views, image):
            logger.warning("View consistency check failed - colors may not match perfectly")
            # Continue anyway, but log the warning
        
        # Quick Win #2: Normalize lighting across all views
        all_views_normalized = self._normalize_lighting(all_views)

        # 3. Generate the 3D model with multiple views
        # Order: Primary (front) -> Left -> Right -> Back
        # Primary view has most weight in reconstruction
        trellis_result = self.trellis.generate(
            TrellisRequest(
                images=all_views_normalized,
                seed=request.seed,
                params=trellis_params,
            )
        )

        # Save generated files
        if self.settings.save_generated_files:
            save_files(
                trellis_result, 
                image, 
                image_primary if self.settings.use_original_as_primary else image_enhanced,
                image_without_background_primary,
                image_edited_left,
                image_without_background_left,
                image_edited_right,
                image_without_background_right,
                image_edited_back,
                image_without_background_back,
            )

        # Convert to PNG base64 for response (only if needed)
        image_edited_base64 = None
        image_without_background_base64 = None
        if self.settings.send_generated_files:
            image_edited_base64 = to_png_base64(image_primary if self.settings.use_original_as_primary else image_enhanced)
            image_without_background_base64 = to_png_base64(image_without_background_primary)

        t2 = time.time()
        generation_time = t2 - t1

        logger.info(f"Total generation time: {generation_time} seconds")
        # Clean the GPU memory
        self._clean_gpu_memory()

        response = GenerateResponse(
            generation_time=generation_time,
            ply_file_base64=trellis_result.ply_file if trellis_result else None,
            image_edited_file_base64=image_edited_base64
            if self.settings.send_generated_files
            else None,
            image_without_background_file_base64=image_without_background_base64
            if self.settings.send_generated_files
            else None,
        )
        return response

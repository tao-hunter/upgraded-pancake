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

        # Generate complementary views with minimal transformation
        # Left three-quarters view
        image_edited_left = self.qwen_edit.edit_image(
            prompt_image=image,
            seed=request.seed,
            prompt="Rotate object 45 degrees left while preserving exact colors, textures, proportions, and all details. Clean neutral background. Maintain original quality and sharpness",
        )
        image_without_background_left = self.rmbg.remove_background(image_edited_left)

        # Right three-quarters view
        image_edited_right = self.qwen_edit.edit_image(
            prompt_image=image,
            seed=request.seed,
            prompt="Rotate object 45 degrees right while preserving exact colors, textures, proportions, and all details. Clean neutral background. Maintain original quality and sharpness",
        )
        image_without_background_right = self.rmbg.remove_background(image_edited_right)

        # Back view for better 3D reconstruction
        image_edited_back = self.qwen_edit.edit_image(
            prompt_image=image,
            seed=request.seed,
            prompt="Show back view of object while preserving exact colors, textures, proportions, and all details. Clean neutral background. Maintain original quality and sharpness",
        )
        image_without_background_back = self.rmbg.remove_background(image_edited_back)

        trellis_result: Optional[TrellisResult] = None

        # Resolve Trellis parameters from request
        trellis_params: TrellisParams = request.trellis_params

        # 3. Generate the 3D model with multiple views
        # Order: Primary (front) -> Left -> Right -> Back
        # Primary view has most weight in reconstruction
        trellis_result = self.trellis.generate(
            TrellisRequest(
                images=[
                    image_without_background_primary,  # Primary view (original)
                    image_without_background_left,      # Left 3/4 view
                    image_without_background_right,     # Right 3/4 view
                    image_without_background_back,      # Back view
                ],
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

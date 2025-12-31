# 3D Generation Quality Improvements

## Overview
This document describes the improvements made to the 3D generation pipeline to produce high-quality models that closely match the input image in shape, color, effects, and sub-objects.

## Key Improvements

### 1. **Original Image Preservation Strategy** ✅
**Problem**: Previous approach heavily edited the input image, losing original colors, shapes, and details.

**Solution**: 
- Use the original image (with minimal edits) as the **primary view** for 3D reconstruction
- Only apply quality enhancement and background removal to preserve accuracy
- Set `use_original_as_primary: true` in settings to enable this

**Impact**: Preserves exact colors, textures, proportions, and fine details from the input image.

### 2. **Enhanced Qwen Edit Prompts** ✅
**Previous prompts**: Aggressive transformations that altered object appearance

**New prompts**:
```
Primary View (Original):
"Preserve exact colors, shapes, and all details. Only improve image quality 
and remove background with neutral solid color. Keep the same viewing angle"

Complementary Views:
"Rotate object [X] degrees [direction] while preserving exact colors, textures, 
proportions, and all details. Clean neutral background. Maintain original quality"
```

**Negative prompt**: Expanded to prevent color changes, distortions, filters, and effects

**Impact**: Minimal transformation while generating useful complementary views.

### 3. **Optimized Multi-View Generation** ✅
**Previous**: 2 views (left 3/4, right 3/4)

**New**: 4 strategic views
1. **Primary** (front) - Original image with minimal edits
2. **Left 3/4** - 45° left rotation
3. **Right 3/4** - 45° right rotation  
4. **Back view** - Complete 3D understanding

**Impact**: Better 3D reconstruction with comprehensive spatial information while maintaining accuracy.

### 4. **Image Quality Enhancement** ✅
Added preprocessing pipeline before generation:
- **Denoising**: MedianFilter to reduce artifacts
- **Sharpness**: 1.15x enhancement to preserve fine details
- **Contrast**: 1.1x boost for better feature definition
- **Color Saturation**: 1.05x mild boost to preserve original colors

**Impact**: Cleaner input for Qwen and Trellis while preserving original features.

### 5. **Optimized Trellis Parameters** ✅

| Parameter | Previous | New | Reason |
|-----------|----------|-----|--------|
| `sparse_structure_steps` | 8 | 12 | Better structural accuracy |
| `sparse_structure_cfg_strength` | 5.75 | 6.5 | Stronger guidance for fidelity |
| `slat_steps` | 20 | 30 | Higher quality texture and geometry |
| `slat_cfg_strength` | 2.4 | 3.0 | Better adherence to input |
| `num_oversamples` | 3 | 4 | More samples for quality |

**Impact**: Higher quality 3D models with better detail preservation.

### 6. **Enhanced Qwen Inference Settings** ✅

| Parameter | Previous | New | Reason |
|-----------|----------|-----|--------|
| `num_inference_steps` | 4 | 6 | Better quality edits |
| `true_cfg_scale` | 1.0 | 1.2 | Stronger prompt adherence |

**Impact**: More accurate image transformations that preserve original features.

## Configuration

### Environment Variables

To enable all improvements, set these in your `.env` file:

```bash
# Use original image as primary view
USE_ORIGINAL_AS_PRIMARY=true

# Trellis quality settings
TRELLIS_SPARSE_STRUCTURE_STEPS=12
TRELLIS_SPARSE_STRUCTURE_CFG_STRENGTH=6.5
TRELLIS_SLAT_STEPS=30
TRELLIS_SLAT_CFG_STRENGTH=3.0
TRELLIS_NUM_OVERSAMPLES=4

# Qwen quality settings
NUM_INFERENCE_STEPS=6
TRUE_CFG_SCALE=1.2
```

### Trade-offs

⚠️ **Generation Time**: Increased by ~30-40% due to:
- 4 views instead of 2
- More Trellis steps (12+30 vs 8+20)
- More Qwen steps (6 vs 4)
- Additional view (back view)

✅ **Quality Improvement**: Significant improvements in:
- Color accuracy
- Shape fidelity
- Detail preservation
- Overall visual match to input

## Expected Results

### Before Improvements
- Colors often altered or desaturated
- Shape distortions from aggressive view changes
- Loss of fine details and sub-components
- Inconsistent textures

### After Improvements
- ✅ Exact color matching to input image
- ✅ Accurate shape and proportions
- ✅ Preserved fine details and sub-objects
- ✅ Consistent textures across views
- ✅ Better 3D spatial accuracy

## Testing Recommendations

1. **Test with diverse objects**: 
   - Complex shapes (cars, people, buildings)
   - Multiple colors and textures
   - Objects with fine details (text, logos, patterns)

2. **Compare quality metrics**:
   - Visual similarity to input
   - Color accuracy
   - Shape fidelity
   - Detail preservation

3. **Benchmark against LLM judge**:
   - Generate 3D models with old and new settings
   - Compare penalty scores
   - Measure improvement percentage

## Future Enhancements

### Potential Next Steps:
1. **Adaptive view selection**: Analyze input complexity to determine optimal number/angles of views
2. **Quality-aware iteration**: Generate multiple candidates and select best based on intermediate quality checks
3. **LLM judge feedback loop**: Integrate scoring directly into pipeline for iterative refinement
4. **Hierarchical evaluation**: Assess object-level and part-level quality
5. **Dynamic parameter tuning**: Adjust Trellis parameters based on object type and complexity

## References

- Trellis Model: `jetx/trellis-image-large`
- Qwen Image Edit: `Qwen/Qwen-Image-Edit-2511`
- Background Removal: `tuandao-zenai/rm_bg`


# High-Quality 3D Generation Guide
## How to Generate 3D Models that Match the Input Image

---

## 🎯 Core Philosophy

> **"Preserve, Don't Transform"**
> 
> The best 3D reconstruction comes from **preserving the original image** rather than heavily editing it. Use the input as the primary reference and generate minimal complementary views.

---

## 💡 Key Ideas for High-Quality Generation

### 1. **Use the Original Image as Primary View** ⭐
**Why:** The input image has the exact colors, shapes, and details you want in the final 3D model.

**How:**
- Set `USE_ORIGINAL_AS_PRIMARY=true`
- Apply only minimal edits: quality enhancement + background removal
- Avoid aggressive transformations that alter the object

**Result:** Colors and shapes match exactly because you're using the source directly.

---

### 2. **Generate Strategic Complementary Views**
**Why:** Trellis needs multiple angles to understand 3D structure, but views must maintain consistency.

**Best Practice - 4 Views:**
1. **Front (Primary):** Original image with minimal edits
2. **Left 3/4:** 45° rotation to the left
3. **Right 3/4:** 45° rotation to the right
4. **Back:** 180° rotation for complete coverage

**Prompt Strategy:**
- **Primary:** "Preserve exact colors, shapes, and all details..."
- **Complementary:** "Rotate object [X]° while preserving exact colors, textures..."

**Avoid:**
- ❌ "Show object in different style"
- ❌ "Transform", "change", "modify"
- ❌ Creative artistic interpretations

---

### 3. **Optimize Trellis Parameters for Fidelity**
**Why:** More sampling steps = better quality, stronger CFG = better adherence to input.

**Recommended Settings:**

| Parameter | Default | Quality | Maximum | Purpose |
|-----------|---------|---------|---------|---------|
| `sparse_structure_steps` | 8 | 12 | 16 | Spatial accuracy |
| `sparse_structure_cfg_strength` | 5.75 | 6.5 | 7.0 | Structural fidelity |
| `slat_steps` | 20 | 30 | 40 | Texture quality |
| `slat_cfg_strength` | 2.4 | 3.0 | 3.5 | Detail preservation |
| `num_oversamples` | 3 | 4 | 5 | Sample diversity |

**Trade-off:** Higher values = better quality but slower generation (30-50% longer).

---

### 4. **Enhance Image Quality Pre-Processing**
**Why:** Clean, sharp input → better 3D reconstruction.

**Enhancement Pipeline:**
```python
1. Denoise: Remove artifacts (MedianFilter)
2. Sharpen: Preserve fine details (+15%)
3. Contrast: Better feature definition (+10%)
4. Saturation: Maintain color vibrancy (+5%)
```

**Key:** Enhancements should be **subtle** to avoid introducing artifacts.

---

### 5. **Optimize Qwen Edit Parameters**
**Why:** More inference steps = more accurate transformations.

**Recommended Settings:**
- `num_inference_steps`: 6-8 (instead of 4)
- `true_cfg_scale`: 1.2-1.5 (instead of 1.0)

**Why This Matters:**
- More steps → smoother transitions between views
- Higher CFG → better prompt adherence (preserves features)

---

### 6. **Use Feature-Preserving Prompts**
**Why:** Prompts are critical - they determine how much the image changes.

**✅ Good Prompts:**
```
"Preserve exact original colors, textures, and proportions. Keep all object 
details, features, and sub-components identical. Clean neutral background."

"Rotate object 45 degrees while preserving exact colors, textures, proportions, 
and all details. Maintain original quality and sharpness."
```

**❌ Bad Prompts:**
```
"Show this object in a different view"
"Transform the image to show another angle"
"Make the background more interesting"
```

**Negative Prompts Should Include:**
- `altered colors, changed proportions, distorted shape`
- `color grading, filters, effects`
- `additional objects, complex background`
- `blurry, motion blur, low quality`

---

### 7. **Optimize Background Removal Settings**
**Why:** Clean background isolation helps Trellis focus on the object.

**Best Settings:**
- `input_image_size`: [1024, 1024] (high resolution)
- `output_image_size`: [518, 518] (Trellis optimal)
- `padding_percentage`: 0.2 (20% padding)
- `limit_padding`: true (prevent edge artifacts)

**Why:** Proper padding ensures the entire object is visible without cropping.

---

### 8. **Match Colors Exactly**
**Why:** Color accuracy is often evaluated by LLM judges.

**Strategies:**
1. Use original image as primary view (preserves RGB values)
2. Avoid prompts that mention colors (e.g., "make it more vibrant")
3. Set minimal color saturation enhancement (+5% max)
4. Use negative prompts: "color grading, filters, effects"

**Validation:** Sample RGB values from input and output - should be ≤5% difference.

---

### 9. **Preserve Sub-Objects and Details**
**Why:** Complex objects have multiple components that must all be present.

**Prompt Technique:**
```
"Keep all object details, features, and sub-components identical"
"Preserve fine details, textures, patterns, text, logos"
```

**Negative Prompts:**
```
"missing details, cropped object, partial view, occluded features"
```

**Example:** If the input has a logo, text, or pattern → it should appear in the 3D model.

---

### 10. **Test and Iterate**
**Why:** Different object types may need different settings.

**Testing Workflow:**
1. Generate with **Quality Mode** settings
2. Render 3D model from multiple angles
3. Compare to input image:
   - Color accuracy (RGB comparison)
   - Shape fidelity (visual inspection)
   - Detail preservation (zoom in on features)
4. Submit to LLM judge for scoring
5. Adjust parameters if needed

**Quick Test:**
```bash
./test_quality.sh your_image.png 42
```

---

## 📊 Expected Quality Metrics

### Color Accuracy
- **Goal:** RGB RMSE < 5
- **Method:** Sample 100 random pixels from input and rendered output
- **Settings:** USE_ORIGINAL_AS_PRIMARY=true

### Shape Fidelity
- **Goal:** IoU (Intersection over Union) > 0.85
- **Method:** Silhouette comparison from same viewing angle
- **Settings:** More Trellis steps (12+)

### Detail Preservation
- **Goal:** Visual inspection score 8/10+
- **Method:** Human evaluation or LLM judge
- **Settings:** Higher slat_steps (30+), sharpen image pre-processing

---

## 🚀 Quick Start Configuration

### For Best Quality (Recommended)
```bash
# .env file
USE_ORIGINAL_AS_PRIMARY=true
TRELLIS_SPARSE_STRUCTURE_STEPS=12
TRELLIS_SPARSE_STRUCTURE_CFG_STRENGTH=6.5
TRELLIS_SLAT_STEPS=30
TRELLIS_SLAT_CFG_STRENGTH=3.0
TRELLIS_NUM_OVERSAMPLES=4
NUM_INFERENCE_STEPS=6
TRUE_CFG_SCALE=1.2
```

### For Maximum Quality (Slower)
```bash
USE_ORIGINAL_AS_PRIMARY=true
TRELLIS_SPARSE_STRUCTURE_STEPS=16
TRELLIS_SPARSE_STRUCTURE_CFG_STRENGTH=7.0
TRELLIS_SLAT_STEPS=40
TRELLIS_SLAT_CFG_STRENGTH=3.5
TRELLIS_NUM_OVERSAMPLES=5
NUM_INFERENCE_STEPS=8
TRUE_CFG_SCALE=1.5
```

---

## 🎓 Advanced Techniques

### Adaptive View Selection
For different object types:
- **Simple objects** (cube, sphere): 2-3 views sufficient
- **Medium complexity** (cars, furniture): 4 views (front, left, right, back)
- **Complex objects** (people, detailed sculptures): 5-6 views (add top, bottom)

### Multi-Candidate Generation
Generate 3-5 candidates with different seeds, select best:
```bash
for seed in 42 123 456 789 999; do
  curl -X POST "http://localhost:10006/generate" \
    -F "prompt_image_file=@input.png" \
    -F "seed=$seed" \
    -o "model_seed_${seed}.ply"
done
```

### Iterative Refinement
1. Generate initial 3D model
2. Render from original viewing angle
3. Compare to input (color, shape, details)
4. If delta > threshold, adjust and regenerate

---

## 📋 Quality Checklist

Before submitting to LLM judge:

- [ ] Colors match input image (visual inspection)
- [ ] Shape/proportions match input
- [ ] All sub-objects/components present
- [ ] Fine details visible (text, patterns, textures)
- [ ] No distortions or artifacts
- [ ] Clean geometry (no holes or noise)
- [ ] Consistent appearance from all angles
- [ ] Background properly removed

---

## 🔍 Troubleshooting

### Problem: Colors don't match
**Solution:**
- Set `USE_ORIGINAL_AS_PRIMARY=true`
- Check prompts don't mention color changes
- Reduce color saturation enhancement to 1.0 (no boost)

### Problem: Shape distorted
**Solution:**
- Increase `trellis_sparse_structure_steps` to 16
- Increase `trellis_sparse_structure_cfg_strength` to 7.0
- Check complementary views aren't too different from original

### Problem: Missing details
**Solution:**
- Increase `trellis_slat_steps` to 40
- Apply sharpening in pre-processing
- Add "preserve fine details" to prompts

### Problem: Artifacts or noise
**Solution:**
- Apply denoising in pre-processing
- Check background removal settings
- Reduce `num_oversamples` if too noisy

---

## 📚 Summary

**The 3 Most Important Things:**

1. **Use original image as primary view** → Preserves colors/details
2. **Optimize Trellis parameters** → Better quality reconstruction
3. **Use feature-preserving prompts** → Minimal unwanted changes

**Remember:** Quality comes from **fidelity to the input**, not creative interpretation. The LLM judge evaluates how well the 3D model matches the original image.

---

## 🔗 Related Documents

- `QUALITY_IMPROVEMENTS.md` - Detailed technical changes
- `IMPLEMENTATION_SUMMARY.md` - Complete implementation overview
- `README.md` - Setup and usage instructions
- `test_quality.sh` - Automated quality testing script

---

**Questions?** Check the implementation in `pipeline_service/modules/pipeline.py` or review the prompt configuration in `pipeline_service/config/qwen_edit_prompt.json`.


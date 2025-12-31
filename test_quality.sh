#!/bin/bash
# Test script to compare quality before and after improvements

echo "==================================="
echo "3D Generation Quality Test Script"
echo "==================================="
echo ""

# Check if image file is provided
if [ -z "$1" ]; then
    echo "Usage: ./test_quality.sh <input_image.png> [seed]"
    echo "Example: ./test_quality.sh cr7.png 42"
    exit 1
fi

INPUT_IMAGE=$1
SEED=${2:-42}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="test_results_${TIMESTAMP}"

echo "Input Image: $INPUT_IMAGE"
echo "Seed: $SEED"
echo "Output Directory: $OUTPUT_DIR"
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Test 1: Legacy mode (faster, lower quality)
echo "📊 Test 1: Legacy Mode (Speed Priority)"
echo "Settings: 2 views, basic parameters"
echo "-----------------------------------"

export USE_ORIGINAL_AS_PRIMARY=false
export TRELLIS_SPARSE_STRUCTURE_STEPS=8
export TRELLIS_SPARSE_STRUCTURE_CFG_STRENGTH=5.75
export TRELLIS_SLAT_STEPS=20
export TRELLIS_SLAT_CFG_STRENGTH=2.4
export TRELLIS_NUM_OVERSAMPLES=3
export NUM_INFERENCE_STEPS=4
export TRUE_CFG_SCALE=1.0

echo "Generating... (this may take 2-3 minutes)"
START_TIME=$(date +%s)

curl -X POST "http://localhost:10006/generate" \
  -F "prompt_image_file=@${INPUT_IMAGE}" \
  -F "seed=${SEED}" \
  -o "${OUTPUT_DIR}/model_legacy.ply" \
  -w "\nHTTP Status: %{http_code}\n" \
  2>/dev/null

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo "✓ Legacy generation completed in ${DURATION}s"
echo "  Output: ${OUTPUT_DIR}/model_legacy.ply"
echo ""

# Test 2: High-quality mode (slower, better quality)
echo "📊 Test 2: High-Quality Mode (Quality Priority)"
echo "Settings: 4 views, optimized parameters"
echo "-----------------------------------"

export USE_ORIGINAL_AS_PRIMARY=true
export TRELLIS_SPARSE_STRUCTURE_STEPS=12
export TRELLIS_SPARSE_STRUCTURE_CFG_STRENGTH=6.5
export TRELLIS_SLAT_STEPS=30
export TRELLIS_SLAT_CFG_STRENGTH=3.0
export TRELLIS_NUM_OVERSAMPLES=4
export NUM_INFERENCE_STEPS=6
export TRUE_CFG_SCALE=1.2

echo "Generating... (this may take 3-5 minutes)"
START_TIME=$(date +%s)

curl -X POST "http://localhost:10006/generate" \
  -F "prompt_image_file=@${INPUT_IMAGE}" \
  -F "seed=${SEED}" \
  -o "${OUTPUT_DIR}/model_quality.ply" \
  -w "\nHTTP Status: %{http_code}\n" \
  2>/dev/null

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo "✓ Quality generation completed in ${DURATION}s"
echo "  Output: ${OUTPUT_DIR}/model_quality.ply"
echo ""

# Test 3: Maximum quality mode (slowest, best quality)
echo "📊 Test 3: Maximum Quality Mode (Maximum Fidelity)"
echo "Settings: 4 views, maximum parameters"
echo "-----------------------------------"

export USE_ORIGINAL_AS_PRIMARY=true
export TRELLIS_SPARSE_STRUCTURE_STEPS=16
export TRELLIS_SPARSE_STRUCTURE_CFG_STRENGTH=7.0
export TRELLIS_SLAT_STEPS=40
export TRELLIS_SLAT_CFG_STRENGTH=3.5
export TRELLIS_NUM_OVERSAMPLES=5
export NUM_INFERENCE_STEPS=8
export TRUE_CFG_SCALE=1.5

echo "Generating... (this may take 5-7 minutes)"
START_TIME=$(date +%s)

curl -X POST "http://localhost:10006/generate" \
  -F "prompt_image_file=@${INPUT_IMAGE}" \
  -F "seed=${SEED}" \
  -o "${OUTPUT_DIR}/model_max_quality.ply" \
  -w "\nHTTP Status: %{http_code}\n" \
  2>/dev/null

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo "✓ Maximum quality generation completed in ${DURATION}s"
echo "  Output: ${OUTPUT_DIR}/model_max_quality.ply"
echo ""

# Summary
echo "==================================="
echo "✅ Test Complete!"
echo "==================================="
echo ""
echo "Results saved to: $OUTPUT_DIR/"
echo "  - model_legacy.ply (fast, 2 views)"
echo "  - model_quality.ply (balanced, 4 views)"
echo "  - model_max_quality.ply (slow, 4 views, max params)"
echo ""
echo "Next Steps:"
echo "1. View the models: python view_3d.py --ply_file ${OUTPUT_DIR}/model_quality.ply"
echo "2. Compare visual quality against input image"
echo "3. Send to LLM judge for scoring"
echo ""
echo "Manual Comparison Checklist:"
echo "  □ Color accuracy (RGB values match input)"
echo "  □ Shape fidelity (geometry matches input)"
echo "  □ Detail preservation (fine features visible)"
echo "  □ Sub-objects present (all components included)"
echo "  □ Texture consistency (materials look correct)"
echo ""


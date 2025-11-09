#!/bin/bash

# Smoke test for nike.com example

set -e

echo "=== Running Smoke Test ==="
echo ""

# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ]; then
  echo "❌ Error: OPENAI_API_KEY environment variable not set"
  echo "Please set your OpenAI API key:"
  echo "  export OPENAI_API_KEY=sk-..."
  exit 1
fi

# Build all packages
echo "Building packages..."
pnpm run build

# Run the audit
echo ""
echo "Running audit on nike.com..."
pnpm --filter @search-audit/cli start run \
  --site https://www.nike.com \
  --config ./configs/sites/nike.yaml \
  --queries ./data/queries/nike-en.json \
  --topk 10 \
  --seed 42 \
  --out ./runs

# Find the most recent run directory
LATEST_RUN=$(ls -t runs | head -1)

if [ -z "$LATEST_RUN" ]; then
  echo "❌ Error: No run directory found"
  exit 1
fi

RUN_DIR="./runs/$LATEST_RUN"

echo ""
echo "=== Smoke Test Results ==="
echo "Run directory: $RUN_DIR"

# Check if required files exist
REQUIRED_FILES=(
  "audit.jsonl"
  "report.md"
  "report.html"
)

FAILED=0
for file in "${REQUIRED_FILES[@]}"; do
  if [ -f "$RUN_DIR/$file" ]; then
    echo "✓ Found $file"
  else
    echo "❌ Missing $file"
    FAILED=1
  fi
done

# Check if we have at least some query artifacts
SCREENSHOT_COUNT=$(ls -1 $RUN_DIR/*-screenshot.png 2>/dev/null | wc -l)
HTML_COUNT=$(ls -1 $RUN_DIR/*-page.html 2>/dev/null | wc -l)

if [ "$SCREENSHOT_COUNT" -ge 3 ]; then
  echo "✓ Found $SCREENSHOT_COUNT screenshots"
else
  echo "⚠ Only found $SCREENSHOT_COUNT screenshots (expected at least 3)"
  FAILED=1
fi

if [ "$HTML_COUNT" -ge 3 ]; then
  echo "✓ Found $HTML_COUNT HTML snapshots"
else
  echo "⚠ Only found $HTML_COUNT HTML snapshots (expected at least 3)"
  FAILED=1
fi

# Check JSONL has valid records
RECORD_COUNT=$(wc -l < "$RUN_DIR/audit.jsonl" 2>/dev/null || echo 0)
if [ "$RECORD_COUNT" -ge 3 ]; then
  echo "✓ Found $RECORD_COUNT audit records"
else
  echo "⚠ Only found $RECORD_COUNT audit records (expected at least 3)"
  FAILED=1
fi

echo ""
if [ $FAILED -eq 0 ]; then
  echo "=== ✓ Smoke Test Passed ==="
  echo ""
  echo "To view the report:"
  echo "  cat $RUN_DIR/report.md"
  echo "  open $RUN_DIR/report.html"
  exit 0
else
  echo "=== ❌ Smoke Test Failed ==="
  exit 1
fi

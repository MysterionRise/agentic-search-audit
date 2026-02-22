#!/usr/bin/env bash
set -euo pipefail

# ─── Demo Runner for Agentic Search Audit ───
# Runs a quick audit on 3 flagship retailer sites with 5 queries each.
# Usage: ./scripts/demo.sh

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEMO_DIR="./runs/demo-${TIMESTAMP}"
MAX_QUERIES=5
SITES=("target" "bestbuy" "zalando")

echo "============================================"
echo "  Agentic Search Audit - Demo Run"
echo "  $(date)"
echo "============================================"
echo ""

# Pre-flight checks
if [ -z "${OPENROUTER_API_KEY:-}" ]; then
    echo "ERROR: OPENROUTER_API_KEY is not set."
    echo "Export it before running: export OPENROUTER_API_KEY=sk-or-..."
    exit 1
fi

# Check search-audit is installed
if ! command -v search-audit &> /dev/null; then
    echo "ERROR: search-audit command not found."
    echo "Install with: pip install -e '.[dev]'"
    exit 1
fi

mkdir -p "$DEMO_DIR"
echo "Output directory: $DEMO_DIR"
echo ""

PASS=0
FAIL=0

for site in "${SITES[@]}"; do
    echo "────────────────────────────────────────────"
    echo "  Auditing: $site"
    echo "────────────────────────────────────────────"
    SITE_DIR="${DEMO_DIR}/${site}"

    if search-audit --site "$site" \
        --max-queries "$MAX_QUERIES" \
        --no-headless \
        --output "$SITE_DIR" \
        --log-level INFO; then
        echo "  ✓ $site completed successfully"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $site failed (exit code $?)"
        FAIL=$((FAIL + 1))
    fi
    echo ""
done

echo "============================================"
echo "  Demo Complete"
echo "  Passed: $PASS / ${#SITES[@]}"
echo "  Failed: $FAIL / ${#SITES[@]}"
echo "  Results: $DEMO_DIR"
echo "============================================"

# Open the first HTML report if on macOS
if [ "$PASS" -gt 0 ] && command -v open &> /dev/null; then
    FIRST_REPORT=$(find "$DEMO_DIR" -name "report.html" -type f | head -1)
    if [ -n "$FIRST_REPORT" ]; then
        echo ""
        echo "Opening first report: $FIRST_REPORT"
        open "$FIRST_REPORT"
    fi
fi

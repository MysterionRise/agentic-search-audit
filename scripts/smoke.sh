#!/bin/bash
# Smoke test for Nike.com audit

set -e

echo "====================================="
echo "Agentic Search Audit - Smoke Test"
echo "====================================="

# Check environment
echo "Checking environment..."

if [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: OPENAI_API_KEY environment variable not set"
    exit 1
fi

# Check dependencies
echo "Checking Python dependencies..."
python -c "import agentic_search_audit" || {
    echo "ERROR: Package not installed. Run: pip install -e ."
    exit 1
}

# Check npx availability
echo "Checking npx (for chrome-devtools-mcp)..."
npx --version > /dev/null 2>&1 || {
    echo "ERROR: npx not found. Please install Node.js"
    exit 1
}

# Run audit with first 3 queries only (for quick test)
echo ""
echo "Running audit on Nike.com (3 queries)..."
echo ""

# Create temporary queries file with just 3 queries
TMP_QUERIES=$(mktemp)
cat > "$TMP_QUERIES" << EOF
{
  "queries": [
    {"id": "q001", "text": "running shoes", "lang": "en", "origin": "predefined"},
    {"id": "q002", "text": "air jordan", "lang": "en", "origin": "predefined"},
    {"id": "q003", "text": "basketball shoes", "lang": "en", "origin": "predefined"}
  ]
}
EOF

# Run audit
search-audit \
    --site nike \
    --queries "$TMP_QUERIES" \
    --log-level INFO \
    --output ./runs/smoke-test

# Cleanup
rm -f "$TMP_QUERIES"

echo ""
echo "====================================="
echo "Smoke test completed successfully!"
echo "Check results in: ./runs/smoke-test"
echo "====================================="

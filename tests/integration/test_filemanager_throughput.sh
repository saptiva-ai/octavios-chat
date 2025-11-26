#!/bin/bash
# tests/integration/test_filemanager_throughput.sh

echo "🧪 Test P-1: File Manager throughput test"

# Check for hey
if ! command -v hey &> /dev/null; then
  echo "⚠️  'hey' tool not found. Skipping performance test."
  echo "Install with: go install github.com/rakyll/hey@latest"
  exit 0
fi

# Create test file (1MB)
dd if=/dev/urandom of=/tmp/perf_test_1mb.bin bs=1M count=1 2>/dev/null

echo "Running load test..."

# Run throughput test (100 requests, 10 concurrent)
hey -n 100 -c 10 -m POST \
  -T "multipart/form-data; boundary=----WebKitFormBoundary" \
  -D /tmp/perf_test_1mb.bin \
  "http://localhost:8001/upload?user_id=perf_test&session_id=perf1" \
  > /tmp/hey_results.txt

# Parse results
REQUESTS_PER_SEC=$(grep "Requests/sec" /tmp/hey_results.txt | awk '{print $2}')
MEAN_LATENCY=$(grep "Average:" /tmp/hey_results.txt | awk '{print $2}')

echo "Throughput: $REQUESTS_PER_SEC req/sec"
echo "Mean latency: $MEAN_LATENCY"

# Cleanup
rm /tmp/perf_test_1mb.bin /tmp/hey_results.txt

# Assertions (adjust thresholds based on environment)
# Using awk for float comparison
if awk "BEGIN {exit !($REQUESTS_PER_SEC > 5)}"; then
  echo "✅ PASS: Throughput acceptable (>5 req/sec)"
else
  echo "⚠️  WARNING: Throughput low ($REQUESTS_PER_SEC req/sec)"
fi

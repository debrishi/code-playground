#!/bin/bash
set -euo pipefail

# End-to-end test runner for the Python lambda.
# Builds the Docker image, starts the container, runs all test suites, and cleans up.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE_NAME="runbox-lambda-python-test"
CONTAINER_NAME="runbox-test-container"
PORT=9000

# Always clean up, whatever path the script exits through: stop the container
# (`--rm` removes it) and delete the test image. BuildKit's build cache
# survives `rmi`, so the next run still rebuilds quickly.
cleanup() {
    docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
    docker rmi -f "$IMAGE_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== Building Docker image ==="
docker build --platform linux/arm64 -t "$IMAGE_NAME" "$SCRIPT_DIR/../lambda"

echo ""
echo "=== Starting container on port $PORT ==="
docker run --rm -d --name "$CONTAINER_NAME" -p "$PORT:8080" "$IMAGE_NAME"

# Wait for the container to be ready
echo "Waiting for container to be ready..."
for i in $(seq 1 10); do
    if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/2015-03-31/functions/function/invocations" -X POST -d '{"body":"{\"language\":\"python\",\"code\":\"print(1)\"}"}' | grep -q "200"; then
        echo "Container is ready."
        break
    fi
    if [ "$i" -eq 10 ]; then
        echo "❌ Container failed to start"
        docker stop "$CONTAINER_NAME" 2>/dev/null || true
        exit 1
    fi
    sleep 2
done

echo ""
echo "=== Running test_suite.sh ==="
SUITE_EXIT=0
bash "$SCRIPT_DIR/test_suite.sh" || SUITE_EXIT=$?

echo ""
echo "=== Running test_stdin.sh ==="
STDIN_EXIT=0
bash "$SCRIPT_DIR/test_stdin.sh" || STDIN_EXIT=$?

echo ""
echo "=== Running test_stress.sh ==="
STRESS_EXIT=0
bash "$SCRIPT_DIR/test_stress.sh" || STRESS_EXIT=$?

echo ""
echo "=== Cleaning up container and image ==="
# The EXIT trap handles this too; doing it here makes the happy path explicit.
cleanup

echo ""
echo "=== Results ==="
TOTAL_EXIT=$((SUITE_EXIT + STDIN_EXIT + STRESS_EXIT))
if [ "$TOTAL_EXIT" -eq 0 ]; then
    echo "🎉 All test suites passed"
else
    echo "⚠️  Some tests failed (suite=$SUITE_EXIT, stdin=$STDIN_EXIT, stress=$STRESS_EXIT)"
fi
exit "$TOTAL_EXIT"

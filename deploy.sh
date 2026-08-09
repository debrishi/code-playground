#!/bin/bash
# Deploy the whole stack: Lambda backend (AWS SAM) first, then the editor
# (Cloudflare Pages) built against the freshly deployed Function URL.
#
# Usage:
#   ./deploy.sh                                        # CORS open to *
#   ./deploy.sh "https://runbox.pages.dev,http://localhost:5173"
#   PAGES_PROJECT=my-project ./deploy.sh
#
# One-time setup (before the first deploy):
#   npx wrangler login                # or set CLOUDFLARE_API_TOKEN
#   npx wrangler pages project create runbox --production-branch=main
#                                     # skip if the Pages project already exists
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ALLOWED_ORIGINS="${1:-}"
PAGES_PROJECT="${PAGES_PROJECT:-runbox}"

for cmd in sam docker aws node npm; do
    command -v "$cmd" >/dev/null || { echo "❌ $cmd not found — install it first"; exit 1; }
done
docker info >/dev/null 2>&1 || { echo "❌ Docker daemon is not running"; exit 1; }

# ---------- Pre-flight: auth checks (fail fast, before touching anything) ----
echo "=== Checking AWS credentials ==="
aws sts get-caller-identity --query Arn --output text 2>/dev/null || {
    echo "❌ No valid AWS credentials."
    echo "   Run 'aws configure' (access keys) or 'aws sso login' (Identity Center),"
    echo "   and export AWS_PROFILE if you use a named profile."
    exit 1
}

echo ""
echo "=== Checking Cloudflare auth ==="
cd "$ROOT/editor"
WHOAMI="$(npx --yes wrangler whoami 2>&1 || true)"
if echo "$WHOAMI" | grep -qi "not authenticated"; then
    echo "❌ Wrangler is not authenticated."
    echo "   Run 'npx wrangler login', or set CLOUDFLARE_API_TOKEN."
    exit 1
fi
echo "Cloudflare auth OK."

# ---------- 1. Backend — AWS Lambda via SAM ----------------------------------
cd "$ROOT/lambda"

echo "=== sam build ==="
sam build

echo ""
echo "=== sam deploy ==="
if [ -n "$ALLOWED_ORIGINS" ]; then
    # Quoted value keeps the commas inside a single CommaDelimitedList parameter.
    sam deploy --parameter-overrides "AllowedOrigins=\"$ALLOWED_ORIGINS\""
else
    sam deploy
fi

FUNCTION_URL="$(aws cloudformation describe-stacks \
    --stack-name runbox-lambda --region ap-south-1 \
    --query "Stacks[0].Outputs[?OutputKey=='FunctionUrl'].OutputValue" \
    --output text)"
echo ""
echo "Function URL: $FUNCTION_URL"

# ---------- 2. Frontend — Cloudflare Pages -----------------------------------
cd "$ROOT/editor"

[ -d node_modules ] || { echo "=== Installing dependencies ==="; npm install; }

echo ""
echo "=== Building editor (VITE_LAMBDA_URL=$FUNCTION_URL) ==="
VITE_LAMBDA_URL="$FUNCTION_URL" npm run build

echo ""
echo "=== Deploying dist/ to Cloudflare Pages project '$PAGES_PROJECT' ==="
npx wrangler pages deploy dist --project-name="$PAGES_PROJECT" --branch=main

echo ""
echo "✅ Deployed. Smoke test: open the Pages URL and click Run Code."
echo "   Roll back via Cloudflare dashboard → Deployments → previous build → Rollback."

# Deployment — editor

Vite SPA, deployed to Cloudflare Pages via direct upload. The scripted path
is [`deploy.sh`](../deploy.sh) at the repo root — it deploys the Lambda and
then the editor in one run. Prefer it over the manual steps below.

## 1. One-time setup

```bash
npx wrangler login    # or set CLOUDFLARE_API_TOKEN

# Only if the Pages project doesn't exist yet:
npx wrangler pages project create runbox --production-branch=main
```

The create command prints the production URL (e.g. `runbox.pages.dev`).

Tighten Lambda CORS to this origin (and localhost for dev) by redeploying
with the origins argument:

```bash
../deploy.sh "https://runbox.pages.dev,http://localhost:5173"
```

## 2. Deploy / re-deploy

```bash
../deploy.sh
```

Equivalent manual steps for the frontend half only:

```bash
export LAMBDA_URL=$(aws lambda get-function-url-config --region ap-south-1 \
  --function-name runbox-lambda --query FunctionUrl --output text)
VITE_LAMBDA_URL=$LAMBDA_URL npm run build
npx wrangler pages deploy dist --project-name=runbox --branch=main
```

Smoke test: open the Pages URL, click **Run Code** with `Developer` in stdin.
Expect `Hello Developer!`.

Roll back via dashboard → Deployments → previous build → **Rollback**.

## Notes

- **No GitHub auto-deploy.** Direct-upload Pages projects don't support
  *Connect to Git*. Every deploy is manual.
- **The Workers + Static Assets UI flow doesn't work for this app** —
  it expects a `wrangler.toml` and uses Worker semantics. Stay on Pages.

# Deployment — code-editor

Vite static SPA hosted on **Cloudflare Pages** (free tier). Backend is the
runner Lambda — see [`../code-lambda/deploy.md`](../code-lambda/deploy.md).

| Resource | Value |
|---|---|
| Host | Cloudflare Pages |
| Build command | `cd code-editor && npm install && npm run build` |
| Output directory | `code-editor/dist` |
| Production URL | `https://<project>.pages.dev` |

## Steps

### 1. Push the repo to GitHub

```bash
git remote add origin git@github.com:<user>/code-playground.git
git push -u origin main
```

### 2. Create the Pages project

Cloudflare dashboard → **Workers & Pages** → **Create application** →
**Pages** → **Connect to Git** → select repo. Production branch: `main`.

### 3. Build settings

| Field | Value |
|---|---|
| Framework preset | Vite |
| Build command | `cd code-editor && npm install && npm run build` |
| Build output directory | `code-editor/dist` |
| Root directory | *(blank)* |
| Node version | `20` |

### 4. Environment variables

In **Settings → Environment variables → Production**:

```
VITE_LAMBDA_URL = https://kvdcixmh7iojuulgcyg7p7tiia0rwhps.lambda-url.ap-south-1.on.aws/
```

Vite inlines this at build time — must be set before the first deploy.

### 5. Deploy

Click **Save and Deploy**. ~60–90 s for first build.

### 6. Tighten Lambda CORS

```bash
aws lambda update-function-url-config --region ap-south-1 \
  --function-name code-lambda \
  --cors '{"AllowOrigins":["https://<project>.pages.dev"],"AllowMethods":["POST"],"AllowHeaders":["content-type"],"MaxAge":86400}'
```

### 7. Smoke test

Open `https://<project>.pages.dev`, click **Run Code** with `Developer` in
stdin. Expect green "Finished" + `Hello Developer!` in the output panel.

## Redeploy after code changes

```bash
git push origin main
```

Pages auto-builds and deploys in ~60 s. Roll back via dashboard →
Deployments → previous build → **Rollback to this deployment**.

## Common failures

1. **`Configuration Error` on Run Code** — `VITE_LAMBDA_URL` wasn't set in
   Production env before the build. Set it, re-trigger the build.
2. **Build fails on `cd code-editor`** — root directory is set, or output
   dir is `dist` instead of `code-editor/dist`.
3. **CORS error in browser, 200 from `curl`** — preflight cached. Hard-refresh
   or wait `MaxAge` (86400 s) for the new origin to take effect.

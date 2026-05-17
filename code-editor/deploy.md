# Deployment — code-editor

The frontend is a Vite-built static SPA. Deployed via **Cloudflare Pages**
on its always-free tier — unlimited bandwidth, automatic HTTPS, GitHub-driven
deploys. The companion runner Lambda lives on AWS; see
[`../code-lambda/deploy.md`](../code-lambda/deploy.md) for that side.

| Resource | Value |
|---|---|
| Host | Cloudflare Pages |
| Build command | `cd code-editor && npm install && npm run build` |
| Output directory | `code-editor/dist` |
| Production URL | `https://<project>.pages.dev` (assigned at first deploy) |
| Lambda Function URL | `https://kvdcixmh7iojuulgcyg7p7tiia0rwhps.lambda-url.ap-south-1.on.aws/` |
| Cost | $0.00/month (well under all limits) |

## Why Cloudflare Pages

| | Pages | Vercel | Netlify | S3+CloudFront |
|---|---|---|---|---|
| Bandwidth/mo | **Unlimited** | 100 GB | 100 GB | 1 TB free, then $0.085/GB |
| Auto-deploy on push | Yes | Yes | Yes | DIY |
| HTTPS | Free | Free | Free | Free via ACM |
| Setup time | 5 min | 5 min | 5 min | 60 min |
| Hobby-tier TOS gotcha | None | "non-commercial only" | None | Pay-per-use |

Pages wins on bandwidth (no asterisk) and parity-of-DX with Vercel/Netlify. For a
playground that calls Lambda for every Run Code click, the static site itself
serves a tiny payload (~71 KB JS gzipped + 21 KB woff2), so any of these would
work — Pages is just the lowest-friction free option.

## Prerequisites

1. The repo pushed to a GitHub remote (Cloudflare Pages reads from GitHub or
   GitLab; no other VCS for free tier).
2. A Cloudflare account ([dash.cloudflare.com](https://dash.cloudflare.com), free).
3. The Lambda backend already deployed (see `../code-lambda/deploy.md`) so
   `VITE_LAMBDA_URL` has something to point at.

## Steps

### 1. Push the repo to GitHub

If `code-playground` isn't on GitHub yet, create an empty repo on github.com,
then:

```bash
git remote add origin git@github.com:<your-user>/code-playground.git
git push -u origin main
```

### 2. Create the Pages project

Cloudflare dashboard → **Workers & Pages** → **Create application** →
**Pages** tab → **Connect to Git**.

- Select the GitHub repo.
- **Project name** — becomes the subdomain (`<project>.pages.dev`).
  Pick something url-friendly, e.g. `code-playground`.
- **Production branch** — `main`.

### 3. Build settings

| Field | Value |
|---|---|
| Framework preset | **Vite** (or "None" — both work) |
| Build command | `cd code-editor && npm install && npm run build` |
| Build output directory | `code-editor/dist` |
| Root directory | *(leave blank — repo root)* |
| Node version | `20` (set in **Settings → Environment variables → Build**) |

The `cd code-editor` prefix is required because Pages assumes the build runs
from the repo root, but our Vite project lives in the `code-editor/`
subdirectory of the monorepo.

### 4. Environment variables

In the Pages project's **Settings → Environment variables**, add for the
**Production** environment:

```
VITE_LAMBDA_URL = https://kvdcixmh7iojuulgcyg7p7tiia0rwhps.lambda-url.ap-south-1.on.aws/
```

Vite inlines `import.meta.env.VITE_*` variables at **build time**, not runtime —
so this must be set in Pages before the first deploy. Changing it later
requires a rebuild (re-trigger from the dashboard or push a no-op commit).

### 5. Deploy

Click **Save and Deploy**. First build takes ~60–90 s (cold container,
fresh `npm install`). Subsequent builds are faster (~30–45 s) thanks to
build caching.

When the build succeeds, the project's production URL goes live at
`https://<project>.pages.dev`. Each branch and each commit also gets its own
preview URL (e.g. `https://abcd1234.<project>.pages.dev`) that's pinned to
that exact build forever — useful for rollbacks.

### 6. Tighten the Lambda CORS

The Lambda Function URL was provisioned with `AllowOrigins: ["*"]` for initial
testing. Once the Pages URL is known, restrict CORS to just that origin so
the runner won't accept cross-origin POSTs from arbitrary sites:

```bash
aws lambda update-function-url-config --region ap-south-1 \
  --function-name code-lambda \
  --cors '{"AllowOrigins":["https://<project>.pages.dev"],"AllowMethods":["POST"],"AllowHeaders":["content-type"],"MaxAge":86400}'
```

If you later add a custom domain, include both:

```bash
--cors '{"AllowOrigins":["https://<project>.pages.dev","https://playground.example.com"],...}'
```

This does **not** affect direct `curl` testing — the Function URL is still
publicly invokable. CORS only restricts which browser origins can issue the
request. Real abuse control comes from the Lambda's reserved concurrency
cap (10) and the 10s subprocess timeout.

### 7. Verify the deploy

Open the production URL in a browser:

1. Tab favicon should show the Vite logo, title "Code Playground".
2. Editor loads with the C++ starter code.
3. Click **Run Code** with `Developer` in stdin → output panel shows
   `Hello Developer!` with a green ✓ "Finished" status badge.
4. Switch to Python, then TypeScript, then Java — each should produce the
   same output.
5. Network tab → confirm the `POST` to the Lambda Function URL returns
   `200 {"output": "Hello Developer!\n"}`.

## Updating the deployed site

Push to `main` → Cloudflare Pages picks up the webhook within seconds →
build runs → deploy goes live. Total time: ~60 s.

```bash
# Local
git push origin main
# Watch the build in the Pages dashboard, or just refresh the production
# URL after ~90 seconds.
```

To **roll back**, go to the Pages dashboard → Deployments → click any
previous successful build → **Rollback to this deployment**. Production
repoints in seconds; no rebuild needed (deploys are immutable artifacts).

## Cost

Within Cloudflare Pages' always-free tier:

- 500 builds/month — would require >16 pushes/day to exhaust.
- Unlimited bandwidth and requests.
- Unlimited sites, unlimited preview URLs.

The Lambda backend has its own free tier (1 M requests/mo + 400,000
GB-seconds compute). At reserved concurrency 10 with a 10s execution
ceiling, the worst-case bill is bounded — see `../code-lambda/deploy.md`.

**Realistic monthly cost for personal use: $0.00.**

## Common deploy failures

1. **`VITE_LAMBDA_URL` is empty in production** — the env var wasn't set in
   the Pages dashboard before the build, or was set on the Preview environment
   instead of Production. The app will render a `Configuration Error` status
   on Run Code. Fix: set the variable, re-trigger the build.

2. **Build fails with `npm ERR! code ENOENT` on `cd code-editor`** — the
   build command is missing the `cd` prefix, or the Output directory is set
   to `dist` instead of `code-editor/dist`. Fix: re-check the build settings.

3. **CORS errors in browser console after Step 6** — the AllowOrigins value
   was updated but the browser cached a preflight. Fix: hard-refresh (Cmd-Shift-R),
   or wait `MaxAge` seconds (86400 = 24 hours by default).

4. **Lambda 403 from the Pages site but 200 from `curl`** — almost always
   the CORS issue from #3. The Lambda itself is fine; the browser is being
   refused the preflight.

## Not yet wired up

- **Custom domain** — Pages → Custom domains → add a CNAME to your DNS.
  Free; Cloudflare handles ACM-equivalent cert provisioning automatically.
- **Cloudflare Web Analytics** — free, privacy-friendly. Pages → Analytics →
  Enable. Adds a single small script tag to the site.
- **Branch deploy previews** — already enabled by default. Each non-`main`
  branch gets `<branch-name>.<project>.pages.dev`.

# Serverless Code Runner — System Design

**Live:** <https://runbox.pages.dev/>

> Dev setup and deployment steps live in [Development Setup](#development-setup) and [Deployment](#deployment), automated by [`deploy.sh`](deploy.sh).

## Architecture Overview

A synchronous, single-Lambda execution engine optimised for zero-maintenance, low latency, and strict cost control.

| Component | Technology | Responsibility |
| :--- | :--- | :--- |
| **Editor** | React + Monaco Editor | UI, payload construction, HTTP fetch with AbortController |
| **Runner** | AWS Lambda (Python orchestrator) via Function URL | Payload validation, subprocess sandboxing, output formatting. Executes user code in **C++, Java, or Python**. |
| **Heater** | Amazon EventBridge (cron) | Pings Lambda every 5 min with `{"is_warmup": true}` to prevent cold starts |

**Network topology:** Lambda runs inside a VPC with no NAT gateway. All outbound calls from user code hang until the 10s subprocess timeout kills them — no data exfiltration possible. EventBridge invokes via Function URL inbound (public HTTPS), so the warmer is unaffected. Add a CloudWatch Logs VPC endpoint from the start to preserve observability.

---

## The 10 / 20 / 30 Cascading Timeout Strategy

Each layer covers the failure mode of the one inside it.

| Limit | Enforced By | Behaviour |
| :--- | :--- | :--- |
| **10s** | `subprocess.run(timeout=10)` | User code forcefully killed. Returns `ERROR_TLE`. |
| **20s** | Lambda configuration timeout | 10s buffer for the orchestrator to clean up and return HTTP response. |
| **30s** | React `AbortController` | Accounts for cold-start + 10s execution + network transit. UI resets gracefully instead of freezing. |

---

## Execution Limits & Sandboxing

| Limit | Mechanism | Notes |
| :--- | :--- | :--- |
| **Memory — 512MB** | Python `resource.setrlimit(RLIMIT_AS)`; Java `-Xmx`; C++ ASan `hard_rss_limit_mb` | Each runtime caps itself at 512MB and surfaces `ERROR_MLE` (`MemoryError` / `OutOfMemoryError`). `RLIMIT_AS` caps virtual address space, not RSS — test with realistic workloads as shared library mappings count toward the limit. **C++ is the exception:** ASan reserves ~8GB of virtual space, so a virtual cap (`RLIMIT_AS`) can't be applied. Instead ASan's own *RSS-based* limiter (`ASAN_OPTIONS=hard_rss_limit_mb=512`) caps resident memory at 512MB and aborts with `hard rss limit exhausted` on breach. Because a monitor thread polls RSS, the kill can overshoot slightly; the cgroup OOM-killer `SIGKILL` (returncode `-9`, not from a timeout) remains the backstop for allocation bursts faster than the poll interval — both map to `ERROR_MLE`. |
| **Payload — 128KB each** | Handler validation in `lambda.py` | `code` and `stdin` are type-checked and size-capped before anything is compiled or run. Non-object payloads and non-string fields are rejected with `400`. |
| **Output — 4KB** | `stdout`/`stderr` written to `/tmp`, first 4096 bytes read back | Prevents `while True: print()` memory exhaustion. |
| **Network — none** | VPC with no NAT gateway | All outbound connections time out at 10s subprocess limit. |
| **Concurrency** | Lambda Reserved Concurrency (opt-in) | Hard cap on simultaneous executions — primary abuse cost control. Commented out in `template.yaml`; enable it (e.g. `10`) once the account has 100+ unreserved executions of headroom. |

**Temp file cleanup:** All execution files are created inside a unique `tempfile.mkdtemp()` directory per invocation and wiped with `shutil.rmtree()` in a `finally` block — catches everything the subprocess writes, not just the primary file.

---

## Edge Cases & Design Decisions

**API Gateway 29s drop**
API Gateway hard-drops connections at 29s, causing `504` errors even when the backend is healthy. Skipped entirely in favour of Lambda Function URLs, which support connections up to 15 minutes natively. Trade-off: no built-in rate limiting — mitigated by Reserved Concurrency cap.

**Zombie Lambdas / double billing**
A proxy architecture (Server Lambda → Execution Lambda) bills for two Lambdas simultaneously. Consolidated into a single Lambda that receives the Function URL request directly. Zero idle compute.

**Warm-start data leaks**
Lambda reuses containers across invocations. All state is scoped to `lambda_handler` local scope. Temp directory is wiped in `finally` before returning — User B cannot read User A's artifacts.

**UX during long executions**
A 10s+ synchronous wait feels like a crashed tab. The Run button disables on click and a dynamic timer (`Running: 1s… 2s…`) mounts immediately to confirm the connection is alive.

---

## Warmer Behaviour & Concurrency

The EventBridge warmer keeps **one** container pre-initialised. Because executions can run up to 10s, the overlap window where a second simultaneous user triggers a cold start is wide — wider than for a typical low-latency API.

To keep multiple containers warm cheaply, send 2–3 concurrent warmup pings from EventBridge in parallel. Cost is negligible since warmup payloads return immediately.

---

## Known Limitations (Post-MVP)

- **Additional runtimes:** Beyond the three supported languages (C++, Java, Python), new runtimes must be bundled into the container image. Lambda has a 10GB image limit, so several more can be added without restructuring.
- **No queue:** At Reserved Concurrency cap, excess requests get throttle errors immediately with no retry. Acceptable at low traffic; add an SQS queue when concurrency becomes a concern.
- **No auth on Function URL:** Reserved Concurrency (opt-in, see `template.yaml`) is the only abuse control. A HMAC token or Cloudflare Turnstile would meaningfully reduce the attack surface.

---

## Development Setup

Prerequisites: Node.js 20+, Python 3.12+, Docker (for Lambda tests), AWS CLI + SAM CLI (for backend deploys).

```bash
cd editor
npm install
cp .env.example .env.local   # then set VITE_LAMBDA_URL
npm run dev                  # Vite dev server on http://localhost:5173
```

Point the editor at a backend by setting `VITE_LAMBDA_URL` in `editor/.env.local` — either your deployed Function URL or a local container:

```bash
# Local Lambda container (no AWS account needed):
docker build --platform linux/arm64 -t runbox-lambda lambda/
docker run --rm -p 9000:8080 runbox-lambda
```

### Testing

```bash
cd editor && npm run lint && npm run build   # static checks + prod build
./lambda-test/test.sh                        # full backend suite (builds image, runs 3 suites)
cd editor && npm run test:e2e                # Playwright e2e against the URL in .env.local
```

---

## Deployment

One script deploys both halves: the Lambda first, then the editor built against the freshly deployed Function URL.

```bash
./deploy.sh    # sam build + deploy, then Vite build + Cloudflare Pages upload
```

One-time setup before the first deploy: authenticate wrangler (`npx wrangler login`, or set `CLOUDFLARE_API_TOKEN`). If the Pages project doesn't exist yet, create it with `npx wrangler pages project create runbox --production-branch=main` — skip this if you already have one.

Backend config lives in `lambda/samconfig.toml` (stack `runbox-lambda`, region `ap-south-1`); the Pages project name comes from `PAGES_PROJECT` (default `runbox`). After the first deploy, tighten CORS by redeploying with your frontend origin:

```bash
./deploy.sh "https://runbox.pages.dev,http://localhost:5173"
```

Roll back the frontend via the Cloudflare dashboard → Deployments → previous build → **Rollback**.

### Warmer

Included in the stack: `template.yaml` defines an EventBridge Scheduler rule that invokes the Lambda every 5 minutes with `{"is_warmup": true}`, which the handler short-circuits. Keeps one container initialised — see [Warmer Behaviour & Concurrency](#warmer-behaviour--concurrency).
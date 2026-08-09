# RunBox Editor

React + Vite + Monaco frontend for the serverless code runner. See the
[root README](../README.md) for the system design and full setup steps.

## Quick start

```bash
npm install
cp .env.example .env.local   # then set VITE_LAMBDA_URL
npm run dev                  # http://localhost:5173
```

Set `VITE_LAMBDA_URL` in `.env.local` to your deployed Function URL (or a
local Lambda container — see the root README).

## Scripts

| Command | What it does |
| :--- | :--- |
| `npm run dev` | Vite dev server with HMR |
| `npm run lint` | ESLint over the whole package |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run test:e2e` | Playwright e2e (starts the dev server, hits the real Lambda) |

## Layout

```
src/
  App.jsx            # top-level state: per-language code buffers, layout
  constants.js       # languages, error-code → label map, Lambda URL
  starterCode.js     # per-language starter snippets
  hooks/
    useCodeRunner.js # fetch → { status, runtime, stdout, error } mapping
    useTheme.js      # OS-synced dark/light theme
  components/        # Header, CodeEditor, OutputPanel, StdinPanel, SaveModal, LanguageDropdown
tests/e2e.spec.js    # Playwright suite
```

Deployment: [`deploy.md`](deploy.md) or `../deploy.sh`.

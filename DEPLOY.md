# Deploying Margadrishti

Two deployables:

1. **Frontend** — a static Vite SPA (`frontend/`) → any static host (Vercel / Netlify / Cloudflare Pages).
2. **API** — FastAPI serving the reproducible **gold tier** (Parquet/DuckDB), no PostGIS/Redis/ETL
   required → any container host.

The full production runtime (PostGIS + Martin tiles + Celery worker/scheduler) is available via
`docker-compose.yml`, but the demo/Product-Link deploy uses the lean offline path below.

---

## 1. API (offline / gold tier)

The API reads the gold artifacts (`backend/data/gold/*.parquet` + `manifest.json`) at runtime.
These are **gitignored build outputs**, so a bare git checkout has none — the serving image bakes
them in. Build it **locally** (where gold exists; produce it with `cd backend && make worker` if needed):

```bash
cd backend
docker build -f Dockerfile.serve -t margadrishti-api .
```

Run it with the secrets/config as **runtime env vars** (never baked into the image):

```bash
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e MARGA_COPILOT_LLM_ENABLED=true \
  -e MARGA_COPILOT_MAX_PER_SESSION=10 \
  -e MARGA_COPILOT_MAX_PER_DAY=200 \
  -e MARGA_CORS_ORIGINS=https://<your-frontend-domain> \
  margadrishti-api
```

Deploy that image to a container host (e.g. **Fly.io** — `fly deploy` builds from the local
context so the local gold is included; or push the image to a registry and run it on Render /
Railway / a VM). Set the same env vars in the host's dashboard.

Health checks: `GET /health` (store mode + versions) and `GET /ready` (503 until serving data is
queryable) — wire `/ready` as the host's readiness probe.

### Required / recommended env

| Var | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Live copilot key — **host env var only**, never committed/baked |
| `MARGA_COPILOT_LLM_ENABLED` | `true` to enable the live copilot (off ⇒ deterministic built-in answers) |
| `MARGA_COPILOT_MAX_PER_SESSION` / `_PER_DAY` | Spend caps (default 10 / 200); on exceed → built-in fallback |
| `CLAUDE_MODEL_FAST` | Copilot model (default `claude-sonnet-4-6`) |
| `MARGA_CORS_ORIGINS` | Comma-separated allowed frontend origin(s) |
| `MARGA_OFFLINE` | `true` (default in the serve image) — gold tier, no DB |

> The `/copilot` endpoint is unauthenticated; the spend caps are what make it safe to expose
> publicly. Keep them set, and fund the Anthropic key for live answers (otherwise it degrades to
> the grounded built-in answer).

## 2. Frontend (static SPA)

Set the API origin and build:

```bash
cd frontend
echo "VITE_API_URL=https://<your-api-domain>" > .env.production   # or set in the host build env
npm ci && npm run build       # outputs dist/
```

Deploy `frontend/dist/` (Vercel/Netlify/Cloudflare Pages auto-detect Vite — build `npm run build`,
output `dist`). After the frontend domain is known, add it to the API's `MARGA_CORS_ORIGINS` and
redeploy the API.

---

## Never deploy / never commit
`.env`, the API key, raw CSVs, `data/_restricted` (PII), `data/bronze|silver|cache`, `*.parquet`,
`*.graphml`. The `.gitignore` and `backend/.dockerignore` enforce this — keep it that way.

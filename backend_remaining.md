# Margadrishti — Remaining Backend Work

Status as of the production-hardening pass. The offline/CI tier is verified (27 tests).
The container path is blocker-fixed and statically validated but **not yet executed
end-to-end** (no Docker in the build sandbox). Items below are the open work, by severity.

---

## 0. Validate the production runtime (must run on a Docker host)
The PostGIS / Celery / Martin path has never run live. After `docker compose up --build`:
- [ ] Confirm `bootstrap` completes (ETL → train → publish) and exits 0.
- [ ] `GET :8000/health` returns versions; `GET :3000/catalog` lists `tiles_cii`.
- [ ] Confirm `publish_all` loads all tables (segments_dim geometry, cii, predictions, …).
- [ ] Add a **gated PostGIS integration test** (skipped unless `POSTGIS_DSN` reachable) that
      runs `publish_all` against a throwaway DB and exercises `PostgisRepository`.
- [ ] Add a **Docker build job to CI** so the image build can't regress.

---

## 1. Authentication & authorization (blocker for multi-role deployment)
RLS is now *enforceable* (non-owner `margadrishti_api` role, `security_invoker` tiles view) but
not *complete*:
- [ ] **OIDC/JWT auth** on the API (command vs zone-inspector vs field-constable roles).
- [ ] Build **`MargadrishtiService` per request** with the caller's authenticated scopes
      (the current `lru_cache` singleton in `api/deps.py` can't carry per-request identity).
- [ ] **Fail-closed RLS**: unset/empty `margadrishti.zone_scope` must return *no* rows; the API
      sets the scope from the verified token. Today the policy is fail-open.
- [ ] **Command vs field role split**; field surfaces only ever see their jurisdiction.
- [ ] **Tiles**: serve field-scoped tiles behind an authenticated proxy (or per-zone source);
      Martin currently connects as owner and shows all zones (acceptable only for command).
- [ ] **Copilot**: it is unauthenticated. The LLM path is gated OFF by default
      (`MARGA_COPILOT_LLM_ENABLED`); before enabling, add auth + rate limiting + per-key
      budget so the Anthropic key can't be drained.

---

## 2. Reproducibility & data
- [ ] Replace live **Overpass** graph download with a pinned **Geofabrik** extract (via
      `pyrosm`) so `road_network_version` is truly reproducible and first-run is robust.
- [ ] Run and commit the **full-city** ETL manifest as the canonical artifact (set
      `MARGA_ETL_BBOX=""`); validate runtime/memory at city scale before claiming it.
- [ ] Pin image **@sha256 digests** + add a Python **lockfile** (uv/pip-tools) for frozen builds.

---

## 3. Optimiser realism (retire the "priority utility" caveat)
- [ ] Police-station **depots** instead of a virtual zone centroid.
- [ ] **Road-network travel times** (OSRM/Valhalla matrix) instead of straight-line haversine.
- [ ] Only then may outputs move from "priority utility" toward measured impact, and only
      with a matched pre/post study.

---

## 4. CII completeness (currently honest TODOs, not pitched as live)
- [ ] `poi_proximity` — metro/market/junction nearness component.
- [ ] `incident_overlap` — co-located ASTraM incident component.
- [ ] Re-weight + re-validate once both land (bump `CII_VERSION`).

---

## 5. Model frontier (all behind the existing dual gate)
- [ ] **ST-GNN** (PyTorch Geometric) — most aligned upgrade; models road-network spillover.
      Attempt only after the full-city graph + eval pipeline are stable.
- [ ] **TabPFN-TS** — experimental rung for sparse covariate-informed ranking.
- [ ] TimesFM / Chronos — zero-shot numeric baselines; lower priority (target mismatch).
- Note: LightGBM currently does NOT beat the recency baseline on rolling-origin → the
  recency fallback ships. Any new rung must beat **both** rolling-origin and held-out-zone.

---

## 6. Ops & observability
- [ ] Structured logging + request IDs; lock CORS to the frontend origin.
- [ ] API healthcheck in compose; readiness vs liveness.
- [ ] Job/queue dashboards (Flower for Celery); alert on failed pipeline runs.
- [ ] Backups/retention for PostGIS; retention windows for `jobs.jsonl` audit log.

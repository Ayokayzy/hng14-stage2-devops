# FIXES

Lean log of application fixes while preparing for containerization. Format: **file**, **lines** (current file after fixes), **problem**, **change**.

---

### `api/main.py`, `worker/worker.py`, `frontend/app.js` — see lines under each file below

**Problem:** Redis was aimed at `localhost` and the frontend at `http://localhost:8000` in code. Inside Docker each service has its own network namespace, so `localhost` is not the Redis or API container.

**Change:** Drive targets from env: **`REDIS_HOST`**, **`REDIS_PORT`** (api + worker) and **`API_URL`** (frontend), with `.env` / process env loaded where shown below. In Compose, set e.g. `REDIS_HOST=redis`, `API_URL=http://api:8000`.

---

### `api/main.py` — lines 11–13

**Problem:** `redis.Redis(host=os.getenv("REDIS_HOST"), port=os.getenv("REDIS_PORT"))` passed `None` when variables were unset, and passed `REDIS_PORT` as a string. Missing env broke Redis silently or with unclear client errors; wrong type risked subtle bugs.

**Change:** Read `REDIS_HOST` / `REDIS_PORT` with defaults `localhost` and `6379`, coerce port with `int(...)`, then construct the client from those values.

---

### `api/requirements.txt` — line 5

**Problem:** `from dotenv import load_dotenv` (line 5 in `main.py`) required `python-dotenv`, but it was not listed. Fresh `pip install -r requirements.txt` raised `ModuleNotFoundError: No module named 'dotenv'`.

**Change:** Added `python-dotenv`.

---

### `worker/worker.py` — lines 8–10 (plus imports lines 1–6)

**Problem:** Same as API: bare `os.getenv(...)` for Redis could be `None`; `REDIS_PORT` was not coerced to `int`. `import signal` was unused. `import dotenv` + `dotenv.config()` depended on `python-dotenv` without declaring it in `worker/requirements.txt`.

**Change:** Removed `signal`. Switched to `from dotenv import load_dotenv` / `load_dotenv()`. Applied the same default host, default port, and `int(...)` pattern as the API for the Redis client.

---

### `worker/requirements.txt` — line 2

**Problem:** Worker loaded `.env` via dotenv but `python-dotenv` was not in requirements (same install failure as API).

**Change:** Added `python-dotenv`.

---

### `frontend/app.js` — line 8

**Problem:** `const API_URL = process.env.API_URL` was `undefined` when `API_URL` was not set (common in minimal local runs). Requests became `undefined/jobs` and failed opaquely.

**Change:** `const API_URL = process.env.API_URL ?? "http://localhost:8000"` so local dev matches prior behavior; set `API_URL` in Compose/K8s to `http://api:8000` (or your real API base) for containers.

---

### `frontend/package.json` — line 11

**Problem:** `require('dotenv')` in `app.js` line 4 had no matching dependency; `npm install` did not install `dotenv`, causing `Cannot find module 'dotenv'`.

**Change:** Added `"dotenv": "^16.4.5"` to `dependencies`.

---

## Not fixed here (for later infra / security work)

- **Redis auth:** `.env` may define `REDIS_PASSWORD`; the app does not pass a password into `redis.Redis`. Wiring password + TLS belongs with hardened Redis deployment.
- **`.env` in images:** Prefer injecting env at runtime; do not bake secrets into images.

---

## Containerization (Docker / Compose)

### `frontend/app.js` — lines 8–10, 33–35

**Problem:** `app.listen(3000)` listened on default host; in containers the process must bind explicitly to `0.0.0.0` so published ports reach the app. Port was not configurable for Compose or health probes.

**Change:** Read `HOST` (default `0.0.0.0`) and `PORT` (default `3000`) from the environment and call `app.listen(PORT, HOST, …)`.

---

### `api/Dockerfile` (new)

**Change:** Multi-stage build: builder creates `/opt/venv` and installs `requirements.txt`; runtime stage copies only the venv + `main.py`, runs as non-root `appuser` (uid 1000), `chown` on `/opt/venv` and `/app`, `HEALTHCHECK` hits `/openapi.json` on `127.0.0.1` using `UVICORN_PORT` (default `8000`), `CMD` runs uvicorn on `0.0.0.0`. No `.env` or secrets copied (see `api/.dockerignore`).

---

### `worker/Dockerfile` (new)

**Change:** Same venv pattern as API; non-root `worker` (uid 1000); `HEALTHCHECK` runs a short Python `redis.ping()` using `REDIS_HOST` / `REDIS_PORT` from the container environment; `CMD` runs `python -u worker.py`. No secrets copied (see `worker/.dockerignore`).

---

### `frontend/Dockerfile` (new)

**Change:** Multi-stage: `deps` runs `npm ci --omit=dev` from `package.json` + `package-lock.json`; `runtime` copies only production `node_modules` and app files, runs as non-root `nodejs` (uid 1000), sets `NODE_ENV=production`, `HEALTHCHECK` uses Node’s HTTP client against `127.0.0.1:$PORT`. No `.env` copied (see `frontend/.dockerignore`).

---

### `docker-compose.yml` (new)

**Change:** Single internal bridge network named via `${COMPOSE_INTERNAL_NETWORK_NAME}`. Redis has **no** `ports:` mapping (not exposed on the host). `api` / `worker` use `depends_on: redis: condition: service_healthy`; `frontend` uses `depends_on: api: condition: service_healthy`. All images, build paths, published port mappings, resource limits, Redis connection values, listen addresses, and `API_URL` are **only** `${VAR}` substitutions (see `env.docker.example`). **Exception:** Redis `healthcheck.test` remains `["CMD", "redis-cli", "ping"]` because Compose cannot express that probe array purely from a single env substitution.

---

### `env.docker.example` (new)

**Change:** Documents every variable required for `docker compose` substitution; copy to `.env` at repo root before `docker compose up`.

---

### `.gitignore` (new)

**Change:** Ignore root `.env` so Compose substitution files with local overrides are not committed by mistake.

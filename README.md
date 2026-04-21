# hng14-stage2-devops

[![CI/CD Pipeline](https://github.com/chukwukelu2023/hng14-stage2-devops/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/chukwukelu2023/hng14-stage2-devops/actions/workflows/ci-cd.yml)

Job dashboard with a **FastAPI** API, **Express** frontend, **Python** worker, and **Redis** queue — runnable entirely in **Docker** so you do **not** need Python, Node, or Redis installed on your laptop.

## Prerequisites

You only need **Docker** with the **Compose** plugin (Docker Desktop includes both).

| OS | What to install |
|----|------------------|
| **macOS** | [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/) |
| **Windows** | [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/) (WSL 2 backend recommended) |
| **Linux** | [Docker Engine](https://docs.docker.com/engine/install/) + [Docker Compose plugin](https://docs.docker.com/compose/install/linux/) |

After installation, confirm in a terminal:

```bash
docker --version
docker compose version
```

Start **Docker Desktop** (macOS/Windows) or the Docker daemon (Linux) before running Compose.

**You do not need Redis on the host.** Redis runs inside Compose on an internal network and is not published to your machine’s ports.

## Quick start (containers)

1. **Clone** this repository and go to the project root (where `docker-compose.yml` lives).

2. **Create your Compose environment file** (Compose reads a file named `.env` in the same directory as `docker-compose.yml` for variable substitution):

   ```bash
   cp env.docker.example .env
   ```

   Edit `.env` only if you need to change host ports or resource limits. Defaults map **API** to host `8000` and **frontend** to host `3000`.

3. **Build and start** all services:

   ```bash
   docker compose up --build
   ```

   Wait until logs show the frontend listening and no services restarting in a loop. The stack waits for **Redis** and the **API** health checks before starting dependents.

4. **Open the app** in a browser:

   - **UI:** [http://localhost:3000](http://localhost:3000)  
     (or the host port you set in `FRONTEND_HOST_PORT_MAPPING`, e.g. `3000:3000` → `localhost:3000`)

5. **Optional — API docs (FastAPI):**  
   [http://localhost:8000/docs](http://localhost:8000/docs)  
   (host side of `API_HOST_PORT_MAPPING`, default `8000:8000`)

To run in the background:

```bash
docker compose up --build -d
```

Stop everything:

```bash
docker compose down
```

## How to test that it works

1. Open **http://localhost:3000**.
2. Click **Submit New Job**.
3. You should see a job id and status moving from **queued** to **completed** (the worker updates Redis).

**API-only check (optional):**

```bash
curl -s -X POST http://localhost:8000/jobs
```

You should get JSON with a `job_id`. Then:

```bash
curl -s http://localhost:8000/jobs/<job_id>
```

Replace `<job_id>` with the value from the previous response; `status` should become `completed` after a few seconds if the worker is running.

## Architecture (short)

- **frontend** (port 3000 on host by default): browser → Express; server calls **api** using `API_URL` (inside Compose this is `http://api:8000`).
- **api** (port 8000 on host by default): enqueues jobs in **Redis**.
- **worker**: consumes the queue and sets job status in Redis.
- **redis**: internal only — not exposed on the host.

## Troubleshooting

| Issue | What to try |
|--------|-------------|
| `docker: command not found` | Install Docker and restart the terminal; ensure Docker Desktop is running. |
| Port already in use | Change `API_HOST_PORT_MAPPING` and/or `FRONTEND_HOST_PORT_MAPPING` in `.env` (e.g. `8080:8000` and `8081:3000`). If you change the API **container** port, also update `API_CONTAINER_PORT` and `API_URL` consistently. |
| Services keep restarting | `docker compose logs` (or `docker compose logs api worker redis`) for errors. |
| Slow first `up` | First build pulls base images and installs dependencies; later runs are faster. |

## More detail on fixes and container design

See [FIXES.md](FIXES.md) for application and Docker-related changes and caveats.

## CI/CD pipeline

The project includes a GitHub Actions workflow at `.github/workflows/ci-cd.yml` running on
`ubuntu-latest` with strict stage order:

1. `lint`
2. `test`
3. `build`
4. `security_scan`
5. `integration_test`
6. `deploy` (only for `push` to `main`)

If any stage fails, downstream stages are blocked by `needs`.

For an engineering deep dive of every stage and command, see [CI_CD_WORKFLOW_EXPLAINED.md](CI_CD_WORKFLOW_EXPLAINED.md).

### Stage details

- **Lint**
  - Python: `flake8` on `api` and `worker`
  - JavaScript: `eslint` on `frontend/app.js`
  - Dockerfiles: `hadolint` on all three service Dockerfiles

- **Test**
  - Runs API unit tests with `pytest`
  - Redis is mocked in tests (no external Redis needed)
  - Produces and uploads `coverage.xml` as `api-coverage-report`

- **Build**
  - Builds `api`, `worker`, and `frontend` images
  - Tags each image with `${GITHUB_SHA}` and `latest`
  - Pushes both tags to a local in-job registry service (`registry:2` on `localhost:5000`)
  - Uploads gzipped image archives for downstream jobs

- **Security scan**
  - Scans all three images with Trivy
  - Fails on `CRITICAL` vulnerabilities
  - Uploads SARIF files as `trivy-sarif-reports`

- **Integration test**
  - Starts the full stack with Docker Compose
  - Submits a job through frontend endpoint `/submit`
  - Polls `/status/:id` until status is `completed`
  - Always tears down with `docker compose down -v --remove-orphans`

- **Deploy**
  - Runs only on `main` pushes
  - Performs a scripted rolling update:
    - start new container
    - wait up to 60 seconds for health check
    - stop old container only after new container is healthy
  - On health-check timeout, deploy aborts and old container remains running

### Troubleshooting CI

- If lint fails, run local checks:
  - `flake8 api worker`
  - `cd frontend && npx eslint app.js`
- If integration test fails, inspect compose logs:
  - `docker compose --env-file env.docker.example logs`
- If Trivy fails, inspect SARIF artifact from the workflow run and patch dependencies/base images.

### Workflow artifacts

- `api-coverage-report`: contains `coverage.xml` from API unit tests.
- `built-image-archives`: gzip-compressed Docker image archives used across build/scan/deploy jobs.
- `trivy-sarif-reports`: SARIF scan reports for `api`, `worker`, and `frontend` images.

### Required GitHub Actions configuration

The deploy job expects the following repository-level settings:

- **Variable:** `IMAGE_BASE`  
  Docker image repository used for deploy promotion (for example: `ghcr.io/<owner>/hng14-stage2-devops/frontend`).

- **Secret:** `DEPLOY_API_URL`  
  Runtime API base URL injected into deployed frontend container (for example: `https://api.example.com`).

If either value is missing, the deploy stage exits early with a clear error message.

### How to set GitHub variable and secret

#### Set a repository variable (`IMAGE_BASE`)
1. Open your repo on GitHub.
2. Go to **Settings**.
3. In the left sidebar, go to **Secrets and variables** -> **Actions**.
4. Open the **Variables** tab.
5. Click **New repository variable**.
6. Set:
   - **Name:** `IMAGE_BASE`
   - **Value:** e.g. `ghcr.io/ayokayzy/hng14-stage2-devops/frontend`
7. Save.

#### Set a repository secret (`DEPLOY_API_URL`)
1. In the same area: **Settings** -> **Secrets and variables** -> **Actions**.
2. Open the **Secrets** tab.
3. Click **New repository secret**.
4. Set:
   - **Name:** `DEPLOY_API_URL`
   - **Secret:** e.g. `https://api.example.com`
5. Save.

#### How the workflow reads them
- Variable: `${{ vars.IMAGE_BASE }}`
- Secret: `${{ secrets.DEPLOY_API_URL }}`

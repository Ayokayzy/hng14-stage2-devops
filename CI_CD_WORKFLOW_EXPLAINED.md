# CI/CD Workflow Explained

This document explains `.github/workflows/ci-cd.yml` in engineering terms so you can safely modify it as the application grows.

## High-level design

The workflow is intentionally **gated**. Jobs run in this exact order:

1. `lint`
2. `test`
3. `build`
4. `security_scan`
5. `integration_test`
6. `deploy` (main branch pushes only)

The order is enforced with `needs`, so a failure in one stage blocks everything after it.

## Trigger behavior

```yaml
on:
  push:
    branches:
      - "**"
  pull_request:
```

- Every push to any branch triggers CI.
- Pull requests also trigger CI.
- Deploy is still protected by a job-level `if` condition (see deploy section).

## Job-by-job breakdown

## 1) `lint` job

Purpose: fail fast on code quality and Dockerfile hygiene.

### Commands and actions

- `actions/checkout@v4`: checks out repository source.
- `actions/setup-python@v5` with Python 3.12: standardizes interpreter version.
- `pip install -r requirements-dev.txt -r api/requirements.txt -r worker/requirements.txt`: installs lint tooling and Python deps.
- `flake8 api worker`: lints Python services.
- `actions/setup-node@v4` with Node 20: standardizes Node runtime.
- `npm install` (in `frontend`): installs frontend dependencies.
- `npx eslint app.js`: lints frontend entrypoint.
- `docker run --rm -i hadolint/hadolint < <Dockerfile>`: lints each service Dockerfile.

### Decision rationale

- Putting all linting in one early gate prevents costly downstream image builds for style issues.
- Hadolint runs in a container to avoid host dependency setup on the runner.

## 2) `test` job

Purpose: validate API behavior with unit tests and record coverage.

### Commands and actions

- Installs Python + test dependencies.
- Runs:
  - `pytest tests -q --cov=. --cov-report=xml:coverage.xml` (inside `api`)
- Uploads artifact:
  - `api-coverage-report` from `api/coverage.xml`

### Decision rationale

- Tests are isolated from Redis via mocks, so unit tests stay deterministic and fast.
- Coverage XML artifact supports later quality dashboards or enforcement.

## 3) `build` job

Purpose: build all service images once, tag consistently, and make them available to later jobs.

### Service container

```yaml
services:
  registry:
    image: registry:2
    ports:
      - 5000:5000
```

This creates an in-job local Docker registry.

### Commands

- Build loop:
  - `docker build -t <image>:${GITHUB_SHA} -t <image>:latest ./<service>`
- Push loop:
  - pushes both SHA and `latest` tags to `localhost:5000`
- Archive loop:
  - `docker save ... | gzip > image-archives/<service>.tar.gz`
- Uploads artifact:
  - `built-image-archives`

### Decision rationale

- SHA tags are immutable for traceability.
- `latest` supports simple “current stable” use cases.
- Image archives are used because each GitHub Actions job has a fresh runner (no shared Docker daemon state).

## 4) `security_scan` job

Purpose: enforce vulnerability policy and keep machine-readable reports.

### Commands and actions

1. Download image archives artifact.
2. Load images with:
   - `gzip -dc ... | docker load`
3. For each image (`api`, `worker`, `frontend`):
   - **Table scan** (`format: table`, `exit-code: "1"`)
     - fails job on CRITICAL findings
     - shows clear CVEs in logs
   - **SARIF scan** (`format: sarif`, `exit-code: "0"`)
     - generates report artifact without adding extra failure mode
4. Upload SARIF files as `trivy-sarif-reports`.

### Important Trivy options

- `severity: CRITICAL`: policy threshold.
- `ignore-unfixed: true`: ignores vulnerabilities without available fixes.
- `scanners: vuln`: scans vulnerabilities only (avoids secret scanner noise in this stage).

### Decision rationale

- Split fail logic (table) from report generation (SARIF) makes debugging practical while preserving strict policy.

## 5) `integration_test` job

Purpose: prove the full stack works together, not just components in isolation.

### Commands

- Starts stack:
  - `docker compose --env-file env.docker.example up -d --build`
- Readiness gate:
  - waits for frontend (`http://localhost:3000/`) and API (`http://localhost:8000/openapi.json`)
- Scenario:
  - `POST /submit` via frontend
  - parse `job_id`
  - poll `GET /status/:id` until `completed` (timeout guarded)
- Cleanup (always):
  - `docker compose ... down -v --remove-orphans`

### Decision rationale

- Readiness checks prevent race-condition failures (“connection reset by peer” during startup).
- `if: always()` cleanup keeps runners clean and avoids false failures in later attempts.

## 6) `deploy` job

Purpose: perform a scripted rolling update with health-gated cutover.

### Condition

```yaml
if: github.event_name == 'push' && github.ref == 'refs/heads/main'
```

Deploy only runs for direct pushes to `main`.

### Commands

- Downloads and loads frontend image archive.
- Creates network and resets temp containers.
- Starts:
  - `frontend-old` on port 3000 using `latest`
  - `frontend-new` on port 3001 using `${GITHUB_SHA}`
- Health poll:
  - checks `docker inspect ... .State.Health.Status` for up to 60s.
- If unhealthy:
  - logs new container, removes it, exits non-zero
  - old container remains running.
- If healthy:
  - removes old container
  - starts promoted container (`frontend-new-prod`) on port 3000 using SHA image.

### Decision rationale

- Health-gated promotion prevents swapping traffic to a bad release.
- 60s bound keeps deployment deterministic and fast to fail.

## Environment variables and shell safety patterns

The workflow repeatedly uses:

- `set -euo pipefail`
  - `-e`: fail on command error
  - `-u`: fail on undefined variables
  - `-o pipefail`: fail when any command in a pipe fails

This reduces silent failures in loops and pipes.

## Artifacts produced

- `api-coverage-report`: test coverage XML.
- `built-image-archives`: gzip Docker archives for all services.
- `trivy-sarif-reports`: security reports for all services.

## Common scaling changes and where to edit

## Add a new microservice (example: `scheduler`)

Update these sections:

1. `build` loops: include `scheduler` in `for svc in ...`.
2. `security_scan`: add table + SARIF scan steps for scheduler image.
3. `integration_test`: include scheduler behavior in test scenario if required.
4. Compose file: ensure service is in `docker-compose.yml`.

## Tighten or relax security policy

Edit Trivy options in `security_scan`:

- `severity`: e.g., `HIGH,CRITICAL`
- `ignore-unfixed`: `false` if you want stricter enforcement
- `exit-code`: keep table scan as policy gate (`1`)

## Speed up CI

- Cache Python/npm dependencies with `actions/cache`.
- Parallelize image scans across a matrix.
- Keep integration test as a single deterministic smoke path.

## Move from demo deploy to real production deploy

Current deploy is runner-local and demonstrates rolling logic. For production:

- Replace with SSH/ECS/Kubernetes deployment target.
- Keep the same rule: new version must pass health check before old version is stopped.
- Preserve rollback behavior on timeout/failure.

## Operational caveats

- The local registry (`localhost:5000`) exists only in the build job context.
- Artifacts bridge job boundaries; removing them breaks downstream jobs.
- `latest` is mutable; production traceability should prefer immutable SHA tags.

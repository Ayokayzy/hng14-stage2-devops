#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ENV_FILE="${ENV_FILE:-env.docker.example}"
TIMEOUT_SECONDS="${INTEGRATION_TIMEOUT_SECONDS:-120}"

teardown() {
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" down -v --remove-orphans
}
trap teardown EXIT

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --build

timeout "${TIMEOUT_SECONDS}" bash -c '
  until curl -fsS http://localhost:3000/ >/dev/null && curl -fsS http://localhost:8000/openapi.json >/dev/null; do
    sleep 2
  done
'

submit_response="$(curl -sS -X POST http://localhost:3000/submit)"
echo "Submit response: ${submit_response}"
job_id="$(echo "${submit_response}" | python -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')"

timeout "${TIMEOUT_SECONDS}" bash -c '
  while true; do
    status_response="$(curl -sS "http://localhost:3000/status/'"${job_id}"'")"
    status="$(echo "${status_response}" | python -c "import json,sys; print(json.load(sys.stdin).get(\"status\",\"\"))")"
    echo "Current status: ${status}"
    if [ "${status}" = "completed" ]; then
      exit 0
    fi
    sleep 2
  done
'

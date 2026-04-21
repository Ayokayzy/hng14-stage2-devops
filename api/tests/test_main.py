from pathlib import Path
from unittest.mock import Mock
import importlib.util

from fastapi.testclient import TestClient


spec = importlib.util.spec_from_file_location(
    "main", Path(__file__).resolve().parents[1] / "main.py"
)
main = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(main)


client = TestClient(main.app)


def test_create_job_enqueues_and_sets_status(monkeypatch):
    mock_redis = Mock()
    monkeypatch.setattr(main, "r", mock_redis)

    response = client.post("/jobs")

    assert response.status_code == 200
    payload = response.json()
    assert "job_id" in payload
    mock_redis.lpush.assert_called_once_with("job", payload["job_id"])
    mock_redis.hset.assert_called_once_with(f"job:{payload['job_id']}", "status", "queued")


def test_get_job_returns_not_found_when_missing(monkeypatch):
    mock_redis = Mock()
    mock_redis.hget.return_value = None
    monkeypatch.setattr(main, "r", mock_redis)

    response = client.get("/jobs/unknown")

    assert response.status_code == 200
    assert response.json() == {"error": "not found"}
    mock_redis.hget.assert_called_once_with("job:unknown", "status")


def test_get_job_returns_decoded_status(monkeypatch):
    mock_redis = Mock()
    mock_redis.hget.return_value = b"completed"
    monkeypatch.setattr(main, "r", mock_redis)

    response = client.get("/jobs/job-123")

    assert response.status_code == 200
    assert response.json() == {"job_id": "job-123", "status": "completed"}
    mock_redis.hget.assert_called_once_with("job:job-123", "status")

from fastapi import FastAPI
import redis
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

_redis_host = os.getenv("REDIS_HOST", "localhost")
_redis_port = int(os.getenv("REDIS_PORT", "6379"))
r = redis.Redis(host=_redis_host, port=_redis_port)


@app.post("/jobs")
def create_job():
    job_id = str(uuid.uuid4())
    r.lpush("job", job_id)
    r.hset(f"job:{job_id}", "status", "queued")
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    status = r.hget(f"job:{job_id}", "status")
    if not status:
        return {"error": "not found"}
    return {"job_id": job_id, "status": status.decode()}

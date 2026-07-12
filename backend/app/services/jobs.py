from datetime import datetime
from threading import Thread
from uuid import uuid4


jobs: dict[str, dict] = {}


def create_job(label: str, target, *args, **kwargs) -> str:
    job_id = str(uuid4())
    jobs[job_id] = {
        "id": job_id,
        "label": label,
        "status": "RUNNING",
        "progress": 0,
        "message": "Starting",
        "created_at": datetime.utcnow().isoformat(),
        "result": None,
        "error": None,
    }

    def runner():
        try:
            result = target(job_id, *args, **kwargs)
            jobs[job_id]["status"] = "COMPLETED"
            jobs[job_id]["progress"] = 100
            jobs[job_id]["message"] = "Completed"
            jobs[job_id]["result"] = result
        except Exception as exc:
            jobs[job_id]["status"] = "FAILED"
            jobs[job_id]["error"] = str(exc)
            jobs[job_id]["message"] = "Failed"

    Thread(target=runner, daemon=True).start()
    return job_id


def update_job(job_id: str, progress: int, message: str):
    if job_id in jobs:
        jobs[job_id]["progress"] = progress
        jobs[job_id]["message"] = message


def get_job(job_id: str):
    return jobs.get(job_id)

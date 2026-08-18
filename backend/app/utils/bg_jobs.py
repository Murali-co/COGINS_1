import uuid
import threading
from typing import Dict, Any, Optional

jobs_lock = threading.Lock()
jobs_db: Dict[str, Dict[str, Any]] = {}

def create_job() -> str:
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs_db[job_id] = {
            "status": "pending",
            "result": None,
            "error": None
        }
    return job_id

def update_job(job_id: str, status: str, result: Any = None, error: Optional[str] = None):
    with jobs_lock:
        if job_id in jobs_db:
            jobs_db[job_id]["status"] = status
            if result is not None:
                jobs_db[job_id]["result"] = result
            if error is not None:
                jobs_db[job_id]["error"] = error

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with jobs_lock:
        return jobs_db.get(job_id)

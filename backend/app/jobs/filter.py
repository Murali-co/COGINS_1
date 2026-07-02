from typing import List, Dict, Any, Optional

class JobFilter:
    @staticmethod
    def filter_jobs(
        jobs: List[Dict[str, Any]],
        title: Optional[str] = None,
        location: Optional[str] = None,
        is_remote: Optional[bool] = None,
        job_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        filtered = []
        for job in jobs:
            # 1. Title Filter
            if title:
                title_keywords = [k.strip().lower() for k in title.split(",") if k.strip()]
                job_title_lower = job["title"].lower()
                job_desc_lower = job.get("description", "").lower()
                # Check if at least one keyword is in the job title or description
                if not any(kw in job_title_lower or kw in job_desc_lower for kw in title_keywords):
                    continue

            # 2. Location Filter — "Any" or empty means no restriction
            if location is not None:
                loc_lower = location.lower().strip()
                # "Any" means no location filter
                if loc_lower and loc_lower != "any":
                    job_loc_lower = job["location"].lower()
                    if loc_lower not in job_loc_lower:
                        # Special check: if user wants Remote, match remote/anywhere/wfh
                        if loc_lower == "remote" and ("remote" in job_loc_lower or "anywhere" in job_loc_lower):
                            pass
                        else:
                            continue

            # 3. Remote Filter (boolean)
            # Only filter out non-remote jobs if the user explicitly requested remote-only (is_remote=True)
            if is_remote:
                job_loc_lower = job["location"].lower()
                job_desc_lower = job.get("description", "").lower()
                job_is_remote = (
                    "remote" in job_loc_lower
                    or "anywhere" in job_loc_lower
                    or "work from home" in job_desc_lower
                    or "wfh" in job_desc_lower
                )

                if not job_is_remote:
                    continue

            # 4. Job Type Filter (remote / hybrid / onsite)
            if job_type and job_type.lower() not in ("any", "all", ""):
                requested_type = job_type.lower().replace("-", "").replace("_", "")  # "on-site" → "onsite"
                job_actual_type = job.get("job_type", "onsite").lower().replace("-", "").replace("_", "")
                if requested_type != job_actual_type:
                    continue

            filtered.append(job)
        return filtered

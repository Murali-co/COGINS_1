import pytest
from app.vector_db.profile_store import ProfileStore
from app.jobs.matcher import JobMatcher

def test_resume_tailoring_flow(client):
    # 1. Register & Login
    client.post("/auth/register", json={
        "email": "tailor_tester@test.com",
        "password": "password123",
        "full_name": "Tailor Tester"
    })
    login_res = client.post("/auth/login", json={
        "email": "tailor_tester@test.com",
        "password": "password123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Test without resume uploaded (Should fail with 400)
    tailor_res = client.post(
        "/resume/tailor",
        headers=headers,
        json={"job_id": "nonexistent-job-id"}
    )
    assert tailor_res.status_code == 400
    assert "upload a resume" in tailor_res.json()["detail"].lower()

    # 3. Save profile and test with missing job (Should fail with 404)
    me_res = client.get("/auth/me", headers=headers)
    user_id = me_res.json()["id"]
    ProfileStore.store_profile(
        user_id=user_id,
        resume_text="Senior Python developer with experience in FastAPI and SQL.",
        skills=["Python", "FastAPI", "SQL"]
    )

    tailor_res_missing_job = client.post(
        "/resume/tailor",
        headers=headers,
        json={"job_id": "nonexistent-job-id"}
    )
    assert tailor_res_missing_job.status_code == 404
    assert "not found" in tailor_res_missing_job.json()["detail"].lower()

    # 4. Upsert a dummy job and test success flow (Should return 200 with tailored response)
    JobMatcher.upsert_jobs([{
        "id": "matching-job-id",
        "title": "FastAPI Engineer",
        "company": "FastAPI Corp",
        "location": "Remote",
        "description": "Looking for a FastAPI developer experienced in building asynchronous REST APIs and SQL optimization.",
        "url": "http://example.com",
        "posted_at": "1 day ago",
        "source": "indeed"
    }])

    tailor_res_success = client.post(
        "/resume/tailor",
        headers=headers,
        json={"job_id": "matching-job-id"}
    )
    assert tailor_res_success.status_code == 200
    data = tailor_res_success.json()
    assert "tailored_resume" in data
    assert "keyword_changes" in data
    assert "ats_score_estimate" in data
    assert isinstance(data["ats_score_estimate"], int)
    assert isinstance(data["keyword_changes"], list)

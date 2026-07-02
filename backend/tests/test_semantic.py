import pytest
from app.vector_db.chroma_client import ChromaDBClient
from app.vector_db.profile_store import ProfileStore
from app.jobs.matcher import JobMatcher

def test_skills_seeding_and_query():
    # Seeding is triggered on startup, verify it counts > 0
    collection = ChromaDBClient.get_collection("skills")
    count = collection.count()
    assert count > 0

    # Query for Python or PyTorch semantically
    results = ChromaDBClient.query_skills("Python programming language", n_results=3)
    assert len(results) > 0
    skills_found = [r["metadata"]["skill"] for r in results]
    assert "Python" in skills_found

def test_query_profile_isolation():
    user_id_1 = 111
    user_id_2 = 222
    
    # Store profile for user 1
    ProfileStore.store_profile(
        user_id=user_id_1,
        resume_text="Senior Python developer with experience building Django apps.",
        skills=["Python", "Django"]
    )
    
    # Store profile for user 2
    ProfileStore.store_profile(
        user_id=user_id_2,
        resume_text="Graphics designer specialized in Adobe Photoshop.",
        skills=["Adobe Photoshop"]
    )

    # Query profile for user 1 asking about Python
    res_1 = ChromaDBClient.query_profile(user_id=user_id_1, query_text="Python Django", n_results=2)
    assert len(res_1) > 0
    # User 1 should match Django
    assert any("Django" in r["document"] or "Python" in r["document"] for r in res_1)
    
    # Query profile for user 2 with the same query - should return nothing relevant because of user isolation!
    res_2 = ChromaDBClient.query_profile(user_id=user_id_2, query_text="Python Django", n_results=2)
    # The document shouldn't contain django/python since user 2 doesn't have it
    assert not any("Django" in r["document"] or "Python" in r["document"] for r in res_2)
    
    # Cleanup profiles
    ProfileStore.delete_profile(user_id_1)
    ProfileStore.delete_profile(user_id_2)

def test_query_jobs():
    # Insert mock jobs
    mock_jobs = [
        {
            "id": "mock_job_1",
            "title": "Machine Learning Engineer",
            "company": "DeepMind",
            "location": "London",
            "description": "Research and construct neural network algorithms using PyTorch.",
            "url": "http://example.com/1",
            "posted_at": "1 hour ago",
            "source": "manual"
        },
        {
            "id": "mock_job_2",
            "title": "React Frontend Developer",
            "company": "Meta",
            "location": "Remote",
            "description": "Build high-performance web applications using React, HTML5, and CSS.",
            "url": "http://example.com/2",
            "posted_at": "2 hours ago",
            "source": "manual"
        }
    ]
    JobMatcher.upsert_jobs(mock_jobs)
    
    # Query jobs for deep learning
    results = ChromaDBClient.query_jobs("PyTorch neural network", n_results=1)
    assert len(results) == 1
    assert results[0]["id"] == "mock_job_1"
    assert "PyTorch" in results[0]["document"]

    # Query with metadata filter
    results_filtered = ChromaDBClient.query_jobs(
        "developer",
        n_results=2,
        where={"company": {"$eq": "Meta"}}
    )
    assert len(results_filtered) == 1
    assert results_filtered[0]["id"] == "mock_job_2"

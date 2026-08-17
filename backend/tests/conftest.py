import pytest
import os
import shutil
import sys
from unittest.mock import MagicMock

# Set mock environment variables before importing any app components
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-test-secret-key"
os.environ["DATABASE_URL"] = "sqlite:///./test_data/users.db"
os.environ["CHROMA_PATH"] = "./test_data/chroma_db"
os.environ["UPLOAD_DIR"] = "./test_uploads"
os.environ["TESTING"] = "true"
os.environ["ENVIRONMENT"] = "testing"

# Direct monkeypatch of embedding functions to ensure consistent behavior across all modules
def mock_embed_text(text: str):
    import hashlib
    # Deterministic hash of the text to perturb the vector slightly and avoid HNSW graph degeneracy
    h = hashlib.md5(text.encode("utf-8")).digest()
    vec = [float(b) / 256.0 * 0.01 for b in h]
    # Pad to 384 dimensions
    vec = vec + [0.0] * (384 - len(vec))
    
    text_lower = text.lower()
    if "python" in text_lower:
        vec[0] = 1.0
    if "pytorch" in text_lower or "machine learning" in text_lower or "neural network" in text_lower:
        vec[1] = 1.0
    if "react" in text_lower or "html5" in text_lower or "frontend" in text_lower:
        vec[2] = 1.0
    return vec

def mock_embed_batch(texts):
    return [mock_embed_text(t) for t in texts]

import app.vector_db.embedder
app.vector_db.embedder.embed_text = mock_embed_text
app.vector_db.embedder.embed_batch = mock_embed_batch

# Also mock chromadb's internal fallback embedding function to return the same vectors
import chromadb.utils.embedding_functions
class MockONNXMiniLM:
    def __init__(self, *args, **kwargs):
        pass
    def __call__(self, input):
        return [mock_embed_text(t) for t in input]

chromadb.utils.embedding_functions.ONNXMiniLM_L6_V2 = MockONNXMiniLM

# Mock OllamaClient to prevent calling localhost/external LLM during tests
from app.llm.ollama_client import OllamaClient
async def mock_generate(cls, prompt: str, system=None, format=None) -> str:
    prompt_lower = (prompt + " " + (system or "")).lower()
    if "agent orchestrator" in prompt_lower or "approved capabilities" in prompt_lower:
        return '{"tasks": [{"task_id": "task_1", "task_type": "analyze_resume", "description": "Analyze resume", "input": {}, "dependencies": []}]}'
    if "tailored_bullets" in prompt_lower:
        return '{"tailored_bullets": ["mocked bullet 1", "mocked bullet 2"]}'
    elif "tailored_resume" in prompt_lower:
        return '{"tailored_resume": "mocked resume text", "keyword_changes": [{"original": "old", "optimized": "new"}], "ats_score_estimate": 95}'
    elif "skill_score" in prompt_lower or "missing_skills" in prompt_lower:
        return '{"present_skills": ["python"], "missing_skills": ["docker"], "skill_score": 80, "recommendations": ["learn docker"], "learning_resources": ["docker docs"]}'
    elif "cover_letter" in prompt_lower or "letter" in prompt_lower:
        return '{"cover_letter": "Dear Hiring Manager, this is a mocked cover letter."}'
    return "Mocked Ollama response"

OllamaClient.generate = classmethod(mock_generate)

from fastapi.testclient import TestClient

# Clean up test directories on startup
for path in ["./test_data", "./test_uploads"]:
    if os.path.exists(path):
        shutil.rmtree(path)
os.makedirs("./test_data", exist_ok=True)
os.makedirs("./test_uploads", exist_ok=True)

from app.main import app
from app.auth.models import init_db

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def clean_test_dirs():
    # Setup/Teardown: Programmatically clear SQLite tables and ChromaDB collections
    # no direct sqlite connections; use SQLAlchemy SessionLocal
    from app.vector_db.chroma_client import ChromaDBClient
    
    # 1. Clear DB tables via SQLAlchemy session
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        for model in [
            'workflow_tasks', 'workflows', 'notifications', 'resume_versions', 'interview_sessions',
            'chat_messages', 'user_criteria', 'applications_history', 'users',
            'feedbacks'
        ]:
            try:
                db.execute(f"TRUNCATE TABLE {model} RESTART IDENTITY CASCADE")
            except Exception:
                # Fallback for SQLite which doesn't support TRUNCATE
                try:
                    db.execute(f"DELETE FROM {model}")
                except Exception:
                    pass
        db.commit()
    finally:
        db.close()

    # 2. Reset ChromaDB collections
    client = ChromaDBClient.get_client()
    for coll_name in ["user_profiles", "job_listings", "applications", "skills"]:
        try:
            client.delete_collection(coll_name)
        except Exception:
            pass
        # Re-create collection
        client.get_or_create_collection(coll_name)
        
    # Re-seed skills for any tests that need it
    ChromaDBClient.seed_skills_if_empty()

    yield


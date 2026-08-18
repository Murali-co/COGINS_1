import pytest
from unittest.mock import patch, AsyncMock
from app.copilot.router import classify_query
from app.rag.memory import ChatMemory
from app.auth.models import DBManager

def test_query_classification():
    # 1. Job keywords
    assert classify_query("Why does this position match me?") == "job"
    assert classify_query("Help me prepare for my software engineer interview tomorrow") == "job"
    assert classify_query("Tell me about my application status") == "job"
    
    # 2. Career keywords
    assert classify_query("How do I transition into an AI Developer role?") == "career"
    assert classify_query("What certifications should I learn next?") == "career"
    assert classify_query("Design a 6-month roadmap for product management") == "career"
    
    # 3. Resume / Fallback
    assert classify_query("Summarize my experience") == "resume"
    assert classify_query("What projects have I done?") == "resume"
    assert classify_query("Hi there!", job_id=None) == "resume"
    
    # 4. Injected Job ID
    assert classify_query("Hello assistant", job_id="job_123") == "job"

@patch("app.copilot.router.RAGGenerator.generate_response", new_callable=AsyncMock)
@patch("app.rag.retriever.ProfileStore.get_profile")
@patch("app.rag.retriever.ProfileStore.query_profile_sections")
def test_copilot_chat_endpoint(mock_query, mock_get_profile, mock_generate, client):
    # Register & Login
    client.post("/auth/register", json={
        "email": "copilot_tester@test.com",
        "password": "password123",
        "full_name": "Copilot Tester"
    })
    user = DBManager.get_user_by_email("copilot_tester@test.com")
    DBManager.verify_email(user["id"])
    login_res = client.post("/auth/login", json={
        "email": "copilot_tester@test.com",
        "password": "password123"
    })
    token = login_res.json()["access_token"]
    csrf_token = login_res.cookies.get("csrf_token")
    headers = {"Authorization": f"Bearer {token}"}
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token

    # Setup mocks
    mock_get_profile.return_value = {"skills": [], "resume_text": ""}
    mock_query.return_value = []
    mock_generate.return_value = "Mock copilot response."

    payload = {
        "message": "Design a study path to learn Kubernetes next.",
        "session_id": "test-session-copilot",
        "stream": False
    }
    response = client.post("/copilot/chat", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["response"] == "Mock copilot response."
    # Check that it classified the Kubernetes study question as a career query
    assert response.json()["classified_as"] == "career"

    # Verify history
    history = ChatMemory.get_messages("test-session-copilot")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"

    # Cleanup session
    client.delete("/copilot/session/test-session-copilot", headers=headers)

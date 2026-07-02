import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.rag.memory import ChatMemory
from app.rag.retriever import RAGRetriever
from app.rag.generator import RAGGenerator

def test_chat_memory():
    session_id = "test-session-123"
    user_id = 999
    
    # Clear any leftover messages
    ChatMemory.clear_session(session_id)
    
    # Assert initially empty
    msgs = ChatMemory.get_messages(session_id)
    assert len(msgs) == 0
    
    # Add messages
    ChatMemory.add_message(session_id, user_id, "user", "Hello assistant")
    ChatMemory.add_message(session_id, user_id, "assistant", "Hello user")
    
    # Fetch messages and verify
    msgs = ChatMemory.get_messages(session_id)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Hello assistant"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "Hello user"
    
    # Verify session listed
    sessions = ChatMemory.get_sessions(user_id)
    assert session_id in sessions
    
    # Clear session
    ChatMemory.clear_session(session_id)
    assert len(ChatMemory.get_messages(session_id)) == 0

@patch("app.rag.retriever.ProfileStore.get_profile")
@patch("app.rag.retriever.ProfileStore.query_profile_sections")
def test_retriever_resume(mock_query, mock_get_profile):
    mock_get_profile.return_value = {
        "skills": ["Python", "Docker"],
        "resume_text": "Experienced Python Software Engineer."
    }
    mock_query.return_value = [
        {"document": "Chunk 1", "metadata": {"section_name": "Experience"}}
    ]
    
    context = RAGRetriever.get_resume_context(user_id=1, query="Python experience")
    assert "Python" in context["skills"]
    assert "Chunk 1" in context["relevant_sections"]

@patch("app.rag.generator.OllamaClient.generate", new_callable=AsyncMock)
@patch("app.rag.retriever.ProfileStore.get_profile")
@patch("app.rag.retriever.ProfileStore.query_profile_sections")
def test_rag_chat_endpoint(mock_query, mock_get_profile, mock_generate, client):
    # Register / login a test user to get token
    client.post("/auth/register", json={
        "email": "rag_tester@test.com",
        "password": "password123",
        "full_name": "RAG Tester"
    })
    
    login_res = client.post("/auth/login", json={
        "email": "rag_tester@test.com",
        "password": "password123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Mock retriever responses
    mock_get_profile.return_value = {
        "skills": ["Python"],
        "resume_text": "Resume text"
    }
    mock_query.return_value = []
    
    # Mock Ollama output
    mock_generate.return_value = "This is a mock LLM answer about your resume."
    
    # Run request
    payload = {
        "message": "What projects have I done?",
        "chat_type": "resume",
        "session_id": "test-session-rag-endpoint",
        "stream": False
    }
    response = client.post("/rag/chat", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["response"] == "This is a mock LLM answer about your resume."
    
    # Verify it persisted the conversation
    messages = ChatMemory.get_messages("test-session-rag-endpoint")
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    
    # Cleanup session
    client.delete("/rag/session/test-session-rag-endpoint", headers=headers)

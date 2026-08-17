import pytest
import json
from unittest.mock import patch, MagicMock
from app.jobs.matcher import JobMatcher
from app.auth.models import DBManager

@patch("app.llm.ollama_client.OllamaClient.generate")
@patch("app.vector_db.profile_store.ProfileStore.get_profile")
def test_interview_coach_flow(mock_get_profile, mock_llm, client):
    # Register & Login
    client.post("/auth/register", json={
        "email": "coach_tester@test.com",
        "password": "password123",
        "full_name": "Coach Tester"
    })
    user = DBManager.get_user_by_email("coach_tester@test.com")
    DBManager.verify_email(user["id"])
    login_res = client.post("/auth/login", json={
        "email": "coach_tester@test.com",
        "password": "password123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Setup profile mock
    mock_get_profile.return_value = {
        "skills": ["Python", "FastAPI"],
        "resume_text": "Experienced Python and FastAPI backend developer."
    }

    # Mock LLM questions
    mock_llm.side_effect = [
        "Tell me about a time you used FastAPI?",  # First question
        "How did you handle database connections in that project?", # Second question
        "Great, what was the impact?", # Third question
        "What other frameworks have you worked with?", # Fourth question
        "And what was your favorite project?", # Fifth question
        # LLM feedback JSON output
        """
        {
            "score": 90,
            "feedback": "Outstanding technical communication and structured answers.",
            "strengths": ["FastAPI expertise", "Clear articulation"],
            "weaknesses": ["Lack of latency metrics"],
            "suggestions": ["Include performance numbers."]
        }
        """
    ]

    # 1. Start Interview
    start_res = client.post("/interview/start", json={"target_role": "Python Backend Engineer"}, headers=headers)
    assert start_res.status_code == 200
    start_data = start_res.json()
    assert "session_id" in start_data
    assert start_data["question"] == "Tell me about a time you used FastAPI?"
    assert start_data["question_index"] == 1
    session_id = start_data["session_id"]

    # 2. Answer Question 1
    ans_res_1 = client.post("/interview/answer", json={"session_id": session_id, "answer": "I built a microservice using FastAPI for a high-traffic app."}, headers=headers)
    assert ans_res_1.status_code == 200
    ans_data_1 = ans_res_1.json()
    assert ans_data_1["question_index"] == 2
    assert ans_data_1["next_question"] == "How did you handle database connections in that project?"
    assert not ans_data_1["is_finished"]

    # 3. Answer Question 2
    ans_res_2 = client.post("/interview/answer", json={"session_id": session_id, "answer": "I used SQLAlchemy async session pool with pool sizing configured."}, headers=headers)
    assert ans_res_2.status_code == 200
    ans_data_2 = ans_res_2.json()
    assert ans_data_2["question_index"] == 3
    assert ans_data_2["next_question"] == "Great, what was the impact?"
    assert not ans_data_2["is_finished"]

    # 4. Answer Question 3
    ans_res_3 = client.post("/interview/answer", json={"session_id": session_id, "answer": "It reduced query response latency by 35% under load."}, headers=headers)
    assert ans_res_3.status_code == 200
    ans_data_3 = ans_res_3.json()
    assert ans_data_3["question_index"] == 4
    assert ans_data_3["next_question"] == "What other frameworks have you worked with?"
    assert not ans_data_3["is_finished"]

    # 5. Answer Question 4
    ans_res_4 = client.post("/interview/answer", json={"session_id": session_id, "answer": "I have also used Flask and Django for smaller apps."}, headers=headers)
    assert ans_res_4.status_code == 200
    ans_data_4 = ans_res_4.json()
    assert ans_data_4["question_index"] == 5
    assert ans_data_4["next_question"] == "And what was your favorite project?"
    assert not ans_data_4["is_finished"]

    # 6. Answer Question 5
    ans_res_5 = client.post("/interview/answer", json={"session_id": session_id, "answer": "My favorite project was a real-time tracking service built with FastAPI and WebSockets."}, headers=headers)
    assert ans_res_5.status_code == 200
    ans_data_5 = ans_res_5.json()
    assert ans_data_5["is_finished"]

    # 7. Get Report
    report_res = client.get(f"/interview/report?session_id={session_id}", headers=headers)
    assert report_res.status_code == 200
    report_data = report_res.json()
    assert report_data["score"] == 90
    assert report_data["feedback"] == "Outstanding technical communication and structured answers."
    assert "FastAPI expertise" in report_data["strengths"]
    assert "Lack of latency metrics" in report_data["weaknesses"]
    assert "Include performance numbers." in report_data["suggestions"]

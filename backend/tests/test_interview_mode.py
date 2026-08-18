from app.auth.models import DBManager
from app.db.models import InterviewSession
from app.db.session import SessionLocal


def test_interview_session_stores_selected_mode():
    db = SessionLocal()
    try:
        session_id = "interview-mode-test"
        DBManager.create_interview_session(
            session_id=session_id,
            user_id=1,
            job_id=None,
            target_role="Backend Engineer",
            chat_history='[]',
            interview_mode="Technical",
        )

        saved = DBManager.get_interview_session(session_id)
        assert saved is not None
        assert saved["interview_mode"] == "Technical"
    finally:
        db.query(InterviewSession).filter(InterviewSession.id == session_id).delete(synchronize_session=False)
        db.commit()
        db.close()

import uuid
import json
import asyncio
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from app.auth.utils import get_current_user
from app.auth.models import DBManager
from app.vector_db.profile_store import ProfileStore
from app.jobs.matcher import JobMatcher
from app.llm.ollama_client import OllamaClient
from app.utils.limiter import limiter

router = APIRouter(prefix="/interview", tags=["interview"])

class StartRequest(BaseModel):
    job_id: Optional[str] = None
    target_role: Optional[str] = None
    interview_mode: Optional[str] = None

class AnswerRequest(BaseModel):
    session_id: str
    answer: str

# Helper to format conversation history for prompt injection
def format_chat_history(history: List[Dict[str, str]]) -> str:
    lines = []
    for msg in history:
        role = "Interviewer" if msg["role"] == "assistant" else "Candidate"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines)

@router.post("/start")
@limiter.limit("5/minute")
async def start_interview(
    request: Request,
    req: StartRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    profile = ProfileStore.get_profile(user_id)
    if not profile or not profile.get("resume_text"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resume not uploaded. Please upload your resume before starting a mock interview."
        )
    
    resume_text = profile["resume_text"]
    focus_text = "General Resume Review"
    
    # If job_id is provided, get the description
    if req.job_id:
        collection = JobMatcher.get_collection()
        job_data = collection.get(ids=[req.job_id])
        if job_data and job_data["ids"]:
            title = job_data["metadatas"][0].get("title", "Target Role")
            company = job_data["metadatas"][0].get("company", "Target Company")
            desc = job_data["documents"][0]
            focus_text = f"Job Application for '{title}' at '{company}'. Job Description:\n{desc}"
    elif req.target_role:
        focus_text = f"Target Role: {req.target_role}"

    # Generate first question
    prompt = f"""
    You are an expert AI Interview Coach. You are conducting a mock interview for the following candidate.

    Candidate Resume Details:
    {resume_text}

    Focus Area:
    {focus_text}

    Generate the FIRST interview question for this candidate. Make it tailored to their background and the focus area. Ask only one question. Do not include any greeting, intro, or formatting blocks.
    """
    
    try:
        question = await asyncio.wait_for(OllamaClient.generate(prompt), timeout=60.0)
        question = question.strip()
    except Exception as e:
        question = "Could you tell me about yourself and your background as it relates to this role?"

    session_id = f"session_{uuid.uuid4().hex[:12]}"
    
    initial_history = [
        {"role": "assistant", "content": question}
    ]
    
    DBManager.create_interview_session(
        session_id=session_id,
        user_id=user_id,
        job_id=req.job_id,
        target_role=req.target_role,
        chat_history=json.dumps(initial_history),
        interview_mode=req.interview_mode,
    )
    
    return {
        "session_id": session_id,
        "question": question,
        "question_index": 1
    }

@router.post("/answer")
@limiter.limit("10/minute")
async def submit_answer(
    request: Request,
    req: AnswerRequest,
    current_user: dict = Depends(get_current_user)
):
    session = DBManager.get_interview_session(req.session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found."
        )
    if session["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found."
        )
    
    if session["is_finished"]:
        return {
            "session_id": req.session_id,
            "is_finished": True
        }

    chat_history = json.loads(session["chat_history"])
    
    # Save user's answer
    chat_history.append({"role": "user", "content": req.answer})
    
    # Calculate current turn count (how many questions have been asked)
    # assistant message count
    question_count = sum(1 for m in chat_history if m["role"] == "assistant")
    
    if question_count >= 5:  # changed from 3 to 5
        # Mark as finished
        DBManager.update_interview_session(
            session_id=req.session_id,
            chat_history=json.dumps(chat_history),
            is_finished=1
        )
        return {
            "session_id": req.session_id,
            "is_finished": True
        }

    # Generate next question
    profile = ProfileStore.get_profile(current_user["id"])
    resume_text = profile.get("resume_text", "")
    
    focus_text = "General Resume Review"
    if session["job_id"]:
        collection = JobMatcher.get_collection()
        job_data = collection.get(ids=[session["job_id"]])
        if job_data and job_data["ids"]:
            title = job_data["metadatas"][0].get("title")
            company = job_data["metadatas"][0].get("company")
            focus_text = f"Job Application for '{title}' at '{company}'"
    elif session["target_role"]:
        focus_text = f"Target Role: {session['target_role']}"

    formatted_history = format_chat_history(chat_history)
    
    prompt = f"""
    You are an expert AI Interview Coach conducting a mock interview.

    Interview Context:
    Candidate Resume: {resume_text}
    Focus Area: {focus_text}

    Here is the dialogue history so far:
    {formatted_history}

    Based on the candidate's last answer, formulate a relevant follow-up question or transition to the next interview question. Ask only one question. Do not output any conversational meta-text, introductions, or explanations. Just return the question.
    """
    
    try:
        next_question = await asyncio.wait_for(OllamaClient.generate(prompt), timeout=60.0)
        next_question = next_question.strip()
    except Exception as e:
        next_question = "Great. Can you walk me through a challenging technical problem you solved in a past project?"

    chat_history.append({"role": "assistant", "content": next_question})
    
    DBManager.update_interview_session(
        session_id=req.session_id,
        chat_history=json.dumps(chat_history),
        is_finished=0
    )
    
    return {
        "session_id": req.session_id,
        "question_index": question_count + 1,
        "next_question": next_question,
        "is_finished": False
    }

@router.get("/report")
@limiter.limit("5/minute")
async def get_report(
    request: Request,
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    session = DBManager.get_interview_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found."
        )
    if session["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found."
        )
        
    if not session["is_finished"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview is still active. Please finish all questions before generating a report."
        )

    # Return cached report if already evaluated
    if session["feedback"] and session["score"] is not None:
        try:
            feedback_data = json.loads(session["feedback"])
            return {
                "score": session["score"],
                "feedback": feedback_data.get("feedback", ""),
                "strengths": feedback_data.get("strengths", []),
                "weaknesses": feedback_data.get("weaknesses", []),
                "suggestions": feedback_data.get("suggestions", [])
            }
        except Exception:
            # Fall back to regenerating if JSON parse fails
            pass

    # Generate new evaluation
    profile = ProfileStore.get_profile(current_user["id"])
    resume_text = profile.get("resume_text", "")
    
    focus_text = "General Resume Review"
    if session["job_id"]:
        collection = JobMatcher.get_collection()
        job_data = collection.get(ids=[session["job_id"]])
        if job_data and job_data["ids"]:
            title = job_data["metadatas"][0].get("title")
            company = job_data["metadatas"][0].get("company")
            focus_text = f"Job Application for '{title}' at '{company}'"
    elif session["target_role"]:
        focus_text = f"Target Role: {session['target_role']}"

    chat_history = json.loads(session["chat_history"])
    formatted_history = format_chat_history(chat_history)
    
    prompt = f"""
    You are an expert Interview Coach and senior hiring manager. Evaluate this candidate's mock interview performance.

    Candidate Resume:
    {resume_text}

    Focus Area:
    {focus_text}

    Dialogue Transcript:
    {formatted_history}

    Provide a structured, constructive assessment. Report the overall performance score (0 to 100), key strengths, areas for improvement/weaknesses, and concrete recommendations.

    Return ONLY a valid JSON object. Do not wrap it in markdown block tags. Do not output any conversational introductions or conclusions.

    JSON Schema:
    {{
        "score": 85,
        "feedback": "Detailed overall assessment of the dialogue and answers...",
        "strengths": ["Strengths 1", "Strengths 2"],
        "weaknesses": ["Weakness 1", "Weakness 2"],
        "suggestions": ["Suggestion 1", "Suggestion 2"]
    }}
    """
    
    score = 75
    feedback_data = {
        "feedback": "Review of answers shows solid background knowledge but responses could be structured more effectively using the STAR method.",
        "strengths": ["Clear technical articulation", "Relevant examples"],
        "weaknesses": ["Lack of quantifiable achievements", "Answers could be more concise"],
        "suggestions": ["Use STAR method (Situation, Task, Action, Result)", "Quantify project outcomes with numbers/percentages"]
    }

    try:
        llm_res = await asyncio.wait_for(OllamaClient.generate(prompt), timeout=90.0)
        cleaned = llm_res.strip()
        if "```" in cleaned:
            parts = cleaned.split("```")
            for p in parts:
                p_strip = p.strip()
                if p_strip.startswith("{") or p_strip.startswith("json\n{"):
                    if p_strip.startswith("json\n"):
                        cleaned = p_strip[5:]
                    else:
                        cleaned = p_strip
                    break
        
        parsed = json.loads(cleaned)
        score = int(parsed.get("score", score))
        feedback_data["feedback"] = parsed.get("feedback", feedback_data["feedback"])
        feedback_data["strengths"] = parsed.get("strengths", feedback_data["strengths"])
        feedback_data["weaknesses"] = parsed.get("weaknesses", feedback_data["weaknesses"])
        feedback_data["suggestions"] = parsed.get("suggestions", feedback_data["suggestions"])
    except asyncio.TimeoutError:
        print(f"Ollama report generation timed out. Using default feedback.")
        # fall through to default feedback_data
    except Exception as e:
        print(f"Ollama report parsing warning: {e}. Raw: {llm_res if 'llm_res' in locals() else 'None'}")

    # Save evaluation report to database
    DBManager.update_interview_session(
        session_id=session_id,
        chat_history=session["chat_history"],
        is_finished=1,
        feedback=json.dumps(feedback_data),
        score=score
    )
    
    return {
        "score": score,
        "feedback": feedback_data["feedback"],
        "strengths": feedback_data["strengths"],
        "weaknesses": feedback_data["weaknesses"],
        "suggestions": feedback_data["suggestions"]
    }

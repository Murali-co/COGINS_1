from typing import List, Dict, Any, AsyncGenerator, Optional
import asyncio
from app.llm.ollama_client import OllamaClient
from app.rag.retriever import RAGRetriever

class RAGGenerator:
    SYSTEM_INSTRUCTIONS = (
        "You are COGNIS, a highly intelligent and professional Local AI Career Copilot. "
        "Your goal is to guide the user with highly accurate, personalized, and actionable "
        "career guidance, resume analysis, and job alignment advice. "
        "Adhere to these rules strictly:\n"
        "1. Answer the user's message using ONLY the provided Context and Conversation History.\n"
        "2. Do not invent achievements, roles, or skills that are not mentioned in the resume or context.\n"
        "3. If the context does not contain enough information to answer a question, state it honestly "
        "and suggest what information is missing.\n"
        "4. Keep your tone professional, encouraging, and structured (using bullet points and bolding where appropriate)."
    )

    @classmethod
    def _format_chat_prompt(cls, message: str, context_str: str, history: List[Dict[str, Any]]) -> str:
        """
        Builds the prompt string combining history, retrieved context, and the new query.
        """
        prompt = "## CONTEXT INFORMATION\n"
        prompt += f"{context_str}\n\n"
        
        prompt += "## CONVERSATION HISTORY\n"
        for msg in history:
            role_label = "User" if msg["role"] == "user" else "Assistant"
            prompt += f"{role_label}: {msg['content']}\n"
            
        prompt += f"\nUser: {message}\n"
        prompt += "Assistant: "
        return prompt

    @classmethod
    def _assemble_context_string(cls, chat_type: str, context: Dict[str, Any]) -> str:
        """
        Formats the retrieved context dict into a readable text block.
        """
        if chat_type == "resume":
            skills_str = ", ".join(context.get("skills", []))
            full_resume_clipped = context.get('full_resume', '')[:2000]
            if len(context.get('full_resume', '')) > 2000:
                full_resume_clipped += "\n... [truncated for speed] ..."
            return (
                f"User Skills: {skills_str}\n\n"
                f"Granular Relevant Resume Sections:\n"
                f"{context.get('relevant_sections', 'No matching sections found.')}\n\n"
                f"Full Resume Content Reference:\n"
                f"{full_resume_clipped}"
            )
            
        elif chat_type == "job":
            job = context.get("job", {})
            matched = ", ".join(job.get("matched_skills", [])) or "None"
            missing = ", ".join(job.get("missing_skills", [])) or "None"
            desc_clipped = job.get('description', '')[:1500]
            if len(job.get('description', '')) > 1500:
                desc_clipped += "\n... [truncated for speed] ..."
            return (
                f"Target Job: {job.get('title')} at {job.get('company')}\n"
                f"Match Score: {job.get('match_score')}%\n"
                f"Matched Skills: {matched}\n"
                f"Missing Skills: {missing}\n\n"
                f"Job Description:\n{desc_clipped}\n\n"
                f"Relevant user experience alignment:\n"
                f"{context.get('relevant_resume_sections', 'No direct section alignments found.')}"
            )
            
        elif chat_type == "career":
            skills_str = ", ".join(context.get("user_skills", []))
            market_jobs_str = ""
            for idx, job in enumerate(context.get("market_demand_jobs", [])):
                market_jobs_str += f"\nJob {idx+1}: {job['title']} at {job['company']}\nDescription Summary:\n{job['description'][:500]}...\n"
                
            return (
                f"User Current Skills: {skills_str}\n\n"
                f"Current User Application History:\n{context.get('application_history', '')}\n\n"
                f"Market Job Demand Examples (Grounding career path requirements):\n"
                f"{market_jobs_str or 'No market jobs retrieved.'}"
            )
            
        return "No context available."

    @classmethod
    async def generate_response(
        cls, 
        user_id: int, 
        message: str, 
        chat_type: str, 
        history: List[Dict[str, Any]], 
        job_id: Optional[str] = None
    ) -> str:
        """
        Generates standard complete text response with timeout.
        """
        # 1. Retrieve context
        if chat_type == "job" and job_id:
            context = RAGRetriever.get_job_context(user_id, job_id)
        elif chat_type == "career":
            context = RAGRetriever.get_career_context(user_id, message)
        else:
            context = RAGRetriever.get_resume_context(user_id, message)
            
        context_str = cls._assemble_context_string(chat_type, context)
        prompt = cls._format_chat_prompt(message, context_str, history)
        
        # 2. Call local LLM with timeout
        try:
            return await asyncio.wait_for(
                OllamaClient.generate(prompt, system=cls.SYSTEM_INSTRUCTIONS),
                timeout=60.0  # 60 second max
            )
        except asyncio.TimeoutError:
            return "I'm taking too long to respond right now. Try a shorter question or check if Ollama is running."

    @classmethod
    async def generate_stream(
        cls, 
        user_id: int, 
        message: str, 
        chat_type: str, 
        history: List[Dict[str, Any]], 
        job_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Streams response tokens back as they generate, with timeout.
        """
        # 1. Retrieve context
        if chat_type == "job" and job_id:
            context = RAGRetriever.get_job_context(user_id, job_id)
        elif chat_type == "career":
            context = RAGRetriever.get_career_context(user_id, message)
        else:
            context = RAGRetriever.get_resume_context(user_id, message)
            
        context_str = cls._assemble_context_string(chat_type, context)
        prompt = cls._format_chat_prompt(message, context_str, history)
        
        # 2. Stream from local LLM
        try:
            async for token in OllamaClient.generate_stream(prompt, system=cls.SYSTEM_INSTRUCTIONS):
                yield token
        except Exception as e:
            print(f"Error streaming from Ollama: {e}")
            yield "Failed to connect to local Ollama. Please check if Ollama is running and your model is pulled."

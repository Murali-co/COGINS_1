import re
from typing import List, Dict, Any
from app.vector_db.chroma_client import ChromaDBClient
from app.vector_db.embedder import embed_text, embed_batch
from app.vector_db.profile_store import ProfileStore
from app.resume.extractor import SKILL_TAXONOMY

class JobMatcher:
    COLLECTION_NAME = "job_listings"
    _match_cache = {}  # In-memory cache for matched jobs to optimize performance

    @classmethod
    def get_collection(cls):
        return ChromaDBClient.get_collection(cls.COLLECTION_NAME)

    @classmethod
    def upsert_jobs(cls, jobs: List[Dict[str, Any]]):
        cls._match_cache.clear()  # Clear match cache when new jobs are indexed
        collection = cls.get_collection()
        if not jobs:
            return
            
        ids = []
        documents = []
        embeddings = []
        metadatas = []
        
        # Collect descriptions for batch embedding to optimize performance
        descriptions = [j["description"] for j in jobs]
        job_embeddings = embed_batch(descriptions)
        
        for i, job in enumerate(jobs):
            ids.append(job["id"])
            documents.append(job["description"])
            embeddings.append(job_embeddings[i])
            metadatas.append({
                "title": job["title"],
                "company": job["company"],
                "location": job["location"],
                "url": job["url"],
                "posted_at": job["posted_at"],
                "source": job["source"],
                "job_type": job.get("job_type", "onsite"),
            })
            
        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas
        )

    @classmethod
    def match_jobs_for_user(cls, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        cache_key = (user_id, limit)
        if cache_key in cls._match_cache:
            return cls._match_cache[cache_key]

        collection = cls.get_collection()
        
        # 1. Retrieve the user's profile text and skills
        profile = ProfileStore.get_profile(user_id)
        if not profile or not profile.get("resume_text"):
            # If no profile, we can't do semantic matching. Return raw list of jobs with 0 score
            results = collection.get(limit=limit)
            return cls._format_unmatched_jobs(results)
            
        user_skills = set(profile.get("skills", []))
        user_skills_lower = {s.lower() for s in user_skills}
        
        # 2. Get the full profile embedding
        profile_collection = ProfileStore.get_collection()
        profile_emb_result = profile_collection.get(
            ids=[f"{user_id}_full_profile"],
            include=["embeddings"]
        )
        
        # Handle numpy arrays safely - avoid boolean checks on multi-element arrays
        user_emb = None
        if profile_emb_result:
            embeddings = profile_emb_result.get("embeddings")
            if embeddings is not None:
                # Convert to list if it's a numpy array to safely check length
                embeddings_list = embeddings.tolist() if hasattr(embeddings, 'tolist') else embeddings
                if isinstance(embeddings_list, list) and len(embeddings_list) > 0:
                    user_emb = embeddings_list[0]
        
        # Recompute embedding if missing
        if user_emb is None:
            user_emb = embed_text(profile["resume_text"])
            
        # 3. Query job_listings with user embedding natively
        results = collection.query(
            query_embeddings=[user_emb],
            n_results=limit
        )
        
        matched_jobs = []
        if not results or not results["ids"] or not results["ids"][0]:
            return []
            
        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0] if "distances" in results else [0.5] * len(ids)
        
        for i in range(len(ids)):
            job_id = ids[i]
            desc = documents[i]
            meta = metadatas[i]
            dist = distances[i]
            
            # Convert distance to similarity score
            # Depending on space (L2 vs Cosine), handle normalize
            # Standard conversion: score = max(0, min(100, (1 - distance) * 100))
            score = (1.0 - float(dist)) * 100.0
            # If distance was L2, it can be > 1. Let's normalize it to 0-100 range.
            if dist > 1.0:
                score = max(0.0, min(100.0, (1.0 - (dist / 2.0)) * 100.0))
            else:
                score = max(0.0, min(100.0, score))
            
            # 4. Extract skills mentioned in this job
            job_desc_lower = desc.lower()
            job_skills = set()
            for kw, std_name in SKILL_TAXONOMY.items():
                escaped_kw = re.escape(kw)
                pattern = rf"\b{escaped_kw}" if (kw.endswith("++") or kw.endswith("#")) else rf"\b{escaped_kw}\b"
                if re.search(pattern, job_desc_lower):
                    job_skills.add(std_name)
                    
            # Separate into matched vs missing skills
            matched_skills_list = []
            missing_skills_list = []
            for s in job_skills:
                if s.lower() in user_skills_lower:
                    matched_skills_list.append(s)
                else:
                    missing_skills_list.append(s)
                    
            matched_jobs.append({
                "id": job_id,
                "title": meta.get("title", "Unknown Role"),
                "company": meta.get("company", "Unknown Company"),
                "location": meta.get("location", "Remote"),
                "description": desc,
                "url": meta.get("url", ""),
                "posted_at": meta.get("posted_at", ""),
                "source": meta.get("source", "scraped"),
                "job_type": meta.get("job_type", "onsite"),
                "match_score": round(score, 1),
                "matched_skills": matched_skills_list,
                "missing_skills": missing_skills_list
            })
            
        # Rank by match score descending
        matched_jobs.sort(key=lambda x: x["match_score"], reverse=True)
        
        cls._match_cache[cache_key] = matched_jobs
        return matched_jobs

    @classmethod
    def _format_unmatched_jobs(cls, get_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        jobs = []
        if not get_results or not get_results["ids"]:
            return []
        for i in range(len(get_results["ids"])):
            meta = get_results["metadatas"][i]
            jobs.append({
                "id": get_results["ids"][i],
                "title": meta.get("title", "Unknown Role"),
                "company": meta.get("company", "Unknown Company"),
                "location": meta.get("location", "Remote"),
                "description": get_results["documents"][i],
                "url": meta.get("url", ""),
                "posted_at": meta.get("posted_at", ""),
                "source": meta.get("source", "scraped"),
                "job_type": meta.get("job_type", "onsite"),
                "match_score": 0.0,
                "matched_skills": [],
                "missing_skills": []
            })
        return jobs

    @classmethod
    def cleanup_old_jobs(cls, days: int = 30):
        collection = cls.get_collection()
        results = collection.get(include=["metadatas"])
        if not results or not results["ids"]:
            return
        
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc)
        ids_to_delete = []
        
        for i, job_id in enumerate(results["ids"]):
            meta = results["metadatas"][i]
            posted_at_str = meta.get("posted_at")
            if not posted_at_str:
                continue
            try:
                posted_date = None
                if "T" in posted_at_str:
                    clean_str = posted_at_str.replace("Z", "+00:00")
                    posted_date = datetime.fromisoformat(clean_str)
                elif "-" in posted_at_str:
                    parts = posted_at_str.split(" ")[0].split("-")
                    if len(parts) == 3:
                        posted_date = datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=timezone.utc)
                
                if posted_date:
                    age_days = (now - posted_date).days
                    if age_days > days:
                        ids_to_delete.append(job_id)
            except Exception as e:
                print(f"Error parsing date {posted_at_str}: {e}")
                
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            print(f"Cleaned up {len(ids_to_delete)} stale jobs from ChromaDB.")


    @classmethod
    async def explain_job_match(cls, user_id: int, job_id: str) -> Dict[str, Any]:
        """
        Retrieves vector match score, matched/missing skills, and queries the local LLM
        to produce detailed analysis of experience, education, keyword gaps, and recommendations.
        """
        collection = cls.get_collection()
        job_data = collection.get(ids=[job_id])
        if not job_data or not job_data["ids"]:
            raise Exception("Job listing not found.")
            
        desc = job_data["documents"][0]
        meta = job_data["metadatas"][0]
        
        # 1. Fetch user profile
        profile = ProfileStore.get_profile(user_id)
        if not profile or not profile.get("resume_text"):
            raise Exception("User profile/resume not found. Please upload a resume first.")
            
        resume_text = profile["resume_text"]
        user_skills = set(profile.get("skills", []))
        user_skills_lower = {s.lower() for s in user_skills}
        
        # 2. Get user embedding
        profile_collection = ProfileStore.get_collection()
        profile_emb_result = profile_collection.get(
            ids=[f"{user_id}_full_profile"],
            include=["embeddings"]
        )
        
        # Handle numpy arrays safely - avoid boolean checks on multi-element arrays
        user_emb = None
        if profile_emb_result:
            embeddings = profile_emb_result.get("embeddings")
            if embeddings is not None:
                # Convert to list if it's a numpy array to safely check length
                embeddings_list = embeddings.tolist() if hasattr(embeddings, 'tolist') else embeddings
                if isinstance(embeddings_list, list) and len(embeddings_list) > 0:
                    user_emb = embeddings_list[0]
        
        # Recompute embedding if missing
        if user_emb is None:
            user_emb = embed_text(resume_text)
            
        # Query specifically to find this job's vector distance
        results = collection.query(
            query_embeddings=[user_emb],
            n_results=100
        )
        
        dist = 0.5
        if results and results["ids"] and results["ids"][0]:
            for idx_id, rid in enumerate(results["ids"][0]):
                if rid == job_id:
                    dist = results["distances"][0][idx_id]
                    break
        
        # Normalize score
        score = (1.0 - float(dist)) * 100.0
        if dist > 1.0:
            score = max(0.0, min(100.0, (1.0 - (dist / 2.0)) * 100.0))
        else:
            score = max(0.0, min(100.0, score))
        score = round(score, 1)

        # 3. Extract skills
        job_desc_lower = desc.lower()
        job_skills = set()
        for kw, std_name in SKILL_TAXONOMY.items():
            escaped_kw = re.escape(kw)
            pattern = rf"\b{escaped_kw}" if (kw.endswith("++") or kw.endswith("#")) else rf"\b{escaped_kw}\b"
            if re.search(pattern, job_desc_lower):
                job_skills.add(std_name)
                
        matched_skills_list = []
        missing_skills_list = []
        for s in job_skills:
            if s.lower() in user_skills_lower:
                matched_skills_list.append(s)
            else:
                missing_skills_list.append(s)
                
        # 4. LLM Gap Analysis
        from app.llm.ollama_client import OllamaClient
        import json
        
        prompt = f"""
        You are an ATS Parser and Career Copilot. Analyze the candidate's resume against the target job description.
        
        Target Job Title: {meta.get("title")}
        Target Job Company: {meta.get("company")}
        
        Candidate Resume:
        {resume_text}
        
        Job Description:
        {desc}
        
        Provide a structured analysis comparing:
        1. Experience Gap: Compare years of experience or level of seniority.
        2. Education Gap: Compare degree levels and fields.
        3. Keyword Gap: Key terms and technologies in the job description missing from the resume.
        4. Actionable Recommendations: Actionable steps (projects, courses, certifications) to raise the match score.
        
        Return ONLY a valid JSON object. Do not wrap it in markdown block tags. Do not output any introductory or concluding text.
        
        JSON Schema:
        {{
            "experience_gap": "description of experience gaps",
            "education_gap": "description of education/degree gaps",
            "keyword_gap": ["missing_term_1", "missing_term_2"],
            "recommendations": ["actionable_tip_1", "actionable_tip_2"]
        }}
        """
        
        experience_gap = "Unable to analyze experience gap."
        education_gap = "Unable to analyze education gap."
        keyword_gap = []
        recommendations = [
            "Review job requirements and align resume keywords.",
            "Build target projects to gain hands-on experience.",
            "Obtain relevant certifications in missing tech stacks."
        ]
        
        try:
            llm_res = await OllamaClient.generate(prompt)
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
            
            data = json.loads(cleaned)
            experience_gap = data.get("experience_gap", experience_gap)
            education_gap = data.get("education_gap", education_gap)
            keyword_gap = data.get("keyword_gap", keyword_gap)
            recommendations = data.get("recommendations", recommendations)
        except Exception as e:
            print(f"Ollama JSON parsing failed, using fallbacks: {e}")
            
        return {
            "score": score,
            "matched_skills": matched_skills_list,
            "missing_skills": missing_skills_list,
            "experience_gap": experience_gap,
            "education_gap": education_gap,
            "keyword_gap": keyword_gap,
            "recommendations": recommendations
        }


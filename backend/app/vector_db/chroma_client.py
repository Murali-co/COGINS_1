import chromadb
from typing import List, Dict, Any, Optional
from app.config import settings
from app.vector_db.embedder import embed_text

class ChromaDBClient:
    _client = None

    @classmethod
    def get_client(cls):
        if cls._client is None:
            import os
            import shutil

            def init_client():
                return chromadb.PersistentClient(path=settings.CHROMA_PATH)

            try:
                cls._client = init_client()
                # Run a quick check to verify database schema/bindings health
                collections = cls._client.list_collections()
                for col in collections:
                    col.count()
            except Exception as e:
                err_msg = str(e)
                if any(phrase in err_msg for phrase in ["mismatched types", "Rust type", "compatible with SQL type", "InternalError"]):
                    print(f"⚠️ ChromaDB database error detected: {e}")
                    print(f"Resetting ChromaDB persistent store at: {settings.CHROMA_PATH}")
                    cls._client = None
                    if os.path.exists(settings.CHROMA_PATH):
                        try:
                            shutil.rmtree(settings.CHROMA_PATH)
                        except Exception as rm_err:
                            print(f"Failed to delete ChromaDB path: {rm_err}")
                            # fallback: try to delete files inside
                            for root, dirs, files in os.walk(settings.CHROMA_PATH, topdown=False):
                                for name in files:
                                    try:
                                        os.remove(os.path.join(root, name))
                                    except Exception:
                                        pass
                                for name in dirs:
                                    try:
                                        os.rmdir(os.path.join(root, name))
                                    except Exception:
                                        pass
                    # Recreate directory and reinitialize
                    os.makedirs(settings.CHROMA_PATH, exist_ok=True)
                    cls._client = init_client()
                else:
                    raise e
        return cls._client

    @classmethod
    def get_collection(cls, name: str):
        client = cls.get_client()
        return client.get_or_create_collection(name=name)

    @classmethod
    def _format_query_results(cls, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        outputs = []
        if results and results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                outputs.append({
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i] if "distances" in results else None
                })
        return outputs

    @classmethod
    def query_profile(
        cls, 
        user_id: int, 
        query_text: str, 
        n_results: int = 5, 
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic query over user resume sections, isolated by user_id.
        """
        collection = cls.get_collection("user_profiles")
        query_emb = embed_text(query_text)
        
        user_filter = {"user_id": {"$eq": str(user_id)}}
        # Exclude the full resume from section queries to find granular matches
        section_filter = {"type": {"$ne": "full"}}
        
        combined_filters = [user_filter, section_filter]
        if where:
            combined_filters.append(where)
            
        combined_where = {"$and": combined_filters}

        results = collection.query(
            query_embeddings=[query_emb],
            n_results=n_results,
            where=combined_where
        )
        return cls._format_query_results(results)

    @classmethod
    def query_jobs(
        cls, 
        query_text: str, 
        n_results: int = 5, 
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic query over scraped job descriptions.
        """
        collection = cls.get_collection("job_listings")
        query_emb = embed_text(query_text)
        
        results = collection.query(
            query_embeddings=[query_emb],
            n_results=n_results,
            where=where
        )
        return cls._format_query_results(results)

    @classmethod
    def query_applications(
        cls, 
        user_id: int, 
        query_text: str, 
        n_results: int = 5, 
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic query over stored applications/proposals (if written to vector db).
        """
        collection = cls.get_collection("applications")
        query_emb = embed_text(query_text)

        user_filter = {"user_id": {"$eq": str(user_id)}}
        if where:
            combined_where = {"$and": [user_filter, where]}
        else:
            combined_where = user_filter

        results = collection.query(
            query_embeddings=[query_emb],
            n_results=n_results,
            where=combined_where
        )
        return cls._format_query_results(results)

    @classmethod
    def query_skills(
        cls, 
        query_text: str, 
        n_results: int = 5, 
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic query over taxonomy skills.
        """
        collection = cls.get_collection("skills")
        query_emb = embed_text(query_text)

        results = collection.query(
            query_embeddings=[query_emb],
            n_results=n_results,
            where=where
        )
        return cls._format_query_results(results)

    @classmethod
    def seed_skills_if_empty(cls):
        """
        Seeds the skills collection from extractor's taxonomy.
        Handles permission errors gracefully in test environments.
        """
        collection = cls.get_collection("skills")
        try:
            if collection.count() == 0:
                from app.resume.extractor import SKILL_TAXONOMY
                from app.vector_db.embedder import embed_batch
                
                unique_skills = sorted(list(set(SKILL_TAXONOMY.values())))
                if not unique_skills:
                    return
                
                ids = [
                    f"skill_{s.lower().replace(' ', '_').replace('+', 'p').replace('#', 'sharp')}" 
                    for s in unique_skills
                ]
                documents = [f"{s} - programming skill, framework, or technology" for s in unique_skills]
                embeddings = embed_batch(documents)
                metadatas = [{"skill": s} for s in unique_skills]
                
                collection.add(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas
                )
                print(f"✅ Successfully seeded {len(unique_skills)} unique skills into vector DB.")
        except PermissionError as e:
            print(f"⚠️  Permission denied writing to ChromaDB: {e}")
            print(f"   → Chroma path: {settings.CHROMA_PATH}")
            print(f"   → Fix: chmod -R u+w {settings.CHROMA_PATH}")
        except Exception as e:
            print(f"⚠️  Warning: Failed to seed skills database: {e}")

# Ensure collections are initialized and seeded on start
ChromaDBClient.get_collection("user_profiles")
ChromaDBClient.get_collection("job_listings")
ChromaDBClient.get_collection("applications")
ChromaDBClient.get_collection("skills")
ChromaDBClient.seed_skills_if_empty()

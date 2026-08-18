from typing import List
from sentence_transformers import SentenceTransformer

# Lazy-loaded model to keep startup fast
_model = None

def get_embedding_model():
    global _model
    if _model is None:
        # Load the specified model
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model

def embed_text(text: str) -> List[float]:
    model = get_embedding_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()

def embed_batch(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    model = get_embedding_model()
    embeddings = model.encode(texts, convert_to_numpy=True)
    return embeddings.tolist()

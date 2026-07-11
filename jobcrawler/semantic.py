"""Semantic title matching: local sentence-transformers embeddings with Chroma
as the persistent embedding store, run ALONGSIDE rapidfuzz for comparison.

Optional dependency (requirements-ml.txt). When the libraries aren't
installed, main falls back to fuzzy-only matching.
"""
import logging
import os

log = logging.getLogger(__name__)
MODEL_NAME = "all-MiniLM-L6-v2"
_model = None


def available():
    try:
        import chromadb  # noqa: F401
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def title_match_ids(jobs, filters):
    """Ids of jobs whose title is semantically close to any role keyword.

    Chroma caches title embeddings across runs so unchanged jobs are never
    re-embedded; similarity itself is a plain cosine check.
    """
    if not jobs:
        return set()
    import chromadb
    import numpy as np

    model = _get_model()
    client = chromadb.PersistentClient(path=os.environ.get("CHROMA_DIR", ".chroma"))
    coll = client.get_or_create_collection("job_titles")

    ids = [j.id for j in jobs]
    cached = set(coll.get(ids=ids)["ids"])
    new = [j for j in jobs if j.id not in cached]
    if new:
        embeddings = model.encode([j.title for j in new],
                                  show_progress_bar=False)
        coll.add(ids=[j.id for j in new], embeddings=embeddings.tolist(),
                 documents=[j.title for j in new])

    got = coll.get(ids=ids, include=["embeddings"])
    vectors = dict(zip(got["ids"], got["embeddings"]))

    role_vectors = model.encode(filters["roles"], show_progress_bar=False)
    role_vectors = [v / np.linalg.norm(v) for v in role_vectors]
    # calibrated on all-MiniLM-L6-v2: engineering titles score ~0.46-0.83
    # against "Software Engineer", non-tech titles ~0.23-0.38
    threshold = filters.get("semantic_threshold", 0.45)

    matched = set()
    for j in jobs:
        v = np.asarray(vectors[j.id], dtype=float)
        v = v / np.linalg.norm(v)
        if any(float(v @ rv) >= threshold for rv in role_vectors):
            matched.add(j.id)
    return matched

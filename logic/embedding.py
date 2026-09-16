"""
SHARED EMBEDDING MODEL

One sentence-transformers model instance, loaded once at import time,
reused by skill_matching.py and feasibility.py so it isn't loaded twice.
"""
from sentence_transformers import SentenceTransformer, util

_model = SentenceTransformer("all-MiniLM-L6-v2")


def embed(text_or_texts):
    return _model.encode(text_or_texts)


def cosine_sim(a, b):
    return util.cos_sim(a, b)

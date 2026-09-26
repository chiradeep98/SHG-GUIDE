"""
Downloads the skill matcher's weights at image-build time.

Without this the first woman to speak waits out a 90MB download mid-request,
and on a host with a read-only filesystem it fails outright. Deliberately
non-fatal: a deployment that leaves sentence_transformers out of
requirements-api.txt should still build, and /api/match falls back to keyword
matching there.
"""
try:
    from sentence_transformers import SentenceTransformer
    SentenceTransformer("all-MiniLM-L6-v2")
    print("embedding model cached")
except Exception as exc:
    print(f"skipping model prefetch: {exc}")

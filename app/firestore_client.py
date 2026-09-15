"""
Firestore client — stores review history and retrieves historical patterns
for contextual, learning-aware reviews.
"""
import os
import logging
from datetime import datetime
from google.cloud import firestore

logger = logging.getLogger(__name__)

_db: firestore.AsyncClient | None = None


def get_db() -> firestore.AsyncClient:
    global _db
    if _db is None:
        _db = firestore.AsyncClient(project=os.environ["GCP_PROJECT_ID"])
    return _db


async def save_review(review_data: dict) -> str:
    """Persist a completed review to Firestore."""
    db = get_db()
    repo = review_data.get("repo_full_name", "unknown").replace("/", "_")
    doc_ref = db.collection("reviews").document()
    await doc_ref.set({
        **review_data,
        "reviewed_at": firestore.SERVER_TIMESTAMP,
        "repo_slug": repo,
    })
    logger.info("Saved review %s to Firestore", doc_ref.id)
    return doc_ref.id


async def get_recent_reviews(repo_full_name: str, limit: int = 5) -> list[dict]:
    """
    Retrieve the N most recent reviews for a repo.
    Used to build historical context for the next Gemini call.
    """
    db = get_db()
    repo_slug = repo_full_name.replace("/", "_")
    query = (
        db.collection("reviews")
        .where("repo_slug", "==", repo_slug)
        .order_by("reviewed_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    docs = query.stream()
    results = []
    async for doc in docs:
        results.append(doc.to_dict())
    return results


async def get_all_reviews(limit: int = 50) -> list[dict]:
    """Return all recent reviews across all repos — used by the dashboard."""
    db = get_db()
    query = (
        db.collection("reviews")
        .order_by("reviewed_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    docs = query.stream()
    results = []
    async for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        # Convert Firestore timestamp to ISO string
        if isinstance(d.get("reviewed_at"), datetime):
            d["reviewed_at"] = d["reviewed_at"].isoformat()
        results.append(d)
    return results


async def get_repo_stats(repo_full_name: str) -> dict:
    """Aggregate stats for a repo — average score, review count, common issues."""
    reviews = await get_recent_reviews(repo_full_name, limit=20)
    if not reviews:
        return {"count": 0, "avg_score": 0, "common_issues": []}

    scores = [r.get("total_score", 0) for r in reviews if r.get("total_score")]
    avg = round(sum(scores) / len(scores), 1) if scores else 0

    # Collect top repeated issue keywords
    issue_words: dict[str, int] = {}
    for r in reviews:
        for comment in r.get("inline_comments", []):
            for word in comment.get("body", "").lower().split():
                if len(word) > 5:
                    issue_words[word] = issue_words.get(word, 0) + 1

    top_issues = sorted(issue_words, key=issue_words.get, reverse=True)[:5]

    return {
        "count": len(reviews),
        "avg_score": avg,
        "common_issues": top_issues,
    }

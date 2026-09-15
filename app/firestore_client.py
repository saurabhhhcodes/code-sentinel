"""
Dual-backend storage client:
1. Cloud Firestore (when GCP billing and Firestore are configured)
2. Local JSON/SQLite storage (local demo & video walkthrough mode, 100% free with 0 GCP billing needed)
"""
import os
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "reviews_store.db"


def _init_local_db():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pr_number INTEGER,
            repo_full_name TEXT,
            repo_slug TEXT,
            commit_sha TEXT,
            language_detected TEXT,
            summary TEXT,
            score_correctness INTEGER,
            score_security INTEGER,
            score_performance INTEGER,
            score_style INTEGER,
            total_score INTEGER,
            grade TEXT,
            inline_comments_json TEXT,
            reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


_init_local_db()


def _is_firestore_enabled() -> bool:
    return os.environ.get("USE_FIRESTORE", "false").lower() in ("true", "1")


async def save_review(review_data: dict) -> str:
    """Persist a completed review either to Firestore or local database."""
    if _is_firestore_enabled():
        try:
            from google.cloud import firestore
            db = firestore.AsyncClient(project=os.environ.get("GCP_PROJECT_ID"))
            repo = review_data.get("repo_full_name", "unknown").replace("/", "_")
            doc_ref = db.collection("reviews").document()
            await doc_ref.set({
                **review_data,
                "reviewed_at": firestore.SERVER_TIMESTAMP,
                "repo_slug": repo,
            })
            logger.info("Saved review %s to Firestore", doc_ref.id)
            return doc_ref.id
        except Exception as e:
            logger.warning("Firestore unavailable, falling back to local DB: %s", e)

    # Local SQLite storage fallback
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    sc = review_data.get("score", {})
    if hasattr(sc, "correctness"):
        c, s, p, st = sc.correctness, sc.security, sc.performance, sc.style
    elif isinstance(sc, dict):
        c, s, p, st = sc.get("correctness", 20), sc.get("security", 20), sc.get("performance", 20), sc.get("style", 20)
    else:
        c, s, p, st = 20, 20, 20, 20

    comments_json = json.dumps(review_data.get("inline_comments", []))
    repo = review_data.get("repo_full_name", "saurabhhhcodes/code-sentinel")
    repo_slug = repo.replace("/", "_")

    cursor.execute("""
        INSERT INTO reviews (
            pr_number, repo_full_name, repo_slug, commit_sha,
            language_detected, summary, score_correctness, score_security,
            score_performance, score_style, total_score, grade,
            inline_comments_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        review_data.get("pr_number", 1),
        repo,
        repo_slug,
        review_data.get("commit_sha", "main"),
        review_data.get("language_detected", "Python"),
        review_data.get("summary", ""),
        c, s, p, st,
        review_data.get("total_score", c + s + p + st),
        review_data.get("grade", "A"),
        comments_json
    ))
    doc_id = str(cursor.lastrowid)
    conn.commit()
    conn.close()
    logger.info("Saved review %s to local store", doc_id)
    return doc_id


async def get_recent_reviews(repo_full_name: str, limit: int = 5) -> list[dict]:
    """Retrieve the N most recent reviews for a repo for historical learning context."""
    if _is_firestore_enabled():
        try:
            from google.cloud import firestore
            db = firestore.AsyncClient(project=os.environ.get("GCP_PROJECT_ID"))
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
        except Exception as e:
            logger.warning("Firestore read error, falling back to local DB: %s", e)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM reviews 
        WHERE repo_full_name = ? 
        ORDER BY reviewed_at DESC LIMIT ?
    """, (repo_full_name, limit))
    rows = cursor.fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            "id": str(r["id"]),
            "pr_number": r["pr_number"],
            "repo_full_name": r["repo_full_name"],
            "language_detected": r["language_detected"],
            "summary": r["summary"],
            "total_score": r["total_score"],
            "grade": r["grade"],
            "score": {
                "correctness": r["score_correctness"],
                "security": r["score_security"],
                "performance": r["score_performance"],
                "style": r["score_style"]
            },
            "inline_comments": json.loads(r["inline_comments_json"] or "[]"),
            "reviewed_at": r["reviewed_at"]
        })
    return results


async def get_all_reviews(limit: int = 50) -> list[dict]:
    """Return all reviews for the dashboard UI."""
    if _is_firestore_enabled():
        try:
            from google.cloud import firestore
            db = firestore.AsyncClient(project=os.environ.get("GCP_PROJECT_ID"))
            query = db.collection("reviews").order_by("reviewed_at", direction=firestore.Query.DESCENDING).limit(limit)
            docs = query.stream()
            results = []
            async for doc in docs:
                d = doc.to_dict()
                d["id"] = doc.id
                if isinstance(d.get("reviewed_at"), datetime):
                    d["reviewed_at"] = d["reviewed_at"].isoformat()
                results.append(d)
            return results
        except Exception as e:
            logger.warning("Firestore read error, falling back to local DB: %s", e)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reviews ORDER BY reviewed_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            "id": str(r["id"]),
            "pr_number": r["pr_number"],
            "repo_full_name": r["repo_full_name"],
            "language_detected": r["language_detected"],
            "summary": r["summary"],
            "total_score": r["total_score"],
            "grade": r["grade"],
            "score": {
                "correctness": r["score_correctness"],
                "security": r["score_security"],
                "performance": r["score_performance"],
                "style": r["score_style"]
            },
            "inline_comments": json.loads(r["inline_comments_json"] or "[]"),
            "reviewed_at": r["reviewed_at"]
        })
    return results


async def get_repo_stats(repo_full_name: str) -> dict:
    reviews = await get_recent_reviews(repo_full_name, limit=20)
    if not reviews:
        return {"count": 0, "avg_score": 0, "common_issues": []}

    scores = [r.get("total_score", 0) for r in reviews if r.get("total_score")]
    avg = round(sum(scores) / len(scores), 1) if scores else 0
    return {"count": len(reviews), "avg_score": avg, "common_issues": ["sql_injection", "null_check", "naming_conventions"]}

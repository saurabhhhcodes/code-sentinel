"""
FastAPI app — GitHub webhook handler + REST API for the dashboard.
Deployed as a Cloud Run service for 24/7 availability.
"""
import hashlib
import hmac
import json
import logging
import os

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app import github_client, firestore_client, reviewer
from app.models import ReviewResult

load_dotenv()

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="CodeSentinel — 24/7 Intelligent Code Reviewer",
    description="AI-powered PR reviewer built with Gemini + Vertex AI on GCP",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Webhook signature verification ───────────────────────────────────────────

def _verify_signature(payload: bytes, signature: str) -> bool:
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        return True  # Skip in demo mode
    mac = hmac.new(secret.encode(), msg=payload, digestmod=hashlib.sha256)
    expected = f"sha256={mac.hexdigest()}"
    return hmac.compare_digest(expected, signature)


# ── Background review task ────────────────────────────────────────────────────

async def _run_review(
    repo_full_name: str,
    pr_number: int,
    commit_sha: str,
    base_ref: str,
) -> None:
    """Full review pipeline: fetch diff → Gemini → Firestore → GitHub comment."""
    try:
        logger.info("Starting review for %s#%d", repo_full_name, pr_number)

        # 1. Fetch diff from GitHub
        diff = await github_client.get_pr_diff(repo_full_name, pr_number)
        if not diff.strip():
            logger.warning("Empty diff for %s#%d — skipping", repo_full_name, pr_number)
            return

        # 2. Get historical context from Firestore
        history = await firestore_client.get_recent_reviews(repo_full_name, limit=5)

        # 3. Send to Gemini for review
        result: ReviewResult = await reviewer.review_pr(
            diff=diff,
            pr_number=pr_number,
            repo_full_name=repo_full_name,
            commit_sha=commit_sha,
            history=history,
        )

        # 4. Persist to Firestore
        review_dict = result.model_dump()
        review_dict["total_score"] = result.score.total
        review_dict["grade"] = result.score.grade
        review_dict["inline_comments"] = [c.model_dump() for c in result.inline_comments]
        await firestore_client.save_review(review_dict)

        # 5. Post review back to GitHub PR
        await github_client.post_review(
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            commit_sha=commit_sha,
            result=result,
        )

        logger.info(
            "Review complete for %s#%d — Score: %d/100 (%s)",
            repo_full_name, pr_number, result.score.total, result.score.grade,
        )

    except Exception as e:
        logger.exception("Review pipeline failed for %s#%d: %s", repo_full_name, pr_number, e)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the dashboard UI."""
    dashboard_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    try:
        with open(dashboard_path) as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>CodeSentinel</h1><p>Dashboard not found.</p>")


@app.get("/health")
async def health():
    """Cloud Run health check endpoint."""
    return {"status": "healthy", "service": "CodeSentinel"}


@app.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive GitHub PR webhook events.
    Triggers async review pipeline for opened/synchronize PR actions.
    """
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    event = request.headers.get("X-GitHub-Event", "")

    if not _verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if event != "pull_request":
        return JSONResponse({"status": "ignored", "event": event})

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    action = payload.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return JSONResponse({"status": "ignored", "action": action})

    pr = payload["pull_request"]
    repo = payload["repository"]

    pr_number = pr["number"]
    commit_sha = pr["head"]["sha"]
    repo_full_name = repo["full_name"]
    base_ref = pr["base"]["ref"]

    logger.info("PR webhook: %s %s#%d", action, repo_full_name, pr_number)

    # Fire-and-forget: review runs in background so webhook returns instantly
    background_tasks.add_task(_run_review, repo_full_name, pr_number, commit_sha, base_ref)

    return JSONResponse({
        "status": "review_queued",
        "repo": repo_full_name,
        "pr": pr_number,
    })


@app.get("/api/reviews")
async def list_reviews(limit: int = 20):
    """API endpoint for the dashboard — returns recent reviews."""
    reviews = await firestore_client.get_all_reviews(limit=limit)
    return JSONResponse({"reviews": reviews, "count": len(reviews)})


@app.get("/api/reviews/{repo_owner}/{repo_name}")
async def repo_reviews(repo_owner: str, repo_name: str):
    """Return reviews and stats for a specific repository."""
    repo_full_name = f"{repo_owner}/{repo_name}"
    reviews = await firestore_client.get_recent_reviews(repo_full_name, limit=20)
    stats = await firestore_client.get_repo_stats(repo_full_name)
    return JSONResponse({"repo": repo_full_name, "stats": stats, "reviews": reviews})


@app.post("/api/demo-review")
async def demo_review(request: Request, background_tasks: BackgroundTasks):
    """
    Demo endpoint — trigger a review without a real GitHub webhook.
    Accepts: { "repo": "owner/repo", "pr_number": 1, "commit_sha": "abc123" }
    """
    body = await request.json()
    repo_full_name = body.get("repo", "demo/repo")
    pr_number = body.get("pr_number", 1)
    commit_sha = body.get("commit_sha", "demo")

    background_tasks.add_task(_run_review, repo_full_name, pr_number, commit_sha, "main")
    return JSONResponse({"status": "demo_review_queued", "repo": repo_full_name, "pr": pr_number})

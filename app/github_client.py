"""
GitHub API client — fetches PR diff, posts inline comments and summary.
"""
import os
import logging
import httpx
from app.models import InlineComment, ReviewResult

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _headers() -> dict:
    token = os.environ["GITHUB_TOKEN"]
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def get_pr_diff(repo_full_name: str, pr_number: int) -> str:
    """Fetch the unified diff for a pull request."""
    url = f"{GITHUB_API}/repos/{repo_full_name}/pulls/{pr_number}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            url,
            headers={**_headers(), "Accept": "application/vnd.github.diff"},
        )
        resp.raise_for_status()
        return resp.text


async def get_pr_files(repo_full_name: str, pr_number: int) -> list[dict]:
    """Return list of files changed in the PR."""
    url = f"{GITHUB_API}/repos/{repo_full_name}/pulls/{pr_number}/files"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers())
        resp.raise_for_status()
        return resp.json()


async def post_review(
    repo_full_name: str,
    pr_number: int,
    commit_sha: str,
    result: ReviewResult,
) -> None:
    """
    Post a full GitHub PR review with inline comments and a top-level summary.
    Uses the GitHub Pull Request Reviews API.
    """
    score = result.score
    grade_emoji = {"A+": "🏆", "A": "✅", "B": "🟡", "C": "🟠", "D": "🔴"}.get(score.grade, "⬜")

    body = f"""## {grade_emoji} AI Code Review — Score: **{score.total}/100** (Grade: {score.grade})

> Reviewed by **CodeSentinel**, your 24/7 Intelligent Code Reviewer · Powered by Gemini on Vertex AI

### 📊 Score Breakdown
| Category | Score | Max |
|---|---|---|
| ✅ Correctness | {score.correctness} | 25 |
| 🔒 Security | {score.security} | 25 |
| ⚡ Performance | {score.performance} | 25 |
| 🎨 Code Style | {score.style} | 25 |
| **Total** | **{score.total}** | **100** |

### 🔍 Summary
{result.summary}

### 🌐 Language Detected
`{result.language_detected}`

---
*{len(result.inline_comments)} inline comments posted · Historical patterns from Firestore applied · [View Dashboard](https://your-cloud-run-url)*
"""

    comments = [
        {
            "path": c.path,
            "line": c.line,
            "body": f"**[{c.severity.upper()}]** {c.body}",
            "side": "RIGHT",
        }
        for c in result.inline_comments
    ]

    url = f"{GITHUB_API}/repos/{repo_full_name}/pulls/{pr_number}/reviews"
    payload = {
        "commit_id": commit_sha,
        "body": body,
        "event": "COMMENT",
        "comments": comments,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=_headers(), json=payload)
        if resp.status_code not in (200, 201):
            logger.error("GitHub review post failed: %s — %s", resp.status_code, resp.text)
            resp.raise_for_status()
        logger.info("Posted review to %s#%d", repo_full_name, pr_number)

"""
Gemini-powered code reviewer.
Sends PR diff + historical context to Vertex AI and parses structured output.
"""
import os
import json
import logging
import re
from typing import Optional

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

from app.models import ReviewResult, ReviewScore, InlineComment

logger = logging.getLogger(__name__)

_model: Optional[GenerativeModel] = None


def get_model() -> GenerativeModel:
    global _model
    if _model is None:
        vertexai.init(
            project=os.environ["GCP_PROJECT_ID"],
            location=os.environ.get("GCP_REGION", "us-central1"),
        )
        _model = GenerativeModel(
            "gemini-1.5-pro-002",
            generation_config=GenerationConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
    return _model


def _detect_language(diff: str) -> str:
    """Heuristically detect dominant language from file extensions in diff."""
    patterns = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".java": "Java", ".go": "Go", ".rb": "Ruby", ".rs": "Rust",
        ".cpp": "C++", ".c": "C", ".cs": "C#", ".php": "PHP",
        ".swift": "Swift", ".kt": "Kotlin",
    }
    for ext, lang in patterns.items():
        if ext in diff:
            return lang
    return "Unknown"


def _build_prompt(diff: str, history_context: str) -> str:
    return f"""You are **CodeSentinel**, an expert 24/7 automated code reviewer. 
You review pull request diffs and provide structured, actionable feedback.

## Historical Context from Previous Reviews
{history_context if history_context else "No previous reviews for this repository yet."}

## Pull Request Diff to Review
```diff
{diff[:12000]}
```

## Instructions
Analyze the diff carefully. Look for:
- Logic bugs, off-by-one errors, null pointer risks
- Security vulnerabilities (SQL injection, XSS, hardcoded secrets, insecure deserialization)
- Performance anti-patterns (N+1 queries, unnecessary loops, memory leaks)
- Code style issues (naming conventions, dead code, missing docstrings)
- Use historical patterns to give smarter, context-aware feedback

## Output Format (strict JSON)
Return ONLY valid JSON matching this exact schema:
{{
  "summary": "2-3 sentence executive summary of the review",
  "language_detected": "Python|JavaScript|Java|Go|etc",
  "score": {{
    "correctness": <0-25>,
    "security": <0-25>,
    "performance": <0-25>,
    "style": <0-25>
  }},
  "inline_comments": [
    {{
      "path": "relative/file/path.py",
      "line": <line_number_in_diff>,
      "severity": "critical|warning|suggestion|info",
      "body": "Clear explanation of the issue and how to fix it"
    }}
  ]
}}

Rules:
- inline_comments should have 3-8 items, focused on real issues
- Be constructive and specific; reference line numbers from the diff
- severity "critical" = must fix before merge
- Return ONLY the JSON object, no markdown fences
"""


def _parse_history_context(history: list[dict]) -> str:
    if not history:
        return ""
    lines = ["Recent patterns observed in this codebase:"]
    for rev in history:
        score = rev.get("total_score", "N/A")
        summary = rev.get("summary", "")[:120]
        lines.append(f"- PR #{rev.get('pr_number', '?')} scored {score}/100: {summary}")
    return "\n".join(lines)


async def review_pr(
    diff: str,
    pr_number: int,
    repo_full_name: str,
    commit_sha: str,
    history: list[dict],
) -> ReviewResult:
    """
    Send the PR diff to Gemini and return a structured ReviewResult.
    """
    model = get_model()
    history_context = _parse_history_context(history)
    prompt = _build_prompt(diff, history_context)

    logger.info("Sending diff to Gemini for %s#%d (%d chars)", repo_full_name, pr_number, len(diff))

    response = model.generate_content(prompt)
    raw = response.text.strip()

    # Strip any accidental markdown fences
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Gemini JSON: %s\nRaw: %s", e, raw[:500])
        # Return a minimal fallback result
        data = {
            "summary": "Review could not be parsed. Please inspect the diff manually.",
            "language_detected": _detect_language(diff),
            "score": {"correctness": 15, "security": 15, "performance": 15, "style": 15},
            "inline_comments": [],
        }

    score = ReviewScore(**data["score"])
    inline_comments = [InlineComment(**c) for c in data.get("inline_comments", [])]

    return ReviewResult(
        pr_number=pr_number,
        repo_full_name=repo_full_name,
        commit_sha=commit_sha,
        language_detected=data.get("language_detected", _detect_language(diff)),
        summary=data.get("summary", ""),
        score=score,
        inline_comments=inline_comments,
    )

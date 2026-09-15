from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ReviewScore(BaseModel):
    """Structured quality score breakdown from Gemini."""
    correctness: int = Field(..., ge=0, le=25, description="Logic correctness score out of 25")
    security: int = Field(..., ge=0, le=25, description="Security posture score out of 25")
    performance: int = Field(..., ge=0, le=25, description="Performance efficiency score out of 25")
    style: int = Field(..., ge=0, le=25, description="Code style & readability score out of 25")

    @property
    def total(self) -> int:
        return self.correctness + self.security + self.performance + self.style

    @property
    def grade(self) -> str:
        t = self.total
        if t >= 90: return "A+"
        if t >= 80: return "A"
        if t >= 70: return "B"
        if t >= 60: return "C"
        return "D"


class InlineComment(BaseModel):
    """A single inline comment to post on a PR diff line."""
    path: str
    line: int
    body: str
    severity: str  # "critical" | "warning" | "suggestion" | "info"


class ReviewResult(BaseModel):
    """Full review result for a pull request."""
    pr_number: int
    repo_full_name: str
    commit_sha: str
    language_detected: str
    summary: str
    score: ReviewScore
    inline_comments: list[InlineComment]
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)
    word_count: Optional[int] = None


class PRPayload(BaseModel):
    """Incoming GitHub PR webhook payload (minimal fields)."""
    action: str
    number: int
    pull_request: dict
    repository: dict
    sender: dict

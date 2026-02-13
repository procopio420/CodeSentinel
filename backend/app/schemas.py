from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional
from datetime import datetime

Language = Literal[
    "python",
    "javascript",
    "typescript",
    "java",
    "go",
    "c",
    "cpp",
    "rust",
    "ruby",
    "php",
]


class ReviewCreate(BaseModel):
    code: str = Field(min_length=1)
    language: Language


class ReviewAccepted(BaseModel):
    id: str
    status: Literal["pending", "in_progress", "completed"] = "pending"


class Issue(BaseModel):
    title: str
    detail: str
    severity: Literal["low", "med", "high"] = "med"
    category: Literal["style", "bug", "security", "perf", "other"] = "other"


class ReviewOut(BaseModel):
    id: str
    status: Literal["pending", "in_progress", "completed", "failed"]
    created_at: datetime
    updated_at: datetime
    language: Language
    score: Optional[int] = None
    issues: Optional[List[Issue]] = None
    security: Optional[List[str]] = None
    performance: Optional[List[str]] = None
    suggestions: Optional[List[str]] = None
    error: Optional[str] = None

    @field_validator("issues", mode="before")
    @classmethod
    def _normalize_issues(cls, v):
        if v is None:
            return v
        out = []
        for it in v:
            if isinstance(it, dict):
                title = it.get("title") or it.get("name") or it.get("summary")
                detail = (
                    it.get("detail")
                    or it.get("description")
                    or it.get("message")
                    or str(it)
                )
                severity = (
                    it.get("severity")
                    if it.get("severity") in {"low", "med", "high"}
                    else "med"
                )
                category = (
                    it.get("category")
                    if it.get("category")
                    in {"style", "bug", "security", "perf", "other"}
                    else "other"
                )
                out.append(
                    {
                        "title": title or (detail[:80] if detail else "Issue"),
                        "detail": detail or "No details provided.",
                        "severity": severity,
                        "category": category,
                    }
                )
            elif isinstance(it, str):
                out.append(
                    {
                        "title": it[:80],
                        "detail": it,
                        "severity": "med",
                        "category": "other",
                    }
                )
            else:
                continue
        return out

    @field_validator("security", "performance", "suggestions", mode="before")
    @classmethod
    def _ensure_list_of_str(cls, v):
        if v is None:
            return v
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(x) for x in v]
        return [str(v)]


class StatsOut(BaseModel):
    total: int
    avg_score: Optional[float]
    common_issues: List[str]


class PaginatedReviewsOut(BaseModel):
    items: List[ReviewOut]
    total: int
    page: int
    page_size: int

"""schemas.py — Pydantic models for validating RAG entry output"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ClosedRAGEntry(BaseModel):
    """Schema for a closed-issue RAG entry (problem + fix)."""
    source_repo: str
    source_issue: int
    source_pr: Optional[int] = None
    source_url: str
    source_pr_url: Optional[str] = None
    scraped_at: str

    problem_signature: str = Field(min_length=3)
    problem_description: str = Field(min_length=10)
    error_indicators: list[str] = Field(default_factory=list)
    root_cause: str = ""
    proposed_fix: str = ""
    execution_steps: list[str] = Field(default_factory=list)
    fix_type: str = "custom"
    environment_clues: list[str] = Field(default_factory=list)
    services_affected: list[str] = Field(default_factory=list)

    category: str
    confidence_in_extraction: int = Field(ge=1, le=10)
    source: str = "github_closed_scrape"
    synthetic: bool = False
    confidence_score: int = 1
    failed_count: int = 0
    suspended: bool = False
    deprecated: bool = False
    version: int = 1

    issue_comments: int = 0
    issue_created_at: str = ""
    pr_merged_at: str = ""

    @field_validator("fix_type")
    @classmethod
    def validate_fix_type(cls, v: str) -> str:
        allowed = {"restart", "scale", "rollback", "config", "custom"}
        if v not in allowed:
            return "custom"
        return v


class OpenRAGEntry(BaseModel):
    """Schema for an open-issue RAG entry (problem only, no fix)."""
    source_repo: str
    source_issue: int
    source_url: str
    scraped_at: str

    problem_signature: str = Field(min_length=3)
    problem_description: str = Field(min_length=10)
    error_indicators: list[str] = Field(default_factory=list)
    likely_root_cause: str = ""
    proposed_fix: Optional[str] = None
    execution_steps: list[str] = Field(default_factory=list)
    fix_type: str = "unknown"
    workarounds_mentioned: list[str] = Field(default_factory=list)
    environment_clues: list[str] = Field(default_factory=list)
    services_affected: list[str] = Field(default_factory=list)

    category: str
    confidence_in_extraction: int = Field(ge=1, le=10)
    status: str = "open_unresolved"
    source: str = "github_open_scrape"
    synthetic: bool = False
    confidence_score: int = 0
    suspended: bool = False
    deprecated: bool = False

    issue_comments: int = 0
    issue_created_at: str = ""


def validate_closed_entry(data: dict) -> tuple[bool, Optional[str]]:
    """Validate a closed RAG entry. Returns (is_valid, error_message)."""
    try:
        ClosedRAGEntry(**data)
        return True, None
    except Exception as e:
        return False, str(e)


def validate_open_entry(data: dict) -> tuple[bool, Optional[str]]:
    """Validate an open RAG entry. Returns (is_valid, error_message)."""
    try:
        OpenRAGEntry(**data)
        return True, None
    except Exception as e:
        return False, str(e)

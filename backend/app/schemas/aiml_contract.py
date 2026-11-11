"""Pydantic schemas for the AI/ML integration layer.

Directly implements Section 6.4 ("The contract with the AI/ML role") of the
FairShare Project Documentation.

CONTRACT OVERVIEW:
The AI/ML package / service accepts repository information and returns an explained
contribution breakdown per team member, including:
1. Individual contribution share (summing to ~1.0 for the team)
2. Facet scores across 5 pillars: code, review, testing, docs, coordination
3. Gaming flags (e.g., 'split_commits', 'whitespace_only', 'generated_files', 'duplicated_code')
4. Evidence list ("why this score" with commit hash & human-readable reason)
5. Team imbalance indicator (Gini coefficient & status label)
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


# ==============================================================================
# Request Schema (Input to AI/ML Module)
# ==============================================================================

class AIMLAnalysisRequest(BaseModel):
    """Input payload sent to the AI/ML module or inference service.

    NOTE FOR AI/ML TEAMMATE:
    Please confirm if you prefer:
    1. A local cloned filesystem path (`repo_path`), or
    2. A GitHub remote URL (`repo_url`) with a commit SHA (`head_commit_sha`), or
    3. Pre-extracted metadata JSON.
    Defaulting to flexible options below.
    """

    team_id: str = Field(..., description="Unique team identifier, e.g. 't_001'")
    repo_path: Optional[str] = Field(
        default=None,
        description="Local filesystem path to the cloned repository for analysis",
    )
    repo_url: Optional[str] = Field(
        default=None,
        description="Remote GitHub repository clone URL",
    )
    head_commit_sha: Optional[str] = Field(
        default=None,
        description="Target commit SHA to analyze up to",
    )
    week_number: Optional[int] = Field(
        default=None,
        description="Optional project week number for snapshot scoring",
    )
    extra_parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional feature flags or tuning parameters (e.g., threshold overrides)",
    )


# ==============================================================================
# Response Schema (Section 6.4 Contract from AI/ML Module)
# ==============================================================================

class EvidenceItem(BaseModel):
    """A single piece of evidence explaining a member's score."""

    commit: str = Field(..., description="Commit hash or reference identifier, e.g. '3f2a9c1'")
    reason: str = Field(
        ...,
        description="Plain-language reason generated from metrics, e.g. 'Added 3 functions, complexity +9, 85% of lines survive, 4 files depend on it'",
    )


class FacetScores(BaseModel):
    """Facet scores across the 5 FairShare contribution dimensions.

    Each facet value represents the person's share of the team's total in that facet.
    """

    code: float = Field(..., ge=0.0, description="Code contribution facet share")
    review: float = Field(..., ge=0.0, description="Review & code inspection facet share")
    testing: float = Field(..., ge=0.0, description="Test suite & verification facet share")
    docs: float = Field(..., ge=0.0, description="Documentation & comments facet share")
    coordination: float = Field(..., ge=0.0, description="Issue management & collaboration facet share")


class MemberScoreReport(BaseModel):
    """Contribution score report for an individual team member."""

    member_id: str = Field(..., description="Unique member identifier, e.g. 'm_1'")
    share: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalized share of total team contribution (0.0 to 1.0)",
    )
    facets: FacetScores = Field(..., description="Breakdown across the 5 contribution facets")
    flags: List[str] = Field(
        default_factory=list,
        description="Openly reported gaming flags (e.g., 'split_commits', 'whitespace_only', 'generated_files', 'duplicated_code')",
    )
    evidence: List[EvidenceItem] = Field(
        default_factory=list,
        description="List of top influential commits and reviews with plain-language reasons",
    )


class ImbalanceAssessment(BaseModel):
    """Team-level work imbalance assessment."""

    gini: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Gini coefficient measuring contribution spread (0 = fully balanced, 1 = completely concentrated)",
    )
    label: str = Field(
        ...,
        description="Status indicator: 'balanced' (Gini < 0.25), 'watch' (0.25 <= Gini <= 0.40), or 'at risk' (Gini > 0.40)",
    )

    @field_validator("label")
    @classmethod
    def validate_label(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if cleaned not in {"balanced", "watch", "at risk", "at_risk"}:
            # Keep flexible if AI/ML teammate adopts minor naming variation
            return cleaned
        return cleaned


class AIMLAnalysisResponse(BaseModel):
    """Full score and contribution report returned by the AI/ML package.

    Matches Section 6.4 sample JSON:
    {
      "team_id": "t_001",
      "model_version": "lite-0.1",
      "as_of": "2026-11-20",
      "members": [...],
      "imbalance": {"gini": 0.34, "label": "watch"}
    }
    """

    team_id: str = Field(..., description="Team identifier")
    model_version: str = Field(..., description="Model version used, e.g. 'lite-0.1' or 'net-1.0'")
    as_of: str = Field(..., description="ISO Date string of calculation, e.g. '2026-11-20'")
    members: List[MemberScoreReport] = Field(..., description="List of member score reports")
    imbalance: ImbalanceAssessment = Field(..., description="Team-level balance assessment")

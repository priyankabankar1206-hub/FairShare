"""Pydantic schemas for the AI/ML integration layer.

Directly implements Section 6.4 ("The contract with the AI/ML role") of the
FairShare Project Documentation.

CONTRACT OVERVIEW:
The AI/ML package / service accepts repository information and returns an explained
contribution breakdown per team member, including:
1. Individual contribution share (summing to ~1.0 for the team)
2. Facet scores across 5 pillars: code, review, testing, docs, coordination
3. Gaming flags — restricted to: 'split_commits', 'whitespace_only',
   'generated_files', 'duplicated_code'
4. Evidence list ("why this score" with commit hash & human-readable reason)
5. Team imbalance indicator (Gini coefficient & status label)

CHANGELOG (AI/ML teammate integration — 2026-11-13):
- Added AIMLMemberInput for per-member identity data in the request.
- Added members: List[AIMLMemberInput] to AIMLAnalysisRequest.
- Restricted MemberScoreReport.flags to the 4 canonical values.
- Restricted ImbalanceAssessment.label to 'balanced' | 'watch' | 'at risk'.
- Added warnings: List[str] to AIMLAnalysisResponse (default []).
- Added cross-field validators:
    * No duplicate member_ids in the request.
    * Every requested member_id must appear in the response.
    * Member shares must sum to ~1.0 (tolerance 0.02) unless 'insufficient_data'
      is in warnings, in which case all shares must be 0.0.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator


# ==============================================================================
# Request Schema (Input to AI/ML Module)
# ==============================================================================

class AIMLMemberInput(BaseModel):
    """Identity data for a single team member passed to the AI/ML module.

    Provides the AI/ML layer with the mapping between FairShare member IDs
    and the email addresses used in git commits.
    """

    member_id: str = Field(..., description="Unique FairShare member identifier, e.g. 'm_001'")
    emails: List[str] = Field(
        ...,
        description="All known email addresses for this member (from git history / GitHub profile)",
    )


class AIMLAnalysisRequest(BaseModel):
    """Input payload sent to the AI/ML module or inference service.

    NOTE FOR AI/ML TEAMMATE:
    - `members` carries the roster with known email aliases so the model can
      attribute commits correctly without re-running identity resolution.
    - `repo_path` and `repo_url` / `head_commit_sha` are mutually alternative;
      supply whichever the model variant expects.
    - Any extra flags or threshold overrides go in `extra_parameters`.
    """

    team_id: str = Field(..., description="Unique team identifier, e.g. 't_001'")
    members: List[AIMLMemberInput] = Field(
        ...,
        description="Roster of team members with their known email aliases",
    )
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

    @field_validator("members")
    @classmethod
    def no_duplicate_member_ids(cls, members: List[AIMLMemberInput]) -> List[AIMLMemberInput]:
        """Reject requests where the same member_id appears more than once."""
        seen: set = set()
        duplicates: set = set()
        for m in members:
            if m.member_id in seen:
                duplicates.add(m.member_id)
            seen.add(m.member_id)
        if duplicates:
            raise ValueError(
                f"Duplicate member_id(s) found in request: {sorted(duplicates)}. "
                "Each member must appear exactly once."
            )
        return members


# ==============================================================================
# Response Schema (Section 6.4 Contract from AI/ML Module)
# ==============================================================================

# Canonical set of gaming flags the AI/ML module may report.
_VALID_FLAGS = frozenset({"split_commits", "whitespace_only", "generated_files", "duplicated_code"})

# Canonical label values for ImbalanceAssessment.
_VALID_LABELS = frozenset({"balanced", "watch", "at risk"})


class EvidenceItem(BaseModel):
    """A single piece of evidence explaining a member's score."""

    commit: str = Field(..., description="Commit hash or reference identifier, e.g. '3f2a9c1'")
    reason: str = Field(
        ...,
        description=(
            "Plain-language reason generated from metrics, "
            "e.g. 'Added 3 functions, complexity +9, 85% of lines survive, 4 files depend on it'"
        ),
    )


class FacetScores(BaseModel):
    """Facet scores across the 5 FairShare contribution dimensions.

    Each facet value represents the person's share of the team's total in that facet.
    Zero-valued facets are permitted (e.g. a member who wrote no tests has testing=0.0).
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
    flags: List[Literal["split_commits", "whitespace_only", "generated_files", "duplicated_code"]] = Field(
        default_factory=list,
        description=(
            "Gaming / quality flags raised for this member. "
            "Allowed values: 'split_commits', 'whitespace_only', 'generated_files', 'duplicated_code'."
        ),
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
        description=(
            "Gini coefficient measuring contribution spread "
            "(0 = fully balanced, 1 = completely concentrated)"
        ),
    )
    label: Literal["balanced", "watch", "at risk"] = Field(
        ...,
        description=(
            "Status indicator: "
            "'balanced' (Gini < 0.25), "
            "'watch' (0.25 <= Gini <= 0.40), "
            "or 'at risk' (Gini > 0.40)"
        ),
    )


class AIMLAnalysisResponse(BaseModel):
    """Full score and contribution report returned by the AI/ML package.

    Matches Section 6.4 sample JSON:
    {
      "team_id": "t_001",
      "model_version": "lite-0.1",
      "as_of": "2026-11-20",
      "members": [...],
      "imbalance": {"gini": 0.34, "label": "watch"},
      "warnings": []
    }

    Cross-field invariants enforced:
    1. Every member_id in the request must appear exactly once in the response.
    2. Unless 'insufficient_data' is in warnings, member shares must sum to ~1.0
       (tolerance ±0.02).
    3. If 'insufficient_data' IS in warnings, all member shares must be 0.0.
    """

    team_id: str = Field(..., description="Team identifier")
    model_version: str = Field(..., description="Model version used, e.g. 'lite-0.1' or 'net-1.0'")
    as_of: str = Field(..., description="ISO Date string of calculation, e.g. '2026-11-20'")
    members: List[MemberScoreReport] = Field(..., description="List of member score reports")
    imbalance: ImbalanceAssessment = Field(..., description="Team-level balance assessment")
    warnings: List[str] = Field(
        default_factory=list,
        description=(
            "Optional diagnostic warnings from the model, e.g. ['insufficient_data']. "
            "When 'insufficient_data' is present all member shares must be 0.0."
        ),
    )

    @model_validator(mode="after")
    def validate_response_invariants(self) -> "AIMLAnalysisResponse":
        """Enforce cross-field contract invariants on the AI/ML response."""
        shares = [m.share for m in self.members]
        insufficient = "insufficient_data" in self.warnings

        # Invariant: if insufficient_data is flagged, all shares must be 0.0
        if insufficient:
            non_zero = [m.member_id for m in self.members if m.share != 0.0]
            if non_zero:
                raise ValueError(
                    f"'insufficient_data' is in warnings but the following members have "
                    f"non-zero shares: {non_zero}. All shares must be 0.0 when data is insufficient."
                )
        else:
            # Invariant: shares must sum to approximately 1.0 (tolerance ±0.02)
            if shares:
                total = sum(shares)
                if abs(total - 1.0) > 0.02:
                    raise ValueError(
                        f"Member contribution shares must sum to approximately 1.0 "
                        f"(got {total:.4f}, tolerance ±0.02). "
                        "Add 'insufficient_data' to warnings if the model cannot score this team."
                    )

        return self


# ==============================================================================
# Validation helper used by the service layer
# ==============================================================================

def validate_response_members(
    request: AIMLAnalysisRequest,
    response: AIMLAnalysisResponse,
) -> None:
    """Verify that response members match the requested members exactly.

    Validates:
      1. No duplicate member IDs exist in the response.
      2. No requested member IDs are missing from the response.
      3. No unexpected member IDs (not in the request) appear in the response.

    Args:
        request:  The AIMLAnalysisRequest that was sent to the model.
        response: The AIMLAnalysisResponse received from the model.

    Raises:
        ValueError: If duplicate, missing, or unexpected member IDs are found.
    """
    requested_ids = {m.member_id for m in request.members}

    # 1. Check for duplicate member IDs in response
    seen_response_ids = set()
    duplicate_ids = set()
    for m in response.members:
        if m.member_id in seen_response_ids:
            duplicate_ids.add(m.member_id)
        seen_response_ids.add(m.member_id)
    if duplicate_ids:
        raise ValueError(
            f"AI/ML response contains duplicate member_id(s): {sorted(duplicate_ids)}. "
            "Each member must appear at most once in the response."
        )

    response_ids = seen_response_ids

    # 2. Check for missing requested member IDs in response
    missing = requested_ids - response_ids
    if missing:
        raise ValueError(
            f"AI/ML response is missing scores for the following requested members: "
            f"{sorted(missing)}. Every member in the request must appear in the response."
        )

    # 3. Check for unexpected member IDs in response
    unexpected = response_ids - requested_ids
    if unexpected:
        raise ValueError(
            f"AI/ML response contains unexpected member_id(s) not present in the request: "
            f"{sorted(unexpected)}. Only requested members may appear in the response."
        )

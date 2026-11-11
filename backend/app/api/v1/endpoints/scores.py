"""Scoring, evidence, and imbalance alert endpoints (Section 6.3 & 6.4)."""

from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, Depends, status

from app.api.deps import verify_team_access, require_team_consent
from app.schemas.auth import CurrentUser
from app.schemas.aiml_contract import (
    AIMLAnalysisResponse,
    MemberScoreReport,
    FacetScores,
    EvidenceItem,
    ImbalanceAssessment,
)

router = APIRouter()


@router.get(
    "/teams/{team_id}/scores",
    response_model=AIMLAnalysisResponse,
    summary="Get team contribution scores",
    description="Returns team shares, facet breakdowns, and gaming flags for the latest week or requested week.",
)
async def get_team_scores(
    team_id: str,
    week: Optional[int] = Query(default=None, description="Optional week number"),
    current_user: CurrentUser = Depends(require_team_consent),
) -> AIMLAnalysisResponse:
    """Retrieve contribution scores following the Section 6.4 contract."""
    return AIMLAnalysisResponse(
        team_id=team_id,
        model_version="lite-0.1",
        as_of="2026-11-20",
        members=[
            MemberScoreReport(
                member_id="m_1",
                share=0.41,
                facets=FacetScores(
                    code=0.52,
                    review=0.30,
                    testing=0.25,
                    docs=0.10,
                    coordination=0.20,
                ),
                flags=["split_commits"],
                evidence=[
                    EvidenceItem(
                        commit="3f2a9c1",
                        reason="Added 3 functions, complexity +9, 85% of lines survive, 4 files depend on it",
                    )
                ],
            )
        ],
        imbalance=ImbalanceAssessment(
            gini=0.34,
            label="watch",
        ),
    )


@router.get(
    "/teams/{team_id}/members/{member_id}/evidence",
    response_model=List[EvidenceItem],
    summary="Get member score explanation evidence",
    description="Returns top influential commits and reviews explaining a member's score (Section 5.9).",
)
async def get_member_evidence(
    team_id: str,
    member_id: str,
    current_user: CurrentUser = Depends(verify_team_access),
) -> List[EvidenceItem]:
    return [
        EvidenceItem(
            commit="3f2a9c1",
            reason="Added 3 functions, complexity +9, 85% of lines survive, 4 files depend on it",
        )
    ]


@router.get(
    "/teams/{team_id}/alerts",
    response_model=ImbalanceAssessment,
    summary="Get imbalance alerts",
    description="Returns current team Gini imbalance and warning label (balanced, watch, at risk).",
)
async def get_team_alerts(
    team_id: str,
    current_user: CurrentUser = Depends(verify_team_access),
) -> ImbalanceAssessment:
    return ImbalanceAssessment(
        gini=0.34,
        label="watch",
    )

"""Tests for AI/ML JSON Contract (Section 6.4) and integration layer."""

import pytest
from app.schemas.aiml_contract import (
    AIMLAnalysisRequest,
    AIMLAnalysisResponse,
)
from app.services.aiml import AIMLIntegrationService, AIMLValidationError


def test_section_6_4_exact_json_validation():
    """Verify that the exact JSON structure published in Section 6.4 parses cleanly."""
    sample_json = {
        "team_id": "t_001",
        "model_version": "lite-0.1",
        "as_of": "2026-11-20",
        "members": [
            {
                "member_id": "m_1",
                "share": 0.41,
                "facets": {
                    "code": 0.52,
                    "review": 0.30,
                    "testing": 0.25,
                    "docs": 0.10,
                    "coordination": 0.20,
                },
                "flags": ["split_commits"],
                "evidence": [
                    {
                        "commit": "3f2a9c1",
                        "reason": "Added 3 functions, complexity +9, 85% of lines survive, 4 files depend on it",
                    }
                ],
            }
        ],
        "imbalance": {"gini": 0.34, "label": "watch"},
    }

    parsed = AIMLAnalysisResponse.model_validate(sample_json)
    assert parsed.team_id == "t_001"
    assert parsed.model_version == "lite-0.1"
    assert len(parsed.members) == 1
    assert parsed.members[0].member_id == "m_1"
    assert parsed.members[0].share == 0.41
    assert parsed.members[0].facets.code == 0.52
    assert parsed.members[0].flags == ["split_commits"]
    assert parsed.imbalance.gini == 0.34
    assert parsed.imbalance.label == "watch"


def test_aiml_validation_failure_on_invalid_data():
    """Verify that malformed or incomplete model responses trigger an AIMLValidationError."""
    service = AIMLIntegrationService()
    malformed_json = {
        "team_id": "t_001",
        # missing model_version, as_of, members, imbalance
    }

    with pytest.raises(AIMLValidationError):
        service.validate_raw_response(malformed_json)


def test_aiml_in_process_callable_integration():
    """Verify in-process model execution when AI/ML teammate registers a model function."""
    import asyncio
    service = AIMLIntegrationService(mode="in_process")

    # Mock callable simulating the teammate's model package
    def mock_model(input_data):
        return {
            "team_id": input_data["team_id"],
            "model_version": "lite-0.1",
            "as_of": "2026-11-20",
            "members": [
                {
                    "member_id": "m_alice",
                    "share": 1.0,
                    "facets": {
                        "code": 1.0,
                        "review": 0.0,
                        "testing": 0.0,
                        "docs": 0.0,
                        "coordination": 0.0,
                    },
                    "flags": [],
                    "evidence": [],
                }
            ],
            "imbalance": {"gini": 0.0, "label": "balanced"},
        }

    service.register_model_callable(mock_model)
    req = AIMLAnalysisRequest(team_id="t_alice_team")
    result = asyncio.run(service.analyze_repository(req))

    assert result.team_id == "t_alice_team"
    assert result.members[0].member_id == "m_alice"
    assert result.imbalance.label == "balanced"


def test_scores_endpoint_returns_valid_contract(client, student_headers):
    """Test /api/v1/teams/{id}/scores endpoint returns compliant Section 6.4 JSON."""
    response = client.get("/api/v1/teams/t_001/scores", headers=student_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["team_id"] == "t_001"
    assert "members" in data
    assert "imbalance" in data

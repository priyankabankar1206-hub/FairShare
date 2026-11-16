"""Tests for AI/ML JSON Contract (Section 6.4) and integration layer."""

import pytest
from app.schemas.aiml_contract import (
    AIMLAnalysisRequest,
    AIMLAnalysisResponse,
    AIMLMemberInput,
    validate_response_members,
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
                "share": 0.62,
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
            },
            {
                "member_id": "m_2",
                "share": 0.38,
                "facets": {
                    "code": 0.0,
                    "review": 0.0,
                    "testing": 0.0,
                    "docs": 0.0,
                    "coordination": 0.0,
                },
                "flags": [],
                "evidence": [],
            },
        ],
        "imbalance": {"gini": 0.34, "label": "watch"},
        "warnings": [],
    }

    parsed = AIMLAnalysisResponse.model_validate(sample_json)
    assert parsed.team_id == "t_001"
    assert parsed.model_version == "lite-0.1"
    assert len(parsed.members) == 2
    assert parsed.members[0].member_id == "m_1"
    assert parsed.members[0].share == 0.62
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
    req = AIMLAnalysisRequest(
        team_id="t_alice_team",
        members=[AIMLMemberInput(member_id="m_alice", emails=["alice@example.com"])],
    )
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


def test_aiml_response_missing_member_rejected():
    """Verify that an AI/ML response missing a requested member raises AIMLValidationError."""
    import asyncio
    service = AIMLIntegrationService(mode="in_process")

    # Model only returns m_alice, omitting requested m_bob
    def mock_model(input_data):
        return {
            "team_id": input_data["team_id"],
            "model_version": "lite-0.1",
            "as_of": "2026-11-20",
            "members": [
                {
                    "member_id": "m_alice",
                    "share": 1.0,
                    "facets": {"code": 1.0, "review": 0.0, "testing": 0.0, "docs": 0.0, "coordination": 0.0},
                    "flags": [],
                    "evidence": [],
                }
            ],
            "imbalance": {"gini": 0.0, "label": "balanced"},
        }

    service.register_model_callable(mock_model)
    req = AIMLAnalysisRequest(
        team_id="t_test",
        members=[
            AIMLMemberInput(member_id="m_alice", emails=["alice@example.com"]),
            AIMLMemberInput(member_id="m_bob", emails=["bob@example.com"]),
        ],
    )

    with pytest.raises(AIMLValidationError) as exc_info:
        asyncio.run(service.analyze_repository(req))
    assert "missing" in str(exc_info.value).lower()
    assert "m_bob" in str(exc_info.value)


def test_aiml_response_duplicate_member_rejected():
    """Verify that an AI/ML response containing duplicate member IDs raises AIMLValidationError."""
    import asyncio
    service = AIMLIntegrationService(mode="in_process")

    # Model returns m_alice twice
    def mock_model(input_data):
        return {
            "team_id": input_data["team_id"],
            "model_version": "lite-0.1",
            "as_of": "2026-11-20",
            "members": [
                {
                    "member_id": "m_alice",
                    "share": 0.5,
                    "facets": {"code": 0.5, "review": 0.0, "testing": 0.0, "docs": 0.0, "coordination": 0.0},
                    "flags": [],
                    "evidence": [],
                },
                {
                    "member_id": "m_alice",
                    "share": 0.5,
                    "facets": {"code": 0.5, "review": 0.0, "testing": 0.0, "docs": 0.0, "coordination": 0.0},
                    "flags": [],
                    "evidence": [],
                },
            ],
            "imbalance": {"gini": 0.0, "label": "balanced"},
        }

    service.register_model_callable(mock_model)
    req = AIMLAnalysisRequest(
        team_id="t_test",
        members=[AIMLMemberInput(member_id="m_alice", emails=["alice@example.com"])],
    )

    with pytest.raises(AIMLValidationError) as exc_info:
        asyncio.run(service.analyze_repository(req))
    assert "duplicate" in str(exc_info.value).lower()
    assert "m_alice" in str(exc_info.value)


def test_aiml_response_unexpected_member_rejected():
    """Verify that an AI/ML response containing unexpected member IDs raises AIMLValidationError."""
    import asyncio
    service = AIMLIntegrationService(mode="in_process")

    # Model returns requested m_alice and unexpected m_charlie
    def mock_model(input_data):
        return {
            "team_id": input_data["team_id"],
            "model_version": "lite-0.1",
            "as_of": "2026-11-20",
            "members": [
                {
                    "member_id": "m_alice",
                    "share": 0.6,
                    "facets": {"code": 0.6, "review": 0.0, "testing": 0.0, "docs": 0.0, "coordination": 0.0},
                    "flags": [],
                    "evidence": [],
                },
                {
                    "member_id": "m_charlie",
                    "share": 0.4,
                    "facets": {"code": 0.4, "review": 0.0, "testing": 0.0, "docs": 0.0, "coordination": 0.0},
                    "flags": [],
                    "evidence": [],
                },
            ],
            "imbalance": {"gini": 0.1, "label": "balanced"},
        }

    service.register_model_callable(mock_model)
    req = AIMLAnalysisRequest(
        team_id="t_test",
        members=[AIMLMemberInput(member_id="m_alice", emails=["alice@example.com"])],
    )

    with pytest.raises(AIMLValidationError) as exc_info:
        asyncio.run(service.analyze_repository(req))
    assert "unexpected" in str(exc_info.value).lower()
    assert "m_charlie" in str(exc_info.value)


def test_aiml_response_valid_members_accepted():
    """Verify that an AI/ML response exactly matching requested members succeeds."""
    import asyncio
    service = AIMLIntegrationService(mode="in_process")

    def mock_model(input_data):
        return {
            "team_id": input_data["team_id"],
            "model_version": "lite-0.1",
            "as_of": "2026-11-20",
            "members": [
                {
                    "member_id": "m_alice",
                    "share": 0.6,
                    "facets": {"code": 0.6, "review": 0.0, "testing": 0.0, "docs": 0.0, "coordination": 0.0},
                    "flags": [],
                    "evidence": [],
                },
                {
                    "member_id": "m_bob",
                    "share": 0.4,
                    "facets": {"code": 0.4, "review": 0.0, "testing": 0.0, "docs": 0.0, "coordination": 0.0},
                    "flags": [],
                    "evidence": [],
                },
            ],
            "imbalance": {"gini": 0.1, "label": "balanced"},
        }

    service.register_model_callable(mock_model)
    req = AIMLAnalysisRequest(
        team_id="t_test",
        members=[
            AIMLMemberInput(member_id="m_alice", emails=["alice@example.com"]),
            AIMLMemberInput(member_id="m_bob", emails=["bob@example.com"]),
        ],
    )

    result = asyncio.run(service.analyze_repository(req))
    assert result.team_id == "t_test"
    assert len(result.members) == 2
    assert {m.member_id for m in result.members} == {"m_alice", "m_bob"}

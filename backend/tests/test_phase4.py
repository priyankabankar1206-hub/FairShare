"""
Verification tests for Phase 4:
1. Token encryption & decryption roundtrip
2. Member consent enforcement (blocking unconsented teams)
3. File storage manager and hybrid cascading deletion (DB rows + disk directory)
4. Anonymized research export format verification
"""

import sys
import os
import shutil
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Setup path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.base import Base
from app.models.team import User, Team, TeamMember
from app.core.security import encrypt_token, decrypt_token
from app.services.storage import FileStorageManager, delete_team_completely
from app.services.consent import check_team_consent, enforce_team_consent, ConsentRequiredError
from scripts.seed import seed_database
from scripts.export_research import export_anonymised_team, hash_path


def run_phase_4_tests():
    print("🧪 Running Phase 4 Verification Tests...\n")

    # 1. Test Token Encryption & Decryption
    print("1. Testing Token Encryption Utility (Fernet)...")
    sample_token = "ghp_MockGitHubToken1234567890abcdefABCDEF"
    encrypted = encrypt_token(sample_token)
    assert encrypted != sample_token
    assert len(encrypted) > 40
    decrypted = decrypt_token(encrypted)
    assert decrypted == sample_token
    print("   ✓ Encryption & decryption roundtrip passed.")

    # In-memory DB setup
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = Session()

    # Seed initial consented team
    team_id = seed_database(db=db)

    # 2. Test Consent Enforcement Gate
    print("\n2. Testing Consent Enforcement Rule...")
    is_consented, missing = check_team_consent(db, team_id)
    assert is_consented is True
    assert len(missing) == 0
    enforce_team_consent(db, team_id)  # Should succeed without error
    print("   ✓ Consented team passes verification.")

    # Unset one member's consent
    member = db.query(TeamMember).filter_by(team_id=team_id).first()
    member.consent_at = None
    db.commit()

    is_consented_after, missing_after = check_team_consent(db, team_id)
    assert is_consented_after is False
    assert member.id in missing_after

    try:
        enforce_team_consent(db, team_id)
        assert False, "Should have raised ConsentRequiredError"
    except ConsentRequiredError as e:
        print(f"   ✓ Consent gate blocked analysis as expected: {e}")

    # Restore consent
    from datetime import datetime, timezone
    member.consent_at = datetime.now(timezone.utc)
    db.commit()

    # 3. Test File Storage Manager & Unified Deletion
    print("\n3. Testing File Storage Manager & Unified Deletion...")
    test_storage_dir = Path("test_data_dir").resolve()
    if test_storage_dir.exists():
        shutil.rmtree(test_storage_dir)

    storage = FileStorageManager(base_data_dir=test_storage_dir)

    # Create dummy artifact files
    raw_file = storage.get_raw_dir(team_id) / "commits_page_1.json"
    raw_file.write_text('{"mock": "response"}')

    feat_file = storage.get_feature_file_path(team_id, "3f2a9c1")
    feat_file.write_bytes(b"\x00\x01\x02\x03")

    graph_file = storage.get_graph_file_path(team_id, 3)
    graph_file.write_bytes(b"mock_graph_pt_data")

    assert raw_file.exists()
    assert feat_file.exists()
    assert graph_file.exists()
    print("   ✓ Created filesystem artifacts (raw, feature embeddings, graph snapshot).")

    # Unified deletion test (DB + Filesystem)
    success = delete_team_completely(db, team_id, storage=storage)
    assert success is True
    # DB check
    assert db.get(Team, team_id) is None
    # Disk check
    assert not storage.get_team_root_dir(team_id).exists()
    print("   ✓ Unified deletion purged both PostgreSQL rows and disk directory data/{team_id}/.")

    # Clean up test dir
    if test_storage_dir.exists():
        shutil.rmtree(test_storage_dir)

    # 4. Test Research Anonymizer Export
    print("\n4. Testing Anonymized Research Export Script...")
    # Re-seed team for export test
    new_team_id = seed_database(db=db)
    new_team = db.get(Team, new_team_id)
    export_payload = export_anonymised_team(db, new_team)
    assert export_payload is not None

    # Check that personal identity attributes are omitted
    export_str = str(export_payload)
    assert "alice@example.com" not in export_str
    assert "bob@cs.univ.edu" not in export_str
    assert "Implement core auth and session handling" not in export_str  # Commit message dropped
    assert "anon_student_001" in export_str  # Replaced with anonymised_id

    # Check path hashing preserves extension
    test_hashed = hash_path("backend/app/auth/router.py")
    assert test_hashed.endswith(".py")
    assert "router" not in test_hashed
    print(f"   ✓ File path hashed: 'backend/app/auth/router.py' -> '{test_hashed}'")
    print("   ✓ Research export structure validated (names/emails/messages stripped).")

    db.close()
    print("\n🎉 ALL PHASE 4 COMPLIANCE & STORAGE TESTS PASSED!")


if __name__ == "__main__":
    run_phase_4_tests()


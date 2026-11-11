"""initial schema with 17 tables and indexes

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-11-07 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. corpus_repos
    op.create_table(
        'corpus_repos',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('full_name', sa.String(length=200), nullable=False),
        sa.Column('licence', sa.String(length=100), nullable=False),
        sa.Column('commit_count', sa.Integer(), nullable=False),
        sa.Column('contributors', sa.Integer(), nullable=False),
        sa.Column('collected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('full_name')
    )

    # 2. teams
    op.create_table(
        'teams',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('course', sa.String(length=100), nullable=False),
        sa.Column('repo_url', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_teams_course', 'teams', ['course'], unique=False)

    # 3. users
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('github_login', sa.String(length=100), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_users_github_login', 'users', ['github_login'], unique=True)

    # 4. alerts
    op.create_table(
        'alerts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=False),
        sa.Column('week', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=30), nullable=False),
        sa.Column('gini', sa.Float(), nullable=False),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alerts_team_id', 'alerts', ['team_id'], unique=False)
    op.create_index('ix_alerts_team_week', 'alerts', ['team_id', 'week'], unique=False)

    # 5. audit_log
    op.create_table(
        'audit_log',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('actor_id', sa.String(length=36), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('target', sa.String(length=200), nullable=False),
        sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_log_actor_id', 'audit_log', ['actor_id'], unique=False)
    op.create_index('ix_audit_log_at', 'audit_log', ['at'], unique=False)

    # 6. jobs
    op.create_table(
        'jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_jobs_team_id', 'jobs', ['team_id'], unique=False)
    op.create_index('ix_jobs_team_status', 'jobs', ['team_id', 'status'], unique=False)

    # 7. team_members
    op.create_table(
        'team_members',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('consent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('anonymised_id', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('anonymised_id'),
        sa.UniqueConstraint('team_id', 'user_id', name='uq_team_member')
    )
    op.create_index('ix_team_members_team_id', 'team_members', ['team_id'], unique=False)
    op.create_index('ix_team_members_user_id', 'team_members', ['user_id'], unique=False)

    # 8. identities
    op.create_table(
        'identities',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=False),
        sa.Column('git_name', sa.String(length=200), nullable=False),
        sa.Column('git_email', sa.String(length=255), nullable=False),
        sa.Column('member_id', sa.String(length=36), nullable=True),
        sa.Column('is_bot', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['member_id'], ['team_members.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_identities_git_email', 'identities', ['git_email'], unique=False)
    op.create_index('ix_identities_member_id', 'identities', ['member_id'], unique=False)
    op.create_index('ix_identities_team_id', 'identities', ['team_id'], unique=False)

    # 9. issues
    op.create_table(
        'issues',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('author_member_id', sa.String(length=36), nullable=True),
        sa.Column('labels', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['author_member_id'], ['team_members.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'number', name='uq_issue_team_number')
    )
    op.create_index('ix_issues_author_member_id', 'issues', ['author_member_id'], unique=False)
    op.create_index('ix_issues_team_id', 'issues', ['team_id'], unique=False)

    # 10. notes
    op.create_table(
        'notes',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=False),
        sa.Column('author_id', sa.String(length=36), nullable=False),
        sa.Column('member_id', sa.String(length=36), nullable=True),
        sa.Column('kind', sa.String(length=50), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['member_id'], ['team_members.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_notes_author_id', 'notes', ['author_id'], unique=False)
    op.create_index('ix_notes_member_id', 'notes', ['member_id'], unique=False)
    op.create_index('ix_notes_team_id', 'notes', ['team_id'], unique=False)

    # 11. pull_requests
    op.create_table(
        'pull_requests',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('author_member_id', sa.String(length=36), nullable=True),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('merged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('state', sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(['author_member_id'], ['team_members.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'number', name='uq_pr_team_number')
    )
    op.create_index('ix_pull_requests_author_member_id', 'pull_requests', ['author_member_id'], unique=False)
    op.create_index('ix_pull_requests_team_id', 'pull_requests', ['team_id'], unique=False)

    # 12. scores
    op.create_table(
        'scores',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=False),
        sa.Column('member_id', sa.String(length=36), nullable=False),
        sa.Column('week', sa.Integer(), nullable=False),
        sa.Column('model_version', sa.String(length=50), nullable=False),
        sa.Column('share', sa.Float(), nullable=False),
        sa.Column('facets', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('flags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['member_id'], ['team_members.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'member_id', 'week', 'model_version', name='uq_score_member_week_version')
    )
    op.create_index('ix_scores_member_id', 'scores', ['member_id'], unique=False)
    op.create_index('ix_scores_team_id', 'scores', ['team_id'], unique=False)
    op.create_index('ix_scores_team_week', 'scores', ['team_id', 'week'], unique=False)
    op.create_index('ix_scores_week', 'scores', ['week'], unique=False)

    # 13. surveys
    op.create_table(
        'surveys',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=False),
        sa.Column('rater_member_id', sa.String(length=36), nullable=False),
        sa.Column('ratee_member_id', sa.String(length=36), nullable=False),
        sa.Column('percent', sa.Float(), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['ratee_member_id'], ['team_members.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['rater_member_id'], ['team_members.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_surveys_ratee_member_id', 'surveys', ['ratee_member_id'], unique=False)
    op.create_index('ix_surveys_rater_member_id', 'surveys', ['rater_member_id'], unique=False)
    op.create_index('ix_surveys_team_id', 'surveys', ['team_id'], unique=False)

    # 14. commits
    op.create_table(
        'commits',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('team_id', sa.String(length=36), nullable=False),
        sa.Column('sha', sa.String(length=40), nullable=False),
        sa.Column('identity_id', sa.String(length=36), nullable=True),
        sa.Column('committed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('additions', sa.Integer(), nullable=False),
        sa.Column('deletions', sa.Integer(), nullable=False),
        sa.Column('flag', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['identity_id'], ['identities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'sha', name='uq_commits_team_sha')
    )
    op.create_index('ix_commits_committed_at', 'commits', ['committed_at'], unique=False)
    op.create_index('ix_commits_identity_id', 'commits', ['identity_id'], unique=False)
    op.create_index('ix_commits_sha', 'commits', ['sha'], unique=False)
    op.create_index('ix_commits_team_id', 'commits', ['team_id'], unique=False)
    op.create_index('ix_commits_team_sha', 'commits', ['team_id', 'sha'], unique=False)

    # 15. evidence
    op.create_table(
        'evidence',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('score_id', sa.String(length=36), nullable=False),
        sa.Column('commit_sha', sa.String(length=40), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['score_id'], ['scores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_evidence_commit_sha', 'evidence', ['commit_sha'], unique=False)
    op.create_index('ix_evidence_score_id', 'evidence', ['score_id'], unique=False)

    # 16. reviews
    op.create_table(
        'reviews',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('pull_request_id', sa.String(length=36), nullable=False),
        sa.Column('reviewer_member_id', sa.String(length=36), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('state', sa.String(length=30), nullable=False),
        sa.Column('comment_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['pull_request_id'], ['pull_requests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewer_member_id'], ['team_members.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_reviews_pull_request_id', 'reviews', ['pull_request_id'], unique=False)
    op.create_index('ix_reviews_reviewer_member_id', 'reviews', ['reviewer_member_id'], unique=False)

    # 17. file_changes
    op.create_table(
        'file_changes',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('commit_id', sa.String(length=36), nullable=False),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('language', sa.String(length=50), nullable=True),
        sa.Column('additions', sa.Integer(), nullable=False),
        sa.Column('deletions', sa.Integer(), nullable=False),
        sa.Column('complexity_delta', sa.Integer(), nullable=False),
        sa.Column('tree_edit_size', sa.Integer(), nullable=False),
        sa.Column('flag', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['commit_id'], ['commits.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_file_changes_commit_id', 'file_changes', ['commit_id'], unique=False)


def downgrade() -> None:
    op.drop_table('file_changes')
    op.drop_table('reviews')
    op.drop_table('evidence')
    op.drop_table('commits')
    op.drop_table('surveys')
    op.drop_table('scores')
    op.drop_table('pull_requests')
    op.drop_table('notes')
    op.drop_table('issues')
    op.drop_table('identities')
    op.drop_table('team_members')
    op.drop_table('jobs')
    op.drop_table('audit_log')
    op.drop_table('alerts')
    op.drop_table('users')
    op.drop_table('teams')
    op.drop_table('corpus_repos')


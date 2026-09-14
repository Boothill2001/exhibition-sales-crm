"""initial schema

Revision ID: 001
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'companies',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('company_code', sa.Text, nullable=False, unique=True),
        sa.Column('company_name', sa.Text, nullable=False),
        sa.Column('province_code', sa.Text),
        sa.Column('region', sa.Text),
        sa.Column('sales_rep', sa.Text),
    )
    op.create_index('ix_companies_company_code', 'companies', ['company_code'])
    op.create_index('ix_companies_company_name', 'companies', ['company_name'])

    op.create_table(
        'contacts',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('contact_code', sa.Text, nullable=False, unique=True),
        sa.Column('company_id', sa.Integer, sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('first_name', sa.Text),
        sa.Column('last_name', sa.Text),
        sa.Column('email', sa.Text),
        sa.Column('phone', sa.Text),
    )
    op.create_index('ix_contacts_contact_code', 'contacts', ['contact_code'])
    op.create_index('ix_contacts_company_id', 'contacts', ['company_id'])

    op.create_table(
        'fair_editions',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('fair_edition_code', sa.Text, nullable=False, unique=True),
        sa.Column('fair_name', sa.Text, nullable=False),
        sa.Column('city', sa.Text),
        sa.Column('venue', sa.Text),
        sa.Column('starts_on', sa.Date),
        sa.Column('ends_on', sa.Date),
        sa.Column('max_stand_height_m', sa.Numeric(5, 2)),
    )
    op.create_index('ix_fair_editions_code', 'fair_editions', ['fair_edition_code'])

    op.create_table(
        'opportunities',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('opportunity_code', sa.Text, nullable=False, unique=True),
        sa.Column('company_id', sa.Integer, sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('contact_id', sa.Integer, sa.ForeignKey('contacts.id'), nullable=True),
        sa.Column('fair_edition_id', sa.Integer, sa.ForeignKey('fair_editions.id'), nullable=True),
        sa.Column('description', sa.Text),
        sa.Column('amount_eur', sa.Numeric(12, 2)),
        sa.Column('status', sa.Text),
        sa.Column('opened_on', sa.Date),
        sa.Column('expected_close_on', sa.Date),
        sa.Column('stand_area_sqm', sa.Numeric(8, 2)),
        sa.Column('client_budget_eur', sa.Numeric(12, 2)),
        sa.Column('requested_height_m', sa.Numeric(5, 2)),
        sa.Column('brief_notes', sa.Text),
        sa.Column('historical_campaign_code', sa.Text),
    )
    op.create_index('ix_opportunities_code', 'opportunities', ['opportunity_code'])
    op.create_index('ix_opportunities_company_id', 'opportunities', ['company_id'])
    op.create_index('ix_opportunities_fair_edition_id', 'opportunities', ['fair_edition_id'])
    op.create_index('ix_opportunities_status', 'opportunities', ['status'])

    op.create_table(
        'activities',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('entry_id', sa.Text, nullable=False, unique=True),
        sa.Column('company_id', sa.Integer, sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('opportunity_id', sa.Integer, sa.ForeignKey('opportunities.id'), nullable=True),
        sa.Column('activity_type', sa.Text),
        sa.Column('occurred_at', sa.DateTime(timezone=True)),
        sa.Column('details', sa.Text),
        sa.Column('follow_up_on', sa.Date),
        sa.Column('completion_marker', sa.Text),
        sa.Column('legacy_author', sa.Text),
    )
    op.create_index('ix_activities_company_id', 'activities', ['company_id'])
    op.create_index('ix_activities_opportunity_id', 'activities', ['opportunity_id'])
    op.create_index('ix_activities_follow_up_on', 'activities', ['follow_up_on'])

    op.create_table(
        'handoff_runs',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('opportunity_id', sa.Integer, sa.ForeignKey('opportunities.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('crm_snapshot', sa.JSON),
        sa.Column('preparer_output', sa.JSON),
        sa.Column('checker_output', sa.JSON),
        sa.Column('coordinator_decision', sa.Text),
        sa.Column('decision_reason', sa.Text),
    )
    op.create_index('ix_handoff_runs_opportunity_id', 'handoff_runs', ['opportunity_id'])


def downgrade() -> None:
    op.drop_table('handoff_runs')
    op.drop_table('activities')
    op.drop_table('opportunities')
    op.drop_table('fair_editions')
    op.drop_table('contacts')
    op.drop_table('companies')

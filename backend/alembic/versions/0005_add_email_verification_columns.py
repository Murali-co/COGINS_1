"""Add email verification columns to users table

Revision ID: 0005_email_verification
Revises: 0003_add_saved_job_table
Create Date: 2026-06-24 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0005_email_verification'
down_revision = '0003_add_saved_job_table'
branch_labels = None
depends_on = None


def upgrade():
    # Add email verification columns to users table
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('verification_token', sa.String(), nullable=True, unique=True))
    op.add_column('users', sa.Column('verification_token_expiry', sa.DateTime(timezone=True), nullable=True))
    
    # Add password reset columns to users table
    op.add_column('users', sa.Column('reset_password_token', sa.String(), nullable=True, unique=True))
    op.add_column('users', sa.Column('reset_password_token_expiry', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    # Remove password reset columns from users table
    op.drop_column('users', 'reset_password_token_expiry')
    op.drop_column('users', 'reset_password_token')
    
    # Remove email verification columns from users table
    op.drop_column('users', 'verification_token_expiry')
    op.drop_column('users', 'verification_token')
    op.drop_column('users', 'email_verified')

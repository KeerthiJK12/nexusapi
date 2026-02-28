"""scope credit transaction idempotency uniqueness by organisation"""

from alembic import op
import sqlalchemy as sa

revision = "0002_credit_tx_idempotency_scope"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE credit_transactions DROP CONSTRAINT IF EXISTS credit_transactions_idempotency_key_key")
    op.create_unique_constraint(
        "uq_credit_tx_org_idempotency",
        "credit_transactions",
        ["organisation_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_credit_tx_org_idempotency", "credit_transactions", type_="unique")
    op.create_unique_constraint(
        "credit_transactions_idempotency_key_key",
        "credit_transactions",
        ["idempotency_key"],
    )

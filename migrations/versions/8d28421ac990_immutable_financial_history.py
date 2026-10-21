"""Protect committed financial history and administrative audit from mutation."""

from alembic import op

revision = "8d28421ac990"
down_revision = "0f6e865e7a63"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE FUNCTION reject_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Committed history is append-only';
        END;
        $$
    """)
    for table in ("audit_log", "accepted_keys", "transactions"):
        op.execute(
            f"CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_history_mutation()"
        )


def downgrade():
    for table in ("audit_log", "accepted_keys", "transactions"):
        op.execute(f"DROP TRIGGER immutable_history ON {table}")
    op.execute("DROP FUNCTION reject_history_mutation()")

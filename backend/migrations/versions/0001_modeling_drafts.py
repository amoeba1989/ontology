"""First incremental migration: modeling drafts only; legacy tables remain intact."""
from alembic import op
import sqlalchemy as sa

revision = "0001_modeling_drafts"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    definitions = {
        "modeling_drafts": [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("owner_id", sa.String(36), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("scenario", sa.Text(), nullable=False),
            sa.Column("content", sa.JSON(), nullable=False),
            sa.Column("proposal", sa.JSON(), nullable=True),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("materialized", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        ],
        "modeling_draft_events": [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("draft_id", sa.String(36), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(40), nullable=False),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        ],
    }
    inspector = sa.inspect(op.get_bind())
    for name, columns in definitions.items():
        if not inspector.has_table(name):
            op.create_table(name, *columns)
        elif {c.name for c in columns} - {c["name"] for c in inspector.get_columns(name)}:
            raise RuntimeError(f"Existing {name} has an incompatible schema; back up and inspect before upgrading")
        field = "owner_id" if name == "modeling_drafts" else "draft_id"
        index = f"ix_{name}_{field}"
        if index not in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(name)}:
            op.create_index(index, name, [field])


def downgrade():
    raise RuntimeError("Automatic downgrade would delete modeling drafts. Restore a verified backup instead.")

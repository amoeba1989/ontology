"""Explicit scene ownership for newly created ontology versions."""
from alembic import op
import sqlalchemy as sa

revision = "0002_scene_versions"
down_revision = "0001_modeling_drafts"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("ontology_versions"):
        if "scene_id" not in {c['name'] for c in inspector.get_columns('ontology_versions')}:
            op.add_column('ontology_versions', sa.Column('scene_id', sa.String(36), nullable=True))


def downgrade():
    raise RuntimeError("Keep scene ownership metadata; restore a verified backup instead")

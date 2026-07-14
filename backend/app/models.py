from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, PKMixin, TimestampMixin

__all__ = ["Base", "Mapped", "PKMixin", "TimestampMixin", "mapped_column"]

# Define ORM models here. Example:
#   class Thing(Base, PKMixin, TimestampMixin):
#       __tablename__ = "things"
#       name: Mapped[str] = mapped_column(nullable=False)
# UUIDv7 `id` + timestamptz created_at/updated_at come from the mixins. Money → Numeric/int-cents, never
# float. FKs → explicit ondelete + index=True. Apply schema via alembic (revision --autogenerate), never
# Base.metadata.create_all.

"""SQLAlchemy models mirroring schema.sql.

schema.sql remains the source of truth for the database (it owns the extension,
the generated column, and the index definitions). These models exist so the
rest of the code can query in Python instead of raw SQL.
"""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Computed, DateTime, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class Chunk(Base):
    """One embeddable slice of a source document."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    source: Mapped[str] = mapped_column(Text, nullable=False)
    repo: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dimensions), nullable=True
    )

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Maintained by Postgres from `content`. Declared Computed so SQLAlchemy
    # knows to read it but never write it -- writing a generated column errors.
    # Present so keyword search can reference Chunk.tsv in queries.
    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', content)", persisted=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        """Return a short identifier useful in logs and debugging."""
        return f"<Chunk {self.repo}/{self.file_path} ({self.chunk_type})>"

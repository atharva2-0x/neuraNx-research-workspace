"""A single repository contract for local SQLite and deployed PostgreSQL."""
import os
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, String, Text, JSON, DateTime, Numeric, Index, ForeignKey, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'fund.db'}")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
Session = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    checksum: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    stage: Mapped[str] = mapped_column(String(100), default="Queued")
    progress: Mapped[int] = mapped_column(default=0)
    page_count: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    pipeline_version: Mapped[str] = mapped_column(String(30), default="1.0.0")


class QueryLog(Base):
    __tablename__ = "query_log"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    route: Mapped[str] = mapped_column(String(30))
    latency_ms: Mapped[int]
    source_pages: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FactRecord(Base):
    __tablename__ = "facts"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    metric: Mapped[str] = mapped_column(String(64), index=True)
    period: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[object] = mapped_column(Numeric(28, 10))
    unit: Mapped[str] = mapped_column(String(100))
    classification: Mapped[str] = mapped_column(String(30))
    data: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (Index("ix_facts_document_metric_period", "document_id", "metric", "period"),)


class ChunkRecord(Base):
    __tablename__ = "chunks"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    page: Mapped[int]
    section: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)


class ValidationRecord(Base):
    __tablename__ = "validation_issues"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    rule: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="open")
    data: Mapped[dict] = mapped_column(JSON)


class CalculationRecord(Base):
    __tablename__ = "calculations"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    data: Mapped[dict] = mapped_column(JSON)


def initialize():
    Base.metadata.create_all(engine)


def metadata(doc):
    p = doc.payload or {}
    return {"id": doc.id, "filename": doc.filename, "checksum": doc.checksum,
            "status": doc.status, "stage": doc.stage, "progress": doc.progress,
            "page_count": doc.page_count, "uploaded_at": doc.uploaded_at.isoformat(),
            "error": doc.error, "pipeline_version": doc.pipeline_version,
            "fact_count": len(p.get("facts", [])), "issue_count": len(p.get("issues", [])),
            "table_count": sum(len(x.get("tables", [])) for x in p.get("pages", [])),
            "synthetic": p.get("synthetic", False)}


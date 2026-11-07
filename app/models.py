"""Typed evidence contract. Source observations never become derived values."""
from __future__ import annotations
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field


class Source(BaseModel):
    document_id: str | None = None
    filename: str | None = None
    page: int = Field(ge=1)
    section: str
    table: str | None = None
    row: str | None = None
    column: str | None = None
    bbox: list[float] | None = None
    method: str = "pdfplumber.table"


class Fact(BaseModel):
    id: str
    metric: str
    period: str
    value: Decimal
    unit: str
    category: str | None = None
    classification: Literal["historical", "forecast", "assumption", "derived"]
    raw_text: str
    source: Source
    confidence: float = Field(default=0.95, ge=0, le=1)


class Issue(BaseModel):
    id: str
    rule: str
    severity: Literal["warning", "info", "error"]
    title: str
    description: str
    fact_ids: list[str] = []
    pages: list[int] = []
    details: dict = {}
    status: Literal["open", "reviewed"] = "open"


class Query(BaseModel):
    document_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=2, max_length=2000)


class Calculation(BaseModel):
    formula: str
    inputs: list[str]
    result: str
    unit: str
    fact_ids: list[str] = []


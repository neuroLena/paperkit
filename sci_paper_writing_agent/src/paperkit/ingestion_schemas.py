"""Additional schemas for ingestion. Not yet connected to the original pipeline."""
from typing import Literal
from pydantic import BaseModel, Field
from decimal import Decimal


class ScientificFact(BaseModel):
    id: str
    text: str
    analysis: str | None = None
    outcome: str | None = None
    predictor: str | None = None
    modality: str | None = None
    model: str | None = None
    sample: str | None = None
    fold: str | None = None
    metric: str
    value: Decimal
    ci_lower: Decimal | None = None
    ci_upper: Decimal | None = None
    confidence_level: Decimal | None = None
    n: int | None = None
    unit: str | None = None
    source_file: str
    source_row: int | None = None
    source_column: str | None = None
    source_sha256: str | None = None
    approved: bool = False


class MetricSpec(BaseModel):
    column: str
    meaning: str
    unit: str | None = None


class TableSpec(BaseModel):
    id: str
    file: str
    title: str
    analysis: str
    grouping_columns: list[str] = Field(default_factory=list)
    metrics: list[MetricSpec] = Field(default_factory=list)


class TableManifest(BaseModel):
    tables: list[TableSpec] = Field(default_factory=list)


class SourceDocument(BaseModel):
    path: str
    sha256: str
    citation_key: str | None = None
    doi: str | None = None


class EvidenceItem(BaseModel):
    id: str
    citation_key: str
    statement: str
    quotation: str
    page: int | None = None
    section: str | None = None
    verified: bool = False


class LiteratureRecord(BaseModel):
    source: SourceDocument
    question: str = ""
    study_design: str = ""
    population: str = ""
    methods: str = ""
    limitations: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class ConceptRecord(BaseModel):
    name: str
    synthesis: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class WritingRule(BaseModel):
    id: str
    category: Literal["structure", "argumentation", "language", "statistics", "reporting", "citations", "formatting", "scientific_reasoning"]
    instruction: str
    rationale: str = ""
    sections: list[str] = Field(default_factory=lambda: ["all"])
    study_designs: list[str] = Field(default_factory=lambda: ["all"])
    priority: Literal["required", "recommended", "optional"]
    severity: Literal["blocking", "warning"]
    validation_method: Literal["python", "ai", "human", "hybrid"]
    source_file: str
    source_page: int | None = None
    source_quote: str | None = None
    group: str = ""
    avoid_terms: list[str] = Field(default_factory=list)
    approved: bool = False


class RuleSet(BaseModel):
    name: str
    version: str = "1.0"
    rules: list[WritingRule] = Field(default_factory=list)


class AgentConfig(BaseModel):
    provider: str = "anthropic"
    model: str | None = None
    max_tokens: int = 8000


class AgentRun(BaseModel):
    agent: str
    model: str
    status: str
    input_tokens: int | None = None
    output_tokens: int | None = None

"""Data schemas. Everything that moves between code and agents goes through these."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["OBSERVED", "INFERRED", "ASSUMED", "SPECULATIVE"]


class SectionSpec(BaseModel):
    id: str
    title: str
    max_words: int = 1000
    required_headings: list[str] = Field(default_factory=list)


class PaperSpec(BaseModel):
    title: str
    design: Literal["observational", "experimental"] = "observational"
    max_rounds: int = 3
    csl: str | None = None
    number_whitelist: list[str] = Field(default_factory=list)
    term_whitelist: list[str] = Field(default_factory=list)
    sections: list[SectionSpec]

    def section(self, sec_id: str) -> SectionSpec:
        for sec in self.sections:
            if sec.id == sec_id:
                return sec
        raise KeyError(f"No section '{sec_id}' in paper.yaml")


class Claim(BaseModel):
    id: str = Field(description="C1, C2, ...")
    text: str = Field(description="One claim in one sentence")
    category: Category
    fact_ids: list[str] = Field(default_factory=list, description="Ids from the facts registry")
    cite_keys: list[str] = Field(default_factory=list, description="Citation keys from the library")
    assumptions: list[str] = Field(default_factory=list, description="What this claim depends on")


class ClaimList(BaseModel):
    """What the planner returns."""

    claims: list[Claim]


class ClaimTable(BaseModel):
    """What is stored on disk. Only a person sets the approved flag, through the CLI."""

    section_id: str
    approved: bool = False
    claims: list[Claim]


class Draft(BaseModel):
    markdown: str = Field(description="The full section in Markdown")


class Issue(BaseModel):
    gate: str = Field(description="Which check raised it")
    severity: Literal["blocking", "warning"] = "blocking"
    message: str
    excerpt: str = ""


class Review(BaseModel):
    issues: list[Issue] = Field(default_factory=list)


class WikiPage(BaseModel):
    markdown: str

# Extended ingestion schemas
from .ingestion_schemas import (ScientificFact, MetricSpec, TableSpec, TableManifest, SourceDocument, EvidenceItem, LiteratureRecord, ConceptRecord, WritingRule, RuleSet, AgentConfig, AgentRun)

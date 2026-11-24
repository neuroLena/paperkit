"""Gates: deterministic checks on a draft. Each module provides check(draft, ctx) -> list[Issue]."""
from __future__ import annotations

from ..schemas import Issue
from . import citations, coverage, language, numbers, structure
from .claims import check_claims
from .common import GateContext

GATES = [structure, citations, numbers, language, coverage]

__all__ = ["GATES", "GateContext", "blocking", "check_claims", "run_gates"]


def run_gates(draft: str, ctx: GateContext) -> list[Issue]:
    issues: list[Issue] = []
    for gate in GATES:
        issues += gate.check(draft, ctx)
    return issues


def blocking(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "blocking"]

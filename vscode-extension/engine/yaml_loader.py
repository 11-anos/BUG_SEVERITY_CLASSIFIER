"""Load user-defined rules from YAML.

Supports two rule shapes:

1. Simple filter — flag every fact matching `where`.
2. Filter + required sibling — flag candidates for which a matching
   sibling fact does NOT exist (same function, optionally later line).

Not supported: rules that need to traverse ancestors beyond the enclosing
function, or that inspect the source text. Those stay in Python.
"""

from pathlib import Path
from typing import Any

import yaml

from guard_walker import DeclFact, UseFact, TerminatorEvent
from rule_types import RuleSpec, Violation


FACT_TYPES = {
    "uses": UseFact,
    "decls": DeclFact,
    "terminators": TerminatorEvent,
}


def _match_condition(value: Any, cond: Any) -> bool:
    if isinstance(cond, dict):
        if "eq" in cond:
            return value == cond["eq"]
        if "neq" in cond:
            return value != cond["neq"]
        if "in" in cond:
            return value in cond["in"]
        if "not_in" in cond:
            return value not in cond["not_in"]
        raise ValueError(f"unknown condition operator: {list(cond)}")
    return value == cond


def _match_fact(fact: Any, where: dict, params_by_key: dict) -> bool:
    for field, cond in where.items():
        if field == "matches_param":
            if cond is not True:
                raise ValueError("matches_param only accepts true")
            key = (fact.scope_kind, fact.scope_line, fact.name)
            if key not in params_by_key:
                return False
            continue
        value = getattr(fact, field, None)
        if not _match_condition(value, cond):
            return False
    return True


def _render(template: str, fact: Any) -> str:
    fields = {
        "name": getattr(fact, "name", ""),
        "line": getattr(fact, "line", ""),
        "col": getattr(fact, "col", ""),
        "context": getattr(fact, "context", ""),
        "state": getattr(fact, "state", ""),
        "kind": getattr(fact, "kind", ""),
        "scope_kind": getattr(fact, "scope_kind", "") or "",
    }
    try:
        return template.format(**fields)
    except KeyError as e:
        raise ValueError(f"unknown placeholder in message template: {e}")


def _enclosing_function_line(fact: Any) -> int | None:
    for ty, ln in fact.ancestors:
        if ty == "function_definition":
            return ln
    return None


def _find_sibling(candidate: Any, spec: dict, facts_by_type: dict, params_by_key: dict) -> bool:
    pool = facts_by_type[spec["select"]]
    where = spec.get("where", {})
    same_fn = spec.get("same_function", False)
    after = spec.get("position_after", False)
    for sib in pool:
        if sib is candidate:
            continue
        if not _match_fact(sib, where, params_by_key):
            continue
        if same_fn and _enclosing_function_line(sib) != _enclosing_function_line(candidate):
            continue
        if after and sib.line <= candidate.line:
            continue
        return True
    return False


def _build_rule(spec: dict) -> RuleSpec:
    try:
        name = spec["name"]
        severity = spec.get("severity", "warning")
        select = spec["select"]
        where = spec.get("where", {})
        require_sibling = spec.get("require_sibling")
        message_template = spec["message"]
    except KeyError as e:
        raise ValueError(f"rule missing required field {e}")

    if select not in FACT_TYPES:
        raise ValueError(f"rule {name!r}: select must be one of {sorted(FACT_TYPES)}")

    def fn(decls, uses, terminators):
        facts_by_type = {"uses": uses, "decls": decls, "terminators": terminators}
        params_by_key = {
            (d.scope_kind, d.scope_line, d.name): d
            for d in decls if d.is_param
        }
        violations = []
        for fact in facts_by_type[select]:
            if not _match_fact(fact, where, params_by_key):
                continue
            if require_sibling is not None:
                if _find_sibling(fact, require_sibling, facts_by_type, params_by_key):
                    continue
            violations.append(Violation(
                rule=name,
                line=fact.line,
                col=fact.col,
                message=_render(message_template, fact),
            ))
        return violations

    return RuleSpec(name, severity, fn)


def load_yaml_rules(path: Path | None) -> list[RuleSpec]:
    if path is None or not path.exists():
        return []
    data = yaml.safe_load(path.read_text())
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"{path}: top level must be a list of rules")
    rules = []
    for i, spec in enumerate(data):
        if not isinstance(spec, dict):
            raise ValueError(f"{path}: rule #{i} is not a mapping")
        rules.append(_build_rule(spec))
    return rules

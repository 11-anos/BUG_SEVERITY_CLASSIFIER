# rules.py — rule engine with per-rule severity, state-based param check.
#
# Run: python3 rules.py <file.cpp> [--verbose] [--json] [--config <path>]

import json
import sys
import yaml
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable
import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser

from guard_walker import Walker, DeclFact, UseFact, TerminatorEvent
from rule_types import Violation, RuleSpec
from yaml_loader import load_yaml_rules

CPP_LANGUAGE = Language(tscpp.language())
parser = Parser(CPP_LANGUAGE)

SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2, "hint": 3}

def _enclosing_function_line(u: UseFact) -> int | None:
    for ty, ln in u.ancestors:
        if ty == "function_definition":
            return ln
    return None


def rule_malloc_without_free(decls, uses, terminators):
    """Every malloc callee in a function must have a subsequent free callee
    in the same function.

    LIMITATION: not path-sensitive. A free inside a conditional passes.
    Does not check that the free's argument matches the malloc'd pointer.
    """
    mallocs = [u for u in uses if u.context == "callee" and u.name == "malloc"]
    frees = [u for u in uses if u.context == "callee" and u.name == "free"]
    violations = []
    for m in mallocs:
        fn_line = _enclosing_function_line(m)
        has_free = any(
            _enclosing_function_line(f) == fn_line and f.line > m.line
            for f in frees
        )
        if not has_free:
            violations.append(Violation(
                rule="malloc-without-free",
                line=m.line,
                col=m.col,
                message=(
                    f"malloc at line {m.line} has no subsequent free "
                    f"in the same function"
                ),
            ))
    return violations
def rule_unchecked_param_use(decls, uses, terminators):
    """A parameter must be in state 'safe' at every non-condition use."""
    params = {
        (d.scope_kind, d.scope_line, d.name): d
        for d in decls if d.is_param
    }
    violations = []
    for u in uses:
        if u.context == "condition":
            continue
        if u.state == "safe":
            continue
        key = (u.scope_kind, u.scope_line, u.name)
        if key not in params:
            continue
        d = params[key]
        violations.append(Violation(
            rule="unchecked-param-use",
            line=u.line,
            col=u.col,
            message=(
                f"parameter {u.name!r} of {d.scope_kind} used at line {u.line} "
                f"({u.context}) with state={u.state!r}"
            ),
        ))
    return violations


def rule_no_dead_code(decls, uses, terminators):
    first_term_by_block: dict[int, tuple[int, int]] = {}
    for t in terminators:
        if t.parent_block_line is None:
            continue
        b = t.parent_block_line
        pos = (t.line, t.col)
        if b not in first_term_by_block or pos < first_term_by_block[b]:
            first_term_by_block[b] = pos

    violations = []
    seen_lines: set[int] = set()
    for u in uses:
        if u.line in seen_lines:
            continue
        for i, (ty, ln) in enumerate(u.ancestors):
            if ty != "compound_statement" or ln not in first_term_by_block:
                continue
            term_line, _ = first_term_by_block[ln]
            if i + 1 >= len(u.ancestors):
                continue
            _, stmt_line = u.ancestors[i + 1]
            if stmt_line == term_line:
                break
            if stmt_line > term_line:
                violations.append(Violation(
                    rule="no-dead-code",
                    line=u.line,
                    col=u.col,
                    message=(
                        f"use of {u.name!r} at line {u.line} is unreachable "
                        f"(after terminator at line {term_line})"
                    ),
                ))
                seen_lines.add(u.line)
                break
    return violations


RULES = [
    RuleSpec("unchecked-param-use", "warning", rule_unchecked_param_use),
    RuleSpec("no-dead-code", "error", rule_no_dead_code),
    RuleSpec("malloc-without-free", "warning", rule_malloc_without_free),
]


def load_severity_overrides(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    if not path.exists():
        print(f"config file not found: {path}", file=sys.stderr)
        sys.exit(2)
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"config file is not valid JSON: {path}: {e}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(data, dict):
        print(f"config file must be a JSON object: {path}", file=sys.stderr)
        sys.exit(2)
    for rule_name, sev in data.items():
        if sev not in SEVERITY_RANK:
            print(
                f"unknown severity {sev!r} for rule {rule_name!r}. "
                f"valid: {sorted(SEVERITY_RANK)}",
                file=sys.stderr,
            )
            sys.exit(2)
    return data


def analyze_file(
    path: Path,
    rules: list[RuleSpec] | None = None,
    severity_overrides: dict[str, str] | None = None,
) -> list[dict]:
    """Analyze one file. Returns a list of violation dicts with severity
    resolved and sorted. Pure — no printing, no exit."""
    if rules is None:
        rules = _active_rules()
    if severity_overrides is None:
        severity_overrides = {}

    src = path.read_bytes()
    tree = parser.parse(src)

    w = Walker(lambda _s: None)
    w.walk(tree.root_node)

    severity_by_rule = {
        spec.name: severity_overrides.get(spec.name, spec.default_severity)
        for spec in rules
    }

    all_violations: list[Violation] = []
    for spec in rules:
        all_violations.extend(spec.fn(w.decls, w.uses, w.terminators))

    all_violations.sort(key=lambda v: (
        SEVERITY_RANK[severity_by_rule[v.rule]],
        v.line,
        v.col,
    ))

    return [
        {**asdict(v), "severity": severity_by_rule[v.rule]}
        for v in all_violations
    ]


def _active_rules() -> list[RuleSpec]:
    """Python RULES merged with YAML rules (YAML wins by name)."""
    yaml_path = Path(__file__).resolve().parent / "rules.yaml"
    try:
        yaml_rules = load_yaml_rules(yaml_path)
    except Exception as e:
        raise ValueError(f"failed to load {yaml_path}: {e}")
    yaml_names = {y.name for y in yaml_rules}
    merged = [spec for spec in RULES if spec.name not in yaml_names]
    merged.extend(yaml_rules)
    return merged


def main() -> None:
    args = sys.argv[1:]
    verbose = "--verbose" in args
    as_json = "--json" in args
    args = [a for a in args if a not in ("--verbose", "--json")]

    config_path: Path | None = None
    if "--config" in args:
        i = args.index("--config")
        if i + 1 >= len(args):
            print("--config requires a path", file=sys.stderr)
            sys.exit(2)
        config_path = Path(args[i + 1])
        del args[i:i + 2]
    else:
        candidate = Path(__file__).resolve().parent / "rule_severities.json"
        if candidate.exists():
            config_path = candidate

    if not args:
        print("usage: rules.py <file.cpp> [--verbose] [--json] [--config <path>]",
              file=sys.stderr)
        sys.exit(2)

    path = Path(args[0])

    try:
        rules = _active_rules()
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)

    overrides = load_severity_overrides(config_path)
    violations = analyze_file(path, rules, overrides)

    if as_json:
        print(json.dumps({
            "file": str(path),
            "violations": violations,
        }, indent=2))
    else:
        if not violations:
            print(f"{path}: no violations")
        for v in violations:
            print(f"{path}:{v['line']}:{v['col']}: {v['severity']}: {v['rule']}: {v['message']}")

    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
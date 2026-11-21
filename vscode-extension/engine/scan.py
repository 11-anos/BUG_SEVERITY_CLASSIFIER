"""Walk a directory, run the rule engine on every .cpp file, aggregate results.

Run: python3 scan.py <directory> [--json]
Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from rules import analyze_file, _active_rules, load_severity_overrides


def _collect_cpp_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.cpp") if p.is_file())


def scan(root: Path) -> dict:
    rules = _active_rules()
    config_path = Path(__file__).resolve().parent / "rule_severities.json"
    overrides = load_severity_overrides(config_path if config_path.exists() else None)

    files = _collect_cpp_files(root)
    by_file: list[dict] = []
    total_severity: Counter = Counter()
    total_rule: Counter = Counter()

    for f in files:
        try:
            violations = analyze_file(f, rules, overrides)
        except Exception as e:
            by_file.append({
                "path": str(f.relative_to(root)),
                "error": str(e),
                "findings": [],
                "counts": {},
            })
            continue

        counts = Counter(v["severity"] for v in violations)
        for v in violations:
            total_severity[v["severity"]] += 1
            total_rule[v["rule"]] += 1

        by_file.append({
            "path": str(f.relative_to(root)),
            "error": None,
            "findings": violations,
            "counts": dict(counts),
        })

    files_with_findings = sum(1 for entry in by_file if entry["findings"])

    return {
        "root": str(root.resolve()),
        "files_scanned": len(files),
        "files_with_findings": files_with_findings,
        "totals": {
            "error": total_severity.get("error", 0),
            "warning": total_severity.get("warning", 0),
            "info": total_severity.get("info", 0),
            "hint": total_severity.get("hint", 0),
            "total": sum(total_severity.values()),
        },
        "by_rule": dict(total_rule),
        "by_file": by_file,
    }


def _print_human(result: dict) -> None:
    print(f"Scanned: {result['root']}")
    print(f"Files:   {result['files_scanned']} scanned, "
          f"{result['files_with_findings']} with findings")
    print(f"Totals:  {result['totals']['error']} error, "
          f"{result['totals']['warning']} warning, "
          f"{result['totals']['info']} info, "
          f"{result['totals']['hint']} hint")
    print()

    if result["by_rule"]:
        print("By rule:")
        for rule, count in sorted(result["by_rule"].items(), key=lambda x: -x[1]):
            print(f"  {rule}: {count}")
        print()

    print("By file:")
    for entry in result["by_file"]:
        if entry["error"]:
            print(f"  {entry['path']}: FAILED — {entry['error']}")
            continue
        n = len(entry["findings"])
        if n == 0:
            continue
        sev_summary = ", ".join(
            f"{count} {sev}" for sev, count in sorted(entry["counts"].items())
        )
        print(f"  {entry['path']}: {n} ({sev_summary})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Project-wide rule scan.")
    ap.add_argument("directory", type=str)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = Path(args.directory)
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        sys.exit(2)

    result = scan(root)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_human(result)

    sys.exit(1 if result["totals"]["total"] > 0 else 0)


if __name__ == "__main__":
    main()

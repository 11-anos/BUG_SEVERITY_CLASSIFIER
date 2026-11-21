from dataclasses import dataclass
from typing import Callable


@dataclass
class Violation:
    rule: str
    line: int
    col: int
    message: str


@dataclass
class RuleSpec:
    name: str
    default_severity: str
    fn: Callable

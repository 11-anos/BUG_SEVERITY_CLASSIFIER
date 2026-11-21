# guard_walker.py — scope + state assertions + structured facts on a C++ UAST.
# Stage B: state model (replaces guard-name model).
#
# Run: python3 guard_walker.py <file.cpp> [--facts]

import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser, Node

CPP_LANGUAGE = Language(tscpp.language())
parser = Parser(CPP_LANGUAGE)

DECLARATOR_WRAPPERS = {"reference_declarator", "pointer_declarator", "array_declarator"}

TERMINATOR_TYPES = {
    "return_statement",
    "throw_statement",
    "break_statement",
    "continue_statement",
    "goto_statement",
}

NULL_LITERAL_TEXT = {"nullptr", "NULL", "null", "0"}


def unwrap_declarator(node: Node | None) -> Node | None:
    if node is None:
        return None
    if node.type == "identifier":
        return node
    if node.type in DECLARATOR_WRAPPERS:
        inner = node.child_by_field_name("declarator")
        if inner is not None:
            return unwrap_declarator(inner)
        for c in node.named_children:
            if c.type == "identifier":
                return c
    return None


def gather_identifiers(node: Node) -> list[Node]:
    out: list[Node] = []

    def rec(n: Node) -> None:
        if n.type == "identifier":
            out.append(n)
        for c in n.children:
            rec(c)

    rec(node)
    return out


def _is_null_literal(node: Node) -> bool:
    if node.type in ("nullptr", "null"):
        return True
    if node.type == "number_literal" and node.text.decode() in NULL_LITERAL_TEXT:
        return True
    if node.type == "identifier" and node.text.decode() in NULL_LITERAL_TEXT:
        return True
    return False


def condition_states(value: Node | None) -> tuple[dict[str, str], dict[str, str]]:
    """For a condition expression, return (true_branch_states, false_branch_states).

    Each is a map var_name -> "safe"|"unsafe". Empty dict means "no assertion".
    Conservative: anything we can't classify gets no entry.
    """
    if value is None:
        return {}, {}
    t = value.type

    if t == "identifier":
        name = value.text.decode()
        return {name: "safe"}, {name: "unsafe"}

    if t == "unary_expression":
        op = value.child_by_field_name("operator")
        arg = value.child_by_field_name("argument")
        if (op is not None and op.text.decode() == "!"
                and arg is not None and arg.type == "identifier"):
            name = arg.text.decode()
            return {name: "unsafe"}, {name: "safe"}
        return {}, {}

    if t == "binary_expression":
        op = value.child_by_field_name("operator")
        left = value.child_by_field_name("left")
        right = value.child_by_field_name("right")
        if op is None or left is None or right is None:
            return {}, {}
        op_text = op.text.decode()

        if op_text == "&&":
            l_t, _ = condition_states(left)
            r_t, _ = condition_states(right)
            return {**l_t, **r_t}, {}
        if op_text == "||":
            _, l_f = condition_states(left)
            _, r_f = condition_states(right)
            return {}, {**l_f, **r_f}

        if op_text in ("!=", "=="):
            ident, lit = None, None
            if left.type == "identifier":
                ident, lit = left, right
            elif right.type == "identifier":
                ident, lit = right, left
            if ident is None or lit is None or not _is_null_literal(lit):
                return {}, {}
            name = ident.text.decode()
            if op_text == "!=":
                return {name: "safe"}, {name: "unsafe"}
            else:
                return {name: "unsafe"}, {name: "safe"}

        return {}, {}

    return {}, {}


def ends_in_terminator(node: Node) -> bool:
    if node.type in TERMINATOR_TYPES:
        return True
    meaningful = [c for c in node.named_children if c.type != "comment"]
    if not meaningful:
        return False
    last = meaningful[-1]
    if last.type in TERMINATOR_TYPES:
        return True
    if last.type == "compound_statement":
        return ends_in_terminator(last)
    return False


@dataclass
class Scope:
    kind: str
    start_line: int
    bindings: dict[str, Node] = field(default_factory=dict)


class ScopeStack:
    def __init__(self) -> None:
        self.stack: list[Scope] = []

    def push(self, scope: Scope) -> None:
        self.stack.append(scope)

    def pop(self) -> None:
        self.stack.pop()

    def resolve(self, name: str) -> Scope | None:
        for scope in reversed(self.stack):
            if name in scope.bindings:
                return scope
        return None


@dataclass
class Assertion:
    var: str
    state: str       # "safe" | "unsafe"
    line: int        # line of the if that produced it
    kind: str        # "if-consequence" | "if-else" | "early-exit"


@dataclass
class DeclFact:
    name: str
    line: int
    col: int
    scope_kind: str
    scope_line: int
    is_param: bool
    ancestors: list[tuple[str, int]]


@dataclass
class UseFact:
    name: str
    line: int
    col: int
    scope_kind: str | None
    scope_line: int | None
    state: str                        # "safe" | "unsafe" | "unknown"
    state_kind: str | None            # which assertion produced it
    state_line: int | None
    context: str
    ancestors: list[tuple[str, int]]


@dataclass
class TerminatorEvent:
    line: int
    col: int
    kind: str
    parent_block_line: int | None


class Walker:
    def __init__(self, log) -> None:
        self.scopes = ScopeStack()
        self.assertions: list[Assertion] = []
        self.log = log
        self.decls: list[DeclFact] = []
        self.uses: list[UseFact] = []
        self.terminators: list[TerminatorEvent] = []
        self.ancestors: list[tuple[str, int]] = []

    # ---- scope helpers -----------------------------------------------------

    def _emit_decl(self, scope: Scope, ident: Node, is_param: bool) -> None:
        self.decls.append(DeclFact(
            name=ident.text.decode(),
            line=ident.start_point[0] + 1,
            col=ident.start_point[1],
            scope_kind=scope.kind,
            scope_line=scope.start_line,
            is_param=is_param,
            ancestors=list(self.ancestors),
        ))

    def _bind_declaration(self, scope: Scope, decl: Node) -> None:
        for d in decl.named_children:
            if d.type == "init_declarator":
                ident = unwrap_declarator(d.child_by_field_name("declarator"))
                if ident is not None:
                    scope.bindings[ident.text.decode()] = ident
                    self._emit_decl(scope, ident, is_param=False)
            elif d.type == "identifier":
                scope.bindings[d.text.decode()] = d
                self._emit_decl(scope, d, is_param=False)

    def _collect_declarations(self, scope: Scope, node: Node) -> None:
        if node.type == "declaration":
            self._bind_declaration(scope, node)
            return
        for child in node.named_children:
            if child.type == "parameter_declaration":
                ident = unwrap_declarator(child.child_by_field_name("declarator"))
                if ident is not None:
                    scope.bindings[ident.text.decode()] = ident
                    self._emit_decl(scope, ident, is_param=True)
            elif child.type == "declaration":
                self._bind_declaration(scope, child)

    # ---- assertion helpers -------------------------------------------------

    def _resolve_state(self, name: str) -> Assertion | None:
        for a in reversed(self.assertions):
            if a.var == name:
                return a
        return None

    def _push_states(self, states: dict[str, str], line: int, kind: str) -> list[Assertion]:
        pushed = [Assertion(var=v, state=s, line=line, kind=kind) for v, s in states.items()]
        self.assertions.extend(pushed)
        return pushed

    def _pop_count(self, n: int) -> None:
        if n > 0:
            del self.assertions[-n:]

    # ---- the walk ----------------------------------------------------------

    def walk(self, node: Node, context: str = "read") -> None:
        self.ancestors.append((node.type, node.start_point[0] + 1))
        try:
            self._walk_inner(node, context)
        finally:
            self.ancestors.pop()

    def _walk_inner(self, node: Node, context: str) -> None:
        t = node.type

        if t in TERMINATOR_TYPES:
            parent_block_line: int | None = None
            if len(self.ancestors) >= 2:
                parent_type, parent_line = self.ancestors[-2]
                if parent_type == "compound_statement":
                    parent_block_line = parent_line
            self.terminators.append(TerminatorEvent(
                line=node.start_point[0] + 1,
                col=node.start_point[1],
                kind=t.replace("_statement", ""),
                parent_block_line=parent_block_line,
            ))

        if t == "function_definition":
            decl = node.child_by_field_name("declarator")
            body = node.child_by_field_name("body")
            fn_name = "<anon>"
            if decl is not None and decl.type == "function_declarator":
                n = decl.child_by_field_name("declarator")
                if n is not None:
                    fn_name = n.text.decode()
            scope = Scope(kind=f"function:{fn_name}", start_line=node.start_point[0] + 1)
            if decl is not None and decl.type == "function_declarator":
                params = decl.child_by_field_name("parameters")
                if params is not None:
                    self._collect_declarations(scope, params)
            self.scopes.push(scope)
            self.log(f"ENTER  {scope.kind}  line={scope.start_line}  params={sorted(scope.bindings)}")
            if body is not None:
                self.walk(body)
            self.log(f"EXIT   {scope.kind}  line={scope.start_line}")
            self.scopes.pop()
            return

        if t == "compound_statement":
            scope = Scope(kind="block", start_line=node.start_point[0] + 1)
            self._collect_declarations(scope, node)
            self.scopes.push(scope)
            self.log(f"ENTER  block  line={scope.start_line}  decls={sorted(scope.bindings)}")

            pushed_count = 0
            for child in node.named_children:
                self.walk(child)

                if child.type != "if_statement":
                    continue
                # Early-exit: no else, consequence terminates.
                alt = child.child_by_field_name("alternative")
                cons = child.child_by_field_name("consequence")
                if alt is not None or cons is None:
                    continue
                if not ends_in_terminator(cons):
                    continue
                cond = child.child_by_field_name("condition")
                cond_value = None
                if cond is not None and cond.type == "condition_clause":
                    cond_value = cond.child_by_field_name("value")
                _, false_states = condition_states(cond_value)
                if not false_states:
                    continue
                line = child.start_point[0] + 1
                pushed = self._push_states(false_states, line, "early-exit")
                pushed_count += len(pushed)
                self.log(
                    f"ASSERT+ early-exit@{line}  "
                    f"{sorted((a.var, a.state) for a in pushed)}"
                )

            if pushed_count:
                del self.assertions[-pushed_count:]
                self.log(f"ASSERT- early-exit (x{pushed_count})")

            self.log(f"EXIT   block  line={scope.start_line}")
            self.scopes.pop()
            return

        if t == "for_statement":
            scope = Scope(kind="for", start_line=node.start_point[0] + 1)
            init = node.child_by_field_name("initializer")
            if init is not None:
                self._collect_declarations(scope, init)
            self.scopes.push(scope)
            self.log(f"ENTER  for  line={scope.start_line}  decls={sorted(scope.bindings)}")
            for fname in ("condition", "update", "body"):
                child = node.child_by_field_name(fname)
                if child is not None:
                    self.walk(child)
            self.log(f"EXIT   for  line={scope.start_line}")
            self.scopes.pop()
            return

        if t == "for_range_loop":
            scope = Scope(kind="for_range", start_line=node.start_point[0] + 1)
            decl = node.child_by_field_name("declarator")
            if decl is not None:
                ident = decl if decl.type == "identifier" else unwrap_declarator(decl)
                if ident is not None:
                    scope.bindings[ident.text.decode()] = ident
                    self._emit_decl(scope, ident, is_param=False)
            self.scopes.push(scope)
            self.log(f"ENTER  for_range  line={scope.start_line}  decls={sorted(scope.bindings)}")
            for fname in ("right", "body"):
                child = node.child_by_field_name(fname)
                if child is not None:
                    self.walk(child)
            self.log(f"EXIT   for_range  line={scope.start_line}")
            self.scopes.pop()
            return

        if t == "if_statement":
            cond = node.child_by_field_name("condition")
            cons = node.child_by_field_name("consequence")
            alt = node.child_by_field_name("alternative")
            line = node.start_point[0] + 1

            if cond is not None:
                self.walk(cond, context="condition")

            cond_value = None
            if cond is not None and cond.type == "condition_clause":
                cond_value = cond.child_by_field_name("value")
            true_states, false_states = condition_states(cond_value)

            if cons is not None:
                pushed = self._push_states(true_states, line, "if-consequence")
                if pushed:
                    self.log(
                        f"ASSERT+ if-consequence@{line}  "
                        f"{sorted((a.var, a.state) for a in pushed)}"
                    )
                self.walk(cons)
                self._pop_count(len(pushed))

            if alt is not None:
                pushed = self._push_states(false_states, line, "if-else")
                if pushed:
                    self.log(
                        f"ASSERT+ if-else@{line}  "
                        f"{sorted((a.var, a.state) for a in pushed)}"
                    )
                self.walk(alt)
                self._pop_count(len(pushed))
            return

        if t == "call_expression":
            fn = node.child_by_field_name("function")
            if fn is not None:
                self.walk(fn, context="callee")
            args = node.child_by_field_name("arguments")
            if args is not None:
                self.walk(args, context="call_arg")
            return

        if t == "condition_clause":
            value = node.child_by_field_name("value")
            if value is not None:
                self.walk(value, context="condition")
            return

        if t == "update_expression":
            arg = node.child_by_field_name("argument")
            if arg is not None:
                self.walk(arg, context="write")
            return

        if t == "declaration":
            for child in node.named_children:
                if child.type == "init_declarator":
                    val = child.child_by_field_name("value")
                    if val is not None:
                        self.walk(val)
            return

        if t == "parameter_declaration":
            return

        if t == "identifier":
            name = node.text.decode()
            line = node.start_point[0] + 1
            col = node.start_point[1]
            scope = self.scopes.resolve(name)
            scope_str = f"{scope.kind} @ line={scope.start_line}" if scope else "UNRESOLVED"
            assertion = self._resolve_state(name)
            if assertion is None:
                state_str = "unknown"
            else:
                state_str = f"{assertion.state}({assertion.kind}@{assertion.line})"
            self.log(f"  USE  {name!r}  line={line}  -> {scope_str}  [{state_str}]  ctx={context}")
            self.uses.append(UseFact(
                name=name,
                line=line,
                col=col,
                scope_kind=scope.kind if scope else None,
                scope_line=scope.start_line if scope else None,
                state=assertion.state if assertion else "unknown",
                state_kind=assertion.kind if assertion else None,
                state_line=assertion.line if assertion else None,
                context=context,
                ancestors=list(self.ancestors[:-1]),
            ))
            return

        for child in node.children:
            self.walk(child, context=context)


def main() -> None:
    args = sys.argv[1:]
    facts = False
    if "--facts" in args:
        facts = True
        args.remove("--facts")

    if not args:
        print("usage: guard_walker.py <file.cpp> [--facts]", file=sys.stderr)
        sys.exit(1)

    path = Path(args[0])
    src = path.read_bytes()
    tree = parser.parse(src)

    w = Walker(print)
    w.walk(tree.root_node)

    if facts:
        print("\n=== FACTS (JSON) ===")
        print(json.dumps({
            "declarations": [asdict(d) for d in w.decls],
            "uses": [asdict(u) for u in w.uses],
            "terminators": [asdict(t) for t in w.terminators],
        }, indent=2))


if __name__ == "__main__":
    main()
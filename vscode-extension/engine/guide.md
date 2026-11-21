Rule authoring guide
This document describes the YAML rule format used by engine/rules.py. A rule is a small mapping that selects facts and reports findings. This guide is complete — reading it should be enough to write a valid rule without inspecting the loader source.

If you are an LLM: read this entire file before writing rules. The "Limitations" section is as important as the schema — a rule that looks correct but uses unsupported syntax will load without error and match nothing.

Contents
Quick reference

Where rules live

Fact types and fields

Condition operators

Message templates

require_sibling

Worked examples

Testing a rule

Limitations — what this format cannot express

Common mistakes

1. Quick reference
A rule is a YAML mapping with these keys:

Key	Required	Type	Notes
name	yes	string	Unique. Overrides any Python rule with the same name.
severity	no	error | warning | info | hint	Default: warning.
select	yes	uses | decls | terminators	Which fact pool to iterate.
where	no	mapping	Filter conditions. Implicit AND across keys.
require_sibling	no	mapping	See §6. If present, candidate is only flagged when no matching sibling exists.
message	yes	string	Template; {field} interpolated from the selected fact.
Minimum valid rule:

yaml
- name: example
  select: uses
  where:
    name: { eq: malloc }
  message: "malloc used at line {line}"
The select field determines which fields are available in where and message. See §3.

2. Where rules live
Rules are loaded from engine/rules.yaml, resolved relative to rules.py (script-relative, not cwd-relative). The file is a top-level YAML list:

yaml
- name: rule-one
  # ...

- name: rule-two
  # ...
Load order: Python rules are registered first, then YAML rules are merged in. YAML wins by name. If a YAML rule has the same name as a Python rule (unchecked-param-use, malloc-without-free, no-dead-code), the YAML version replaces the Python one entirely.

Empty or missing file: treated as "no YAML rules." Python rules run unchanged. No error.

Malformed YAML or missing required key: rules.py prints the loader error to stderr and exits with code 2.

Unknown severity: exits with code 2, listing valid severities.

3. Fact types and fields
The engine emits three kinds of facts. The select key chooses one. Every field on the selected fact type is queryable in where, and available as {field} in the message.

uses — every identifier use in expression position
Field	Type	Values / meaning
name	string	The identifier's text.
line	int	1-indexed.
col	int	0-indexed.
scope_kind	string or null	The scope this name resolved to: "function:NAME", "block", "for", "for_range", or null if unresolved.
scope_line	int or null	Start line of that scope.
state	string	"safe" | "unsafe" | "unknown". See §3.1.
state_kind	string or null	"if-consequence" | "if-else" | "early-exit" | null. Which assertion set the state.
state_line	int or null	Line of the if that produced the state.
context	string	"read" | "write" | "callee" | "call_arg" | "condition". See §3.2.
ancestors	list	Ancestor (type, line) pairs from root to parent. Not meaningfully queryable via where — see §9.
3.1 state semantics
State describes what the enclosing path knows about a variable at the point of the use, based on if-conditions encountered.

"safe" — a preceding check established the variable is valid (e.g. if (!p) return; before this use).

"unsafe" — a preceding check established the opposite (e.g. inside if (p == nullptr) { … }).

"unknown" — no assertion applies.

The engine extracts assertions from these condition shapes only:

Condition	True branch	False branch
x	x: safe	x: unsafe
!x	x: unsafe	x: safe
x != nullptr (or NULL, null, 0)	x: safe	x: unsafe
x == nullptr	x: unsafe	x: safe
a && b	union of true-states of a and b	(none)
a || b	(none)	union of false-states of a and b
Anything else — x.size() > 0, x[j] > y, arbitrary expressions — produces no assertion. The variable's state remains whatever it was before.

3.2 context semantics
Context	When
read	Ordinary read: a = x + 1.
write	Assignment target or update: x = 1, x++.
callee	Function name position in a call: the swap in swap(a, b).
call_arg	Argument position: the a in swap(a, b).
condition	Inside an if / while / for condition clause.
Method-call receivers are reported as callee: in v.size(), the v is context: callee. (Known imprecision — a future version may split this.)

decls — every declaration
Field	Type	Values / meaning
name	string	Declared name.
line	int	1-indexed.
col	int	0-indexed.
scope_kind	string	Scope that owns the declaration.
scope_line	int	Start line of that scope.
is_param	bool	True for function parameters.
decls facts describe bindings. They do not have a context or state.

terminators — control-flow exits
Field	Type	Values / meaning
line	int	1-indexed.
col	int	0-indexed.
kind	string	"return" | "throw" | "break" | "continue" | "goto".
parent_block_line	int or null	Line of the enclosing compound_statement if this terminator is a direct child of one, else null.
matches_param — a pseudo-field on uses
In a where clause for select: uses, the key matches_param: true filters to uses whose name, scope, and line resolve to a function parameter of the same function. Its only valid value is true.

yaml
where:
  matches_param: true
  context: { neq: condition }
This is the mechanism by which a rule can ask "is this use of a function parameter?" without needing a cross-fact join.

4. Condition operators
Every where entry maps a field name to either a bare value or a single-operator mapping.

Form	Meaning
field: value	Equality. Shorthand for {eq: value}.
{ eq: value }	Equality.
{ neq: value }	Inequality.
{ in: [a, b, c] }	Value is one of the listed values.
{ not_in: [a, b, c] }	Value is none of the listed values.
No other operators exist. gt, lt, regex, contains, matches are not supported and will raise a load-time error (they will be caught as unknown condition operators).

Multiple keys under where are ANDed:

yaml
where:
  context: { eq: callee }
  name:    { eq: malloc }
matches facts where both conditions hold.

5. Message templates
The message is a Python str.format() template. Placeholders are {field} where field is any of the selected fact's fields.

Available placeholders (any fact type):

{name}

{line}

{col}

{scope_kind}

{scope_line}

Only for select: uses:

{context}

{state}

{state_kind}

{state_line}

Only for select: terminators:

{kind}

{parent_block_line}

Unavailable placeholders render as empty strings (no error). A placeholder with an unrecognized name is a load-time error.

Good examples:

yaml
message: "parameter '{name}' of {scope_kind} used at line {line} ({context}) with state='{state}'"
message: "malloc at line {line} has no subsequent free in the same function"
message: "call to '{name}' at line {line} is not inside an if"
6. require_sibling
Optional. When present, a candidate fact from select is flagged only if no matching sibling fact exists. This is how you express "X without a matching Y."

yaml
- name: malloc-without-free
  severity: warning
  select: uses
  where:
    context: { eq: callee }
    name:    { eq: malloc }
  require_sibling:
    select: uses
    where:
      context: { eq: callee }
      name:    { eq: free }
    same_function: true
    position_after: true
  message: "malloc at line {line} has no subsequent free in the same function"
Fields inside require_sibling:

Key	Required	Meaning
select	yes	Which fact pool to search. Usually the same as the outer select.
where	no	Same condition syntax as §4.
same_function	no	If true, sibling must be in the same enclosing function_definition.
position_after	no	If true, sibling must have a strictly greater line than the candidate.
Semantics: for each candidate fact, walk the sibling pool. If any fact matches where AND satisfies same_function (when set) AND satisfies position_after (when set), the candidate is skipped. Otherwise the candidate is reported.

same_function is computed by scanning ancestors for a function_definition entry. Both the candidate and the sibling must have one, and the lines must match. Facts outside any function (e.g. top-level uses) will not satisfy same_function.

7. Worked examples
7.1 Flag every call to a specific function
yaml
- name: no-raw-printf
  severity: warning
  select: uses
  where:
    context: { eq: callee }
    name:    { eq: printf }
  message: "printf at line {line} — prefer std::cout"
What it does: iterates uses, selects callee-position printf, reports each. No sibling, no state. This is the simplest rule shape.

7.2 Flag parameter uses that aren't in a safe state
yaml
- name: unchecked-param-use
  severity: warning
  select: uses
  where:
    matches_param: true
    context: { not_in: [condition] }
    state:   { not_in: [safe] }
  message: "parameter '{name}' of {scope_kind} used at line {line} ({context}) with state='{state}'"
What it does: selects uses, filters to parameters (matches_param: true), excludes uses that appear in a condition (the condition itself is not "using" the param), excludes uses whose state is "safe". Reports the rest.

Why condition is excluded: a param used in if (!p) is establishing the state, not using the variable under an unchecked assumption.

7.3 Flag malloc calls with no subsequent free in the same function
See §6 for the full rule. This is the canonical require_sibling shape.

7.4 Flag calls to a specific function that are not inside an if
yaml
- name: swap-must-be-in-if
  severity: warning
  select: uses
  where:
    context: { eq: callee }
    name:    { eq: swap }
  message: "call to 'swap' at line {line} is not inside an if"
Wait — this rule does not check the "inside an if" part. The current format cannot query ancestors meaningfully (§9). The rule as written flags every swap call regardless of context. Do not write this rule as-is — it will over-report.

This example is included deliberately, as a cautionary note: the format is not expressive enough for "inside an X" rules unless X can be reduced to a fact that the engine already emits as a separate fact type. If you need that rule, it must be written in Python.

8. Testing a rule
Add the rule to engine/rules.yaml, then run against a fixture:

text
cd /home/brad/Desktop/Practice/pbl
.venv/bin/python3 vscode-extension/engine/rules.py vscode-extension/fixtures/cpp/<file>.cpp
To see the fact stream a rule is matching against, use --facts:

text
.venv/bin/python3 vscode-extension/engine/guard_walker.py vscode-extension/fixtures/cpp/<file>.cpp --facts
This prints every DeclFact, UseFact, and TerminatorEvent as JSON. If a rule matches nothing, check the fact stream first — the fields the rule queries are visible there.

To check the whole project at once:

text
.venv/bin/python3 vscode-extension/engine/scan.py vscode-extension/fixtures/cpp
Corrupt-rule diagnostic: if a rule fails to load, rules.py exits with code 2 and prints a message naming the missing or invalid field. Read that message; it points at the offending rule.

9. Limitations — what this format cannot express
Read this section before writing a rule. If a rule idea requires any of these, it must be written in Python (add a function to rules.py and register a RuleSpec).

No regex or substring matching on names. name conditions support eq, neq, in, not_in only. There is no matches: or regex: operator. To match "any function starting with str", you would need to enumerate them in an in: list, or move to Python.

No numeric comparisons. No gt, lt, gte, lte. You cannot express "flag this use if there are more than 3 of them" in a rule. Aggregation is not a rule capability.

No querying ancestors for containment. ancestors is a list of (type, line) pairs. You can only compare it for equality against another list, which is useless in practice. There is no way to express "this use is inside an if / loop / try block" as a YAML rule, even though ancestors holds that information. The swap-must-be-in-if example in §7.4 illustrates this gap.

No negation of an entire where clause. Each condition is positive ("this field equals X") or negative on one field ("this field is not X"). There is no way to say "not (A and B)."

No OR across different fields. Two keys in where are ANDed. You cannot say "context is callee OR name is malloc."

No cross-file analysis. A rule sees one file's facts. You cannot express "this function is called from another file" or "this header declares the type used here."

No source-text access. Rules see structured facts, not raw text. You cannot regex a comment, a string literal, or an expression.

No user-defined severity per finding. Severity is a single value per rule. All findings from a rule share it.

No aggregation or counting. A rule reports facts one by one. It cannot say "if a file has more than N findings of another rule, report once."

No interaction with other rules. Rules run independently. A rule cannot suppress another rule's findings, escalate them, or depend on them.

10. Common mistakes
Wrong field for the selected fact type. select: uses with where: { is_param: true } will match nothing, because uses facts don't have is_param. If the intent was parameters, use matches_param: true instead. If the intent was the declaration itself, use select: decls with is_param: true.

Using state on non-uses facts. Only uses have state. A decls rule with where: { state: { eq: safe } } will match nothing.

Mistaking context: callee for "the function being called is X". In swap(a, b), the swap identifier has context: callee. Its name is "swap". This is correct. But in v.size(), the v also has context: callee — because the receiver of a method call is classified as callee for simplicity. If your rule needs "the identifier being called", this ambiguity can cause false positives.

Expecting require_sibling to enforce a specific order across branches. position_after: true compares line numbers, not control-flow order. A sibling that appears textually later but is unreachable on the current path will still count.

Assuming an unmatched rule is a bug in the loader. A rule that matches nothing is usually a field-name typo or a field that doesn't exist on the selected fact type. Use --facts (§8) to see the actual shape.

Forgetting matches_param only accepts true. Writing matches_param: false will raise a load error. To filter for non-parameters, you cannot use matches_param — you'd need a different rule shape.

Writing a rule whose message template references a field the fact doesn't have. The renderer substitutes empty string silently, so the message will read as "used at line " with no name. Check field availability per §3.

Appendix: severity semantics
Severity is used for sorting output and coloring diagnostics. It does not affect whether a rule runs. The four values map to VSCode's diagnostic severities:

Rule severity	VSCode severity
error	Error (red squiggle)
warning	Warning (yellow squiggle)
info	Information (blue squiggle)
hint	Hint (grey, faint)
The user-editable file engine/rule_severities.json overrides a rule's declared severity. This is separate from YAML — a rule can declare warning in rules.yaml and the user can promote it to error in rule_severities.json without touching the rule definition. When both exist, rule_severities.json wins.

End of guide.

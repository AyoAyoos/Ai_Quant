"""
Sandboxed strategy runner (worker process).

This is the ONLY place AI-generated strategy code executes. It is designed to
be spawned as a subprocess by the orchestrator (``backtest_service``) and run
standalone during development:

    python -m app.services.strategy_runner --data data.csv [--cash 100000] [--commission 0.1] [--sizer-percents 95] < strategy.py

Input protocol:
  * strategy code  -> stdin (avoids Windows argv length/quoting limits)
  * data + config  -> argv (paths, numeric knobs)

Output protocol:
  * one sentinel-prefixed JSON line on stdout: ``__BT_RESULT__ <json>``
    {"ok": true, "metrics": {...}}  or  {"ok": false, "error": "..."}
  * anything the strategy prints goes to stdout/stderr BEFORE the sentinel
    (the parent caps captured bytes); the sentinel is the last line.
  * non-zero exit code on failure.

Security note: this is a GUARDRAIL, not a sandbox. The real boundary is the
isolated subprocess + timeout (hard memory/process sandboxing is a Phase 5
item). The ``ast`` pre-check only refuses the obvious escape hatches so
accidental/dumb malicious code fails fast and cheap.
"""
import argparse
import ast
import json
import math
import sys
import types
import uuid
from datetime import datetime

import backtrader as bt

RESULT_MARKER = "__BT_RESULT__"

# Imports beyond these fail the guardrail.
ALLOWED_IMPORTS = {"backtrader", "pandas", "numpy", "math", "datetime"}

# Builtin/attribute names that are escape/capability hatches. Calls are
# refused; dunder attribute access (and the escape-y dunder classes) too.
BLOCKED_CALLS = {
    "exec", "eval", "open", "input", "compile", "globals", "locals",
    "vars", "breakpoint", "getattr", "setattr", "delattr", "__import__",
}
BLOCKED_DUNDER_ATTRS = {
    "__class__", "__subclasses__", "__base__", "__bases__", "__mro__",
    "__globals__", "__builtins__", "__import__", "__getattribute__",
    "__reduce__", "__reduce_ex__", "__getstate__", "__setstate__",
    "__subclasshook__",
}
# Referencing these module-level dunders as bare names is refused too.
BLOCKED_DUNDER_NAMES = BLOCKED_DUNDER_ATTRS

TIMEOUT_DEFAULT_SECONDS = 120


# --------------------------------------------------------------------------- #
# Guardrail (ast static analysis)
# --------------------------------------------------------------------------- #
class GuardrailError(Exception):
    pass


class _Guardrails(ast.NodeVisitor):
    def visit_Import(self, node):
        for alias in node.names:
            self._check_root(alias.name, node)
            self.generic_visit(node)

    def visit_ImportFrom(self, node):
        self._check_root(node.module or "", node)
        self.generic_visit(node)

    def _check_root(self, name: str, node) -> None:
        root = name.split(".")[0]
        if root not in ALLOWED_IMPORTS:
            raise GuardrailError(f"refused import: {name}")

    def visit_Attribute(self, node):
        if node.attr in BLOCKED_DUNDER_ATTRS:
            raise GuardrailError(f"refused attribute access: .{node.attr}")
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id in BLOCKED_DUNDER_NAMES:
            raise GuardrailError(f"refused name reference: {node.id}")
        self.generic_visit(node)

    def _walk_call_names(self, node):
        """Yield every name used in a call function position."""
        func = node.func
        if isinstance(func, ast.Name):
            yield func.id
        elif isinstance(func, ast.Attribute):
            yield func.attr

    def visit_Call(self, node):
        for name in self._walk_call_names(node):
            if name in BLOCKED_CALLS:
                raise GuardrailError(f"refused call to: {name}()")
        self.generic_visit(node)


def check_guardrails(code: str) -> None:
    """Raise GuardrailError if the code trips a static rule. No execution."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise GuardrailError(f"strategy code does not parse: {exc.args[0]}")

    visitor = _Guardrails()
    try:
        visitor.visit(tree)
    except GuardrailError:
        raise
    except Exception as exc:  # defensively treat any ast hiccup as a reject
        raise GuardrailError(f"guardrail analysis failed: {exc}")

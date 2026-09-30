import ast
import re


REQUIRED_IMPORT = "import backtrader as bt"
STRATEGY_CLASS_NAME = "GeneratedStrategy"


def validate_strategy_code(code: str) -> dict:
    """
    Perform static validation of AI-generated Backtrader strategy code.

    This function DOES NOT execute the generated code.
    """

    errors = []
    warnings = []

    # ---------------------------------------------------------
    # 1. Basic checks
    # ---------------------------------------------------------
    if not code or not code.strip():
        return {
            "valid": False,
            "errors": ["Strategy code is empty."],
            "warnings": [],
        }

    code = code.strip()

    # ---------------------------------------------------------
    # 2. Python syntax validation
    # ---------------------------------------------------------
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        location = f"line {exc.lineno}" if exc.lineno else "unknown line"

        return {
            "valid": False,
            "errors": [
                f"Python syntax error at {location}: {exc.msg}"
            ],
            "warnings": [],
        }

    # ---------------------------------------------------------
    # 3. Required Backtrader import
    # ---------------------------------------------------------
    has_backtrader_import = False

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "backtrader" and alias.asname == "bt":
                    has_backtrader_import = True

    if not has_backtrader_import:
        errors.append(
            "Missing required import: import backtrader as bt"
        )

    # ---------------------------------------------------------
    # 4. Check imports
    # ---------------------------------------------------------
    allowed_imports = {"backtrader"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in allowed_imports:
                    errors.append(
                        f"Unsupported import: {alias.name}"
                    )

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""

            if module != "backtrader":
                errors.append(
                    f"Unsupported import: from {module} import ..."
                )

    # ---------------------------------------------------------
    # 5. Find GeneratedStrategy class
    # ---------------------------------------------------------
    strategy_class = None

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if node.name == STRATEGY_CLASS_NAME:
                strategy_class = node
                break

    if strategy_class is None:
        errors.append(
            "Required class 'GeneratedStrategy' was not found."
        )

    # ---------------------------------------------------------
    # 6. Validate inheritance
    # ---------------------------------------------------------
    if strategy_class is not None:

        inherits_backtrader = False

        for base in strategy_class.bases:

            # bt.Strategy
            if (
                isinstance(base, ast.Attribute)
                and isinstance(base.value, ast.Name)
                and base.value.id == "bt"
                and base.attr == "Strategy"
            ):
                inherits_backtrader = True

        if not inherits_backtrader:
            errors.append(
                "GeneratedStrategy must inherit from bt.Strategy."
            )

    # ---------------------------------------------------------
    # 7. Check next() method
    # ---------------------------------------------------------
    if strategy_class is not None:

        has_next_method = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "next"
            for node in strategy_class.body
        )

        if not has_next_method:
            errors.append(
                "GeneratedStrategy must contain a next() method."
            )

    # ---------------------------------------------------------
    # 8. Security checks
    # ---------------------------------------------------------
    forbidden_names = {
        "exec",
        "eval",
        "compile",
        "__import__",
        "open",
        "input",
    }

    forbidden_modules = {
        "os",
        "sys",
        "subprocess",
        "socket",
        "shutil",
        "pathlib",
    }

    for node in ast.walk(tree):

        # Dangerous function calls
        if isinstance(node, ast.Call):

            if isinstance(node.func, ast.Name):
                if node.func.id in forbidden_names:
                    errors.append(
                        f"Forbidden function usage: {node.func.id}()"
                    )

            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in {
                    "system",
                    "popen",
                    "remove",
                    "unlink",
                }:
                    errors.append(
                        f"Potentially unsafe function usage: {node.func.attr}()"
                    )

        # Dangerous imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_module = alias.name.split(".")[0]

                if root_module in forbidden_modules:
                    errors.append(
                        f"Forbidden module import: {alias.name}"
                    )

        if isinstance(node, ast.ImportFrom):
            if node.module:
                root_module = node.module.split(".")[0]

                if root_module in forbidden_modules:
                    errors.append(
                        f"Forbidden module import: {node.module}"
                    )

    # ---------------------------------------------------------
    # 9. Check for runnable script boilerplate
    # ---------------------------------------------------------
    if re.search(r"if\s+__name__\s*==\s*[\"']__main__[\"']", code):
        warnings.append(
            "Runnable __main__ block found. It should be removed before execution."
        )

    if "cerebro.run(" in code:
        warnings.append(
            "cerebro.run() found. The backtest engine should control execution."
        )

    if "cerebro.plot(" in code:
        warnings.append(
            "cerebro.plot() found. Plotting should be handled by the application."
        )

    # ---------------------------------------------------------
    # 10. Final result
    # ---------------------------------------------------------
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
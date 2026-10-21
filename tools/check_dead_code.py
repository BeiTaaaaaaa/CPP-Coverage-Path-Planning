"""Find unused imports and unreferenced module-level definitions.

A refactor that leaves dead helpers behind is not a correctness bug, but in a
repository meant to be read and reused it is a real defect: a reader cannot tell
a dormant function from a load-bearing one.  This checks the library modules
(not the experiments, which are entry points and legitimately reference little).
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "cppclip"


def names_used(tree: ast.AST) -> set[str]:
    """Every identifier that appears anywhere in the module's code."""
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Names referenced from docstrings / __all__ entries.
            used.add(node.value)
    return used


def check(path: pathlib.Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    used = names_used(tree)
    problems: list[str] = []

    imported: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.append(((alias.asname or alias.name).split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom):
            # `from __future__ import annotations` is a compiler directive, not a
            # name binding, so it can never be "used".
            if node.module == "__future__":
                continue
            for alias in node.names:
                if alias.name != "*":
                    imported.append((alias.asname or alias.name, node.lineno))

    raw = src.splitlines()
    for name, lineno in imported:
        # One textual use is the import line itself.
        hits = sum(
            1
            for i, line in enumerate(raw, 1)
            if name in line and i != lineno
        )
        if hits == 0:
            problems.append(f"L{lineno}: unused import {name!r}")

    defined: list[tuple[str, int]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.append((node.name, node.lineno))

    exported = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "__all__":
                    try:
                        exported = {ast.literal_eval(node.value)}  # type: ignore[assignment]
                        exported = set(next(iter(exported))) if exported else set()
                    except Exception:  # noqa: BLE001
                        pass

    for name, lineno in defined:
        if name in exported or name.startswith("__"):
            continue
        hits = sum(1 for i, line in enumerate(raw, 1) if name in line and i != lineno)
        if hits == 0:
            problems.append(f"L{lineno}: {name!r} defined but never referenced")

    return problems


def main() -> None:
    total = 0
    for path in sorted(PKG.glob("*.py")):
        problems = check(path)
        if problems:
            print(f"{path.name}:")
            for p in problems:
                print(f"  {p}")
            total += len(problems)
    if total:
        print(f"\n{total} issue(s)")
        sys.exit(1)
    print("no unused imports or dead module-level definitions")


if __name__ == "__main__":
    main()

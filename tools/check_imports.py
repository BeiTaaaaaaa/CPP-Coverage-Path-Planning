"""Import every module and script: catches broken references a refactor left behind.

``compileall`` only checks syntax, and a missing name raised inside a function
body is not a syntax error.  Importing executes the module-level code and
resolves every module-level reference, which is the part a refactor most often
breaks.

Package modules are imported through their real dotted names -- loading
``cppclip/planner.py`` as a file would fail on its relative imports and prove
nothing.  Scripts that need the Fields2Cover container are skipped: they cannot
run outside it by construction, and ``tools/setup_fields2cover.sh`` documents
how to run them.
"""

from __future__ import annotations

import importlib
import importlib.util
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Scripts that require the Fields2Cover container, or that shell out to Docker.
CONTAINER_ONLY = {"f2c_benchmark.py", "f2c_example.py"}


def import_package_modules() -> tuple[int, list[str]]:
    sys.path.insert(0, str(ROOT / "src"))
    checked, problems = 0, []
    for path in sorted((ROOT / "src" / "cppclip").glob("*.py")):
        name = f"cppclip.{path.stem}" if path.stem != "__init__" else "cppclip"
        try:
            importlib.import_module(name)
            checked += 1
        except Exception:  # noqa: BLE001
            problems.append(f"{path.relative_to(ROOT)}: {traceback.format_exc().strip().splitlines()[-1]}")
    return checked, problems


def import_scripts() -> tuple[int, list[str]]:
    for d in ("experiments", "tests"):
        sys.path.insert(0, str(ROOT / d))
    checked, problems = 0, []
    for rel in ("experiments", "tests", "tools", "examples"):
        for path in sorted((ROOT / rel).glob("*.py")):
            if path.name in CONTAINER_ONLY:
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"_probe_{path.stem}", path)
                module = importlib.util.module_from_spec(spec)
                # Register before executing so dataclasses and friends resolve.
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)  # type: ignore[union-attr]
                checked += 1
            except Exception:  # noqa: BLE001
                problems.append(f"{path.relative_to(ROOT)}: {traceback.format_exc().strip().splitlines()[-1]}")
    return checked, problems


def main() -> None:
    n1, p1 = import_package_modules()
    n2, p2 = import_scripts()
    problems = p1 + p2
    for p in problems:
        print(f"  FAIL {p}")
    print(f"\n{n1 + n2} modules imported cleanly, {len(problems)} failed")
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()

"""AVS-TST-DOI-001 / T11.2 — transitive import graph of the DOI package.

DOI-11 claim: "No DOI component may call a provider". The testable form is
stronger than "does not call": no provider client may be IMPORTABLE from the
DOI package, transitively.

This probe parses the AST of every DOI module (no execution, so nothing can
reach a network), follows first-party imports transitively, and reports any
module in the closure whose name or content indicates a provider client.

Interpreter: venv\\Scripts\\python.exe
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

DOI_MODULES = [
    "domain/dynamic_options_intelligence.py",
    "domain/contract_family_generation.py",
    "domain/deterministic_option_valuation.py",
    "domain/dynamic_options_lifecycle.py",
    "domain/dynamic_options_outcomes.py",
    "domain/dynamic_options_probability.py",
    "domain/dynamic_options_projection.py",
    "domain/dynamic_options_ranking.py",
    "canonical_data/dynamic_options_bridge.py",
    "canonical_data/dynamic_options_family.py",
    "canonical_data/dynamic_options_lifecycle.py",
    "canonical_data/dynamic_options_outcomes.py",
    "canonical_data/dynamic_options_probability.py",
    "canonical_data/dynamic_options_production.py",
    "canonical_data/dynamic_options_projection.py",
    "canonical_data/dynamic_options_ranking.py",
    "canonical_data/dynamic_options_valuation.py",
    "contracts/dynamic_options_policy.py",
]

PROVIDER_TOKENS = (
    "polygon", "marketdata", "market_data", "fred", "tastytrade", "tasty",
    "anthropic", "openai", "alpaca", "tradier", "iex", "quandl",
)
NETWORK_TOKENS = ("requests", "httpx", "urllib", "aiohttp", "socket", "websocket", "http.client")


def module_to_path(name: str) -> Path | None:
    candidate = ROOT / (name.replace(".", "/") + ".py")
    if candidate.exists():
        return candidate
    package = ROOT / name.replace(".", "/") / "__init__.py"
    if package.exists():
        return package
    return None


def imports_of(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return set()
    found: set[str] = set()
    package = path.parent.relative_to(ROOT).as_posix().replace("/", ".")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import
                base = package
                for _ in range(node.level - 1):
                    base = base.rpartition(".")[0]
                found.add(f"{base}.{node.module}" if node.module else base)
            elif node.module:
                found.add(node.module)
    return found


def main() -> int:
    seen: set[str] = set()
    queue: list[tuple[str, str]] = []
    external: dict[str, set[str]] = {}

    for relative in DOI_MODULES:
        name = relative[:-3].replace("/", ".")
        queue.append((name, "<root>"))

    closure: dict[str, str] = {}
    while queue:
        name, parent = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        path = module_to_path(name)
        if path is None:
            external.setdefault(name.split(".")[0], set()).add(parent)
            continue
        closure[name] = parent
        for imported in imports_of(path):
            if imported not in seen:
                queue.append((imported, name))

    print(f"first-party modules in the DOI transitive closure: {len(closure)}")
    for name in sorted(closure):
        print(f"  {name}")

    print(f"\nexternal / stdlib roots reached: {len(external)}")
    print("  " + ", ".join(sorted(external)))

    print("\n--- provider-client check ---")
    hits = []
    for name in sorted(closure) + sorted(external):
        lowered = name.lower()
        for token in PROVIDER_TOKENS:
            if token in lowered:
                hits.append((name, token, closure.get(name, "external")))
    for name in sorted(external):
        lowered = name.lower()
        for token in NETWORK_TOKENS:
            if lowered == token or lowered.startswith(token + "."):
                hits.append((name, f"NETWORK:{token}", "external"))

    if hits:
        print("  *** PROVIDER OR NETWORK MODULE REACHABLE ***")
        for name, token, parent in hits:
            print(f"    {name}  (matched {token}, imported by {parent})")
    else:
        print("  none: no provider client and no network library is importable")
        print("  from the DOI package, transitively.")

    print("\nRESULT:", "FAIL" if hits else "PASS")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())

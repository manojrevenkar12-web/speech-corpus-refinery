"""The refinery decides from what it fetched, never from the test world's answers.

Only the harness (`scr.world`, `scr.evaluation`, `scr.heldout`, `scr.pipeline`, `scr.cli`) may
know about truth files. Every other module must not import it or mention them, so a decision
cannot quietly depend on the answer.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "scr"
HARNESS = {"world", "evaluation", "heldout", "pipeline", "cli"}


def _decision_modules() -> list[Path]:
    out = []
    for p in SRC.rglob("*.py"):
        rel = p.relative_to(SRC)
        if rel.parts[0] in HARNESS or rel.stem in HARNESS:
            continue
        out.append(p)
    return out


def _imports(p: Path) -> set[str]:
    names: set[str] = set()
    pkg = ".".join(("scr", *p.relative_to(SRC).parent.parts))
    for node in ast.walk(ast.parse(p.read_text())):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parent = pkg.split(".")[: len(pkg.split(".")) - node.level + 1]
                base = ".".join([*parent, base] if base else parent)
            names.add(base)
            names |= {f"{base}.{a.name}" for a in node.names}
    return names


def test_decision_code_never_imports_the_harness():
    assert len(_decision_modules()) > 20
    for p in _decision_modules():
        bad = {n for n in _imports(p) for h in HARNESS if n == f"scr.{h}" or n.startswith(f"scr.{h}.")}
        assert not bad, f"{p.relative_to(SRC)} imports {bad}"


def test_decision_code_never_mentions_truth_files():
    for p in _decision_modules():
        text = p.read_text().lower()
        assert "truth" not in text and "world.yaml" not in text, p.relative_to(SRC)

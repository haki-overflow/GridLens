"""List every top-level name defined in the Python and TypeScript sources, so a
move-only merge of files can be proven to lose or duplicate nothing.

    python tools/names.py snapshot out.json     # write the current names
    python tools/names.py compare out.json      # compare with a snapshot
A name may move between files; it may not disappear or appear twice.
"""
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# names renamed on purpose during the merges (old -> new)
RENAMED = {"page": ["page_problem"], "EXAMPLE": ["DISPATCH_EXAMPLE", "UNITS_EXAMPLE"]}
SKIP = {"venv", "node_modules", "legacy", "tests", "__pycache__", "dist"}


def py_names(path):
    out = []
    for n in ast.parse(path.read_text()).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append(n.name)
        elif isinstance(n, ast.Assign):
            out += [t.id for t in n.targets if isinstance(t, ast.Name)]
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            out.append(n.target.id)
    return out


TS = re.compile(r"^(?:export\s+)?(?:async\s+)?(?:function|class|const|let|interface|type)\s+([A-Za-z_]\w*)", re.M)


def scan():
    names = {}
    files = list(ROOT.glob("*.py")) + [p for d in ("api", "tools", "legacy") for p in (ROOT / d).glob("*.py")]
    for p in files:
        names[str(p.relative_to(ROOT))] = py_names(p)
    for p in (ROOT / "web" / "src").glob("*.ts"):
        names[str(p.relative_to(ROOT))] = TS.findall(p.read_text())
    return names


def flatten(d):
    out = {}
    for f, ns in d.items():
        for n in ns:
            out.setdefault(n, []).append(f)
    return out


def main():
    cmd, path = sys.argv[1], Path(sys.argv[2])
    if cmd == "snapshot":
        path.write_text(json.dumps(scan(), indent=1))
        flat = flatten(scan())
        dup = {n: f for n, f in flat.items() if len(f) > 1 and not n.startswith("__")}
        print(f"{sum(map(len, scan().values()))} names in {len(scan())} files; "
              f"{len(dup)} names defined in more than one file")
        for n, f in sorted(dup.items())[:60]:
            print("  ", n, "->", ", ".join(f))
        return 0
    old, new = flatten(json.loads(path.read_text())), flatten(scan())
    lost = sorted(n for n in set(old) - set(new)
                  if not all(r in new for r in RENAMED.get(n, [])) or n not in RENAMED)
    print("lost:", lost or "none")
    extra_dup = {n: f for n, f in new.items() if len(f) > 1 and len(old.get(n, [])) <= 1}
    print("newly duplicated:", extra_dup or "none")
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())

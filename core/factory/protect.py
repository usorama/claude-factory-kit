"""The person's gate on the factory's own rules: no model changes them by itself.

Protected: the factory scripts (factory/), factory.toml (roles, models, budget, landing), every prompt
(.ai/prompts/), the rules (.ai/factory-rules.md, .ai/defect-library.md, .ai/factory-agents.md).
factory init, factory roles accept and factory approve record a snapshot under var/factory/protected/. When any
protected file differs from it, the clock does not run and says which files changed; a person reads the change with
`factory approve` and records it with `factory approve --yes`. A chief session that edits a rule, a prompt or the
budget therefore stops the factory until a person agrees.
Usage: protect.py [--yes]      show the changes (exit 1 when there are some); --yes records them
"""
import difflib
import hashlib
import json
import shutil
import sys
from pathlib import Path

from common import log, now, var

FILES = ("factory.toml", ".ai/factory-rules.md", ".ai/defect-library.md", ".ai/factory-agents.md")
FOLDERS = ("factory", ".ai/prompts")
SKIP = ("__pycache__",)


def protected(root):
    root = Path(root)
    found = [root / name for name in FILES if (root / name).is_file()]
    for folder in FOLDERS:
        found += [p for p in (root / folder).rglob("*") if p.is_file() and not set(p.parts) & set(SKIP)]
    return sorted(str(p.relative_to(root)) for p in found)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def store(root):
    return var(root) / "protected"


def snapshot(root):
    """Record the current protected files as approved."""
    root, folder = Path(root), store(root)
    if folder.exists():
        shutil.rmtree(folder)
    (folder / "files").mkdir(parents=True)
    manifest = {}
    for name in protected(root):
        manifest[name] = digest(root / name)
        target = folder / "files" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
    (folder / "manifest.json").write_text(json.dumps({"at": now(), "files": manifest}, indent=1))
    return manifest


def changes(root):
    """Protected files added, removed or edited since the last approval. No snapshot at all counts as a change."""
    root, manifest = Path(root), store(root) / "manifest.json"
    if not manifest.exists():
        return ["(no approved snapshot yet: run factory approve)"]
    approved = json.loads(manifest.read_text())["files"]
    current = {name: digest(root / name) for name in protected(root)}
    return sorted(name for name in set(approved) | set(current) if approved.get(name) != current.get(name))


def diff(root, names):
    root, lines = Path(root), []
    for name in names:
        old_path, new_path = store(root) / "files" / name, root / name
        old = old_path.read_text().splitlines() if old_path.exists() else []
        new = new_path.read_text().splitlines() if new_path.exists() else []
        lines += difflib.unified_diff(old, new, f"approved/{name}", name, lineterm="")
    return "\n".join(lines)


def main(argv=None, root=None):
    args = sys.argv[1:] if argv is None else argv
    root = Path(root or Path.cwd())
    names = changes(root)
    if not names:
        print("protected files: no change since the last approval")
        return 0
    if "--yes" in args:
        snapshot(root)
        log(root, event="approved", files=names, note=f"a person approved changes to {', '.join(names)}")
        print(f"approved: {', '.join(names)}")
        return 0
    print(diff(root, names) or "\n".join(names))
    print(f"\n{len(names)} protected file(s) changed. Read the change above; approve it with: factory approve --yes")
    return 1


if __name__ == "__main__":
    sys.exit(main())

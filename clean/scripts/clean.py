#!/usr/bin/env python3
"""Retire worktrees proven stale, and optionally collect idle mbx storage.

A worktree is retired only when it is registered, unlocked, not a main worktree,
clean including untracked files, has no process working in it, and its branch is
merged into the base or its upstream is gone (a detached HEAD must be reachable
from a branch or tag). Every check that fails or cannot run preserves the
checkout.

git refuses to remove a worktree holding an initialized submodule. Removing it
also deletes that submodule's per-worktree git directory, so the one `--force`
this script uses comes only after every submodule is clean and has no commit
missing from its remotes and tags.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# The skill directory is linked into repositories; keep it free of bytecode.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import inventory_worktrees as inv  # noqa: E402

MBX_BUDGET = "25GiB"

# A checkout under the temp directory is a session's scratch copy, and the
# session that made it may come back; the OS already reaps these.
TEMP_ROOTS = {str(Path(tempfile.gettempdir()).resolve()), str(Path("/tmp").resolve())}


def git(path: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, check=False)


def working_dirs() -> set[str]:
    """Every process's cwd. Failing to list them means activity is unknown."""
    out = subprocess.run(["lsof", "-n", "-a", "-d", "cwd", "-Fn"], capture_output=True, text=True, check=False)
    if not out.stdout:
        raise RuntimeError(f"lsof listed no working directories: {out.stderr.strip()}")
    return {line[1:] for line in out.stdout.splitlines() if line.startswith("n")}


def own_checkouts() -> set[str]:
    """The checkout this runs from, and the agent's project, are always active."""
    roots = set()
    for start in (os.getcwd(), os.environ.get("CLAUDE_PROJECT_DIR")):
        if start:
            top = git(start, "rev-parse", "--show-toplevel")
            if top.returncode == 0:
                roots.add(top.stdout.strip())
    return roots


def busy(path: str, cwds: set[str], own: set[str]) -> bool:
    return path in own or any(c == path or c.startswith(path + "/") for c in cwds)


def stale_reason(wt: dict[str, Any]) -> str | None:
    """Why the worktree must stay, or None when it qualifies."""
    branch = wt.get("branch") or {}
    if not wt.get("exists"):
        return "missing"
    if any(wt["path"].startswith(root + "/") for root in TEMP_ROOTS):
        return "a session's scratch checkout"
    if wt.get("is_main_worktree") or wt.get("bare"):
        return "main worktree"
    if wt.get("locked"):
        return "locked"
    if wt.get("errors"):
        return "inspection failed"
    if not wt.get("clean"):
        return "uncommitted or untracked files"
    if wt.get("head_merged_into_base") or branch.get("upstream_track") == "[gone]":
        return None
    if wt.get("detached") and wt.get("containing_refs"):
        return None
    return "not merged and upstream still exists"


def submodule_blocker(path: str) -> str | None:
    """Why the submodules make removal unsafe, or None when nothing would be lost."""
    probe = (
        "git status --porcelain --untracked-files=all; "
        "git log --oneline -1 HEAD --branches --not --remotes --tags"
    )
    out = git(path, "submodule", "foreach", "--recursive", "--quiet", probe)
    if out.returncode != 0:
        return f"submodule inspection failed: {out.stderr.strip()}"
    if out.stdout.strip():
        return "a submodule has changes or commits missing from its remotes"
    return None


def retire(path: str, cwds: set[str], own: set[str]) -> tuple[str, str]:
    # Re-check right before acting: the inventory may be minutes old.
    status = git(path, "status", "--porcelain", "--untracked-files=all", "--ignore-submodules=none")
    if status.returncode != 0 or status.stdout.strip():
        return "kept", "changed since the inventory"
    if busy(path, cwds, own):
        return "kept", "a process is working in it"

    plain = git(path, "worktree", "remove", path)
    if plain.returncode == 0:
        return "removed", ""
    if "submodules" not in plain.stderr:
        return "kept", plain.stderr.strip()

    blocker = submodule_blocker(path)
    if blocker:
        return "kept", blocker
    forced = git(path, "worktree", "remove", "--force", path)
    if forced.returncode == 0:
        return "removed", "with submodules"
    return "kept", forced.stderr.strip()


def collect_mbx() -> str:
    if not shutil.which("mbx"):
        return "mbx: not installed, skipped"
    building = [subprocess.run(["pgrep", "-x", name], capture_output=True, check=False) for name in ("cargo", "rustc")]
    if any(proc.returncode == 0 for proc in building):
        return "mbx: a build is running, skipped"
    out = subprocess.run(["mbx", "gc", "--max-size", MBX_BUDGET], capture_output=True, text=True, check=False)
    return "mbx: " + (out.stdout.strip() or out.stderr.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("roots", nargs="*", type=Path, help="Roots containing Git worktrees")
    parser.add_argument("--dry-run", action="store_true", help="List what would be retired; change nothing")
    parser.add_argument("--gc", action="store_true", help=f"Also run mbx gc with a {MBX_BUDGET} budget when no build is running")
    args = parser.parse_args()

    roots = [root.expanduser().resolve() for root in args.roots] or inv.default_roots()
    report = inv.inventory(roots, max_depth=4, sizes=False)
    cwds, own = working_dirs(), own_checkouts()

    rows = []
    for repo in report["repositories"]:
        for wt in repo["worktrees"]:
            path = wt["path"]
            branch = (wt.get("branch") or {}).get("name") or "(detached)"
            reason = stale_reason(wt) or ("a process is working in it" if busy(path, cwds, own) else None)
            if reason:
                rows.append(("keep", path, branch, reason))
            elif args.dry_run:
                rows.append(("retire", path, branch, ""))
            else:
                result, note = retire(path, cwds, own)
                rows.append((result, path, branch, note))

    for action, path, branch, note in sorted(rows, key=lambda r: (r[0], r[1])):
        print(f"{action:8} {path}  [{branch}]" + (f"  {note}" if note else ""))
    counts = {a: sum(1 for r in rows if r[0] == a) for a in sorted({r[0] for r in rows})}
    print(" ".join(f"{a}={n}" for a, n in counts.items()))

    if args.gc and not args.dry_run:
        print(collect_mbx())
    return 0


if __name__ == "__main__":
    sys.exit(main())

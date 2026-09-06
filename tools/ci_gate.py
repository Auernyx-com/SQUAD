#!/usr/bin/env python3
"""
squad-alteration-gate's fail-closed check.

Adapted from Auernyx-com/auernyx-agent-mk2's tools/ci_gate.py, as a
deliberate proof of concept that the same governance-authorization pattern
(a PR must add a real, allowlist-verified authorization record, or it
cannot merge) generalizes to a second, independent application -- SQUAD is
its own repo, not a branch or subdirectory of Mk2/AVRS; this is that
pattern reused, not a shared codebase.

Two checks, both fail-closed (raise SystemExit on any failure, print PASS
only if every check clears):

1. AUTHORIZATION RECORD REQUIRED -- ported directly from Mk2. Every PR must
   add at least one governance authorization record under
   governance/alteration-program/authorization/records/, and that record
   must name an authorizedBy login present in allowlist.json, with a valid
   non-future ISO date and a non-empty reason.

2. PROVENANCE MUST VERIFY -- SQUAD-specific, using SQUAD's own existing
   Obsidian Judgment system (MODULES/OBSIDIAN_JUDGMENT) rather than
   inventing a new one. This is the piece Mk2's gate has no equivalent of:
   SQUAD's governance-hash-mismatch detection existed but nothing ever
   enforced it automatically (verified during a 2026-09-05 audit: the repo
   had an unresolved governance_hash_mismatch for ~6.5 months because
   nothing but a human manually running a QA script would ever notice).
   This gate now IS that automatic enforcement point -- every PR fails
   closed if provenance doesn't verify, instead of drifting silently.
   This check only blocks the merge; it does not itself write or clear any
   judgment record -- whether Obsidian Judgment should auto-activate a
   persistent judgment.v1.json on failure (vs. just failing this one CI
   run) is a separate, not-yet-decided policy question.

Mk2-specific checks that do NOT have a real SQUAD analog were deliberately
NOT ported rather than faked: Mk2's updates/incoming staging inbox and its
three hardcoded append-only ndjson trace file paths are Mk2-only concepts
with no equivalent structure in this repo (SQUAD's own audit trail,
SYSTEM/META/PROVENANCE/audit.ndjson, is intentionally gitignored and so
isn't something a git-diff-based check could see anyway).
"""
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def run(cmd, cwd: Path | None = None):
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise SystemExit(f"Command failed: {' '.join(cmd)}\n{p.stderr.strip()}")
    return p.stdout


def git_root() -> Path:
    out = run(["git", "-C", str(REPO_ROOT), "rev-parse", "--show-toplevel"]).strip()
    return Path(out)


def repo_prefix(groot: Path) -> str:
    rel = os.path.relpath(str(REPO_ROOT), str(groot))
    if rel == ".":
        return ""
    return rel.replace("\\", "/").rstrip("/") + "/"


GIT_ROOT = git_root()
PREFIX = repo_prefix(GIT_ROOT)

AUTH_RECORD_DIR = f"{PREFIX}governance/alteration-program/authorization/records"
ALLOWLIST_PATH = REPO_ROOT / "governance/alteration-program/authorization/allowlist.json"

GITHUB_LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


def fail(msg: str) -> None:
    raise SystemExit(f"Fail-closed: {msg}")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_changed_files(base_ref):
    diff = run(["git", "-C", str(GIT_ROOT), "diff", "--name-only", f"{base_ref}...HEAD"])
    return [f.strip() for f in diff.splitlines() if f.strip()]


def get_working_files():
    staged = run(["git", "-C", str(GIT_ROOT), "diff", "--name-only", "--cached"])
    staged_files = [f.strip() for f in staged.splitlines() if f.strip()]
    if staged_files:
        return staged_files, "staged"

    wt = run(["git", "-C", str(GIT_ROOT), "diff", "--name-only"])
    wt_files = [f.strip() for f in wt.splitlines() if f.strip()]
    return wt_files, "working"


def get_changed_auth_records(files):
    prefix = AUTH_RECORD_DIR + "/"
    return [f for f in files if f.startswith(prefix) and f.endswith(".json")]


def validate_auth_record(record_path: str) -> None:
    full_path = GIT_ROOT / record_path
    try:
        record = load_json(full_path)
    except Exception as e:
        fail(f"could not parse authorization record {record_path}: {e}")

    for field in ("authorizedBy", "authorizedAt", "reason"):
        if field not in record:
            fail(f"authorization record missing required field '{field}' in {record_path}")

    authorized_by = record["authorizedBy"]
    if not isinstance(authorized_by, str) or not GITHUB_LOGIN_RE.match(authorized_by):
        fail(f"authorizedBy must be a valid GitHub login (got {authorized_by!r}) in {record_path}")

    authorized_at = record["authorizedAt"]
    if not isinstance(authorized_at, str):
        fail(f"authorizedAt must be an ISO date string YYYY-MM-DD (got {authorized_at!r}) in {record_path}")
    try:
        parsed_date = date.fromisoformat(authorized_at)
    except ValueError:
        fail(f"authorizedAt must be a valid ISO date string YYYY-MM-DD (got {authorized_at!r}) in {record_path}")
    if parsed_date > date.today():
        fail(f"authorizedAt must not be a future date (got {authorized_at!r}) in {record_path}")

    if not isinstance(record.get("reason"), str) or not record["reason"].strip():
        fail(f"reason must be a non-empty string in {record_path}")

    if not ALLOWLIST_PATH.exists():
        fail(f"allowlist not found at {ALLOWLIST_PATH}")
    try:
        allowlist = load_json(ALLOWLIST_PATH)
    except Exception as e:
        fail(f"could not parse allowlist {ALLOWLIST_PATH}: {e}")

    allowed_logins = allowlist.get("authorizedLogins", [])
    if authorized_by not in allowed_logins:
        fail(f"authorizedBy '{authorized_by}' is not in the allowlist ({ALLOWLIST_PATH}). authorizedLogins: {allowed_logins}")


def assert_provenance_verifies() -> None:
    src = REPO_ROOT / "MODULES" / "OBSIDIAN_JUDGMENT" / "src"
    if not src.is_dir():
        # Module missing entirely would itself be worth failing on in a
        # real repo, but don't let a checkout oddity mask the real
        # authorization-record failure above with a confusing traceback.
        fail("MODULES/OBSIDIAN_JUDGMENT/src not found -- cannot verify provenance")

    sys.path.insert(0, str(src))
    from obsidian_judgment import is_judgment_active, read_judgment, verify_provenance  # type: ignore

    if is_judgment_active(REPO_ROOT):
        judgment = read_judgment(REPO_ROOT) or {}
        fail(f"an active Obsidian Judgment exists and must be resolved before merging: {judgment.get('failure')}")

    status = verify_provenance(REPO_ROOT)
    if not status.ok:
        fail(f"provenance verification failed ({status.code}): {status.reason}. details={status.details}")


def main():
    base_ref = os.environ.get("SQUAD_BASE_REF", "").strip()
    if base_ref:
        files = get_changed_files(base_ref)
        source = f"commit-diff:{base_ref}...HEAD"
    else:
        files, source = get_working_files()

    assert_provenance_verifies()

    if not files:
        print("SQUAD Alteration Gate: PASS (no-op diff, zero changes; provenance verified)")
        return

    auth_records = get_changed_auth_records(files)
    if len(auth_records) < 1:
        raise SystemExit(
            f"Fail-closed: must change/add at least ONE authorization record under "
            f"{AUTH_RECORD_DIR}/ (from {source}). "
            f"Found: {auth_records}"
        )

    for record in auth_records:
        validate_auth_record(record)

    print("SQUAD Alteration Gate: PASS (authorization record verified; provenance verified)")


if __name__ == "__main__":
    main()

"""
tests/test_alteration_gate_workflow.py

Coverage for two round-7 (2026-09-07) independent-audit findings in
.github/workflows/squad-alteration-gate.yml:

1. THE SCRIPT-INJECTION BUG (high). github.event.pull_request.head.ref --
   the PR's source branch name, fully controlled by whoever opens the PR --
   was spliced directly into `run:` bash blocks via `${{ }}`. GitHub Actions
   performs this substitution as a raw text splice into the step script
   BEFORE bash ever runs, so wrapping the expression in double quotes does
   not protect against it: a branch name containing a `"` followed by shell
   metacharacters (e.g. a `$(...)` command substitution) breaks out of the
   quotes and executes as a real shell command. Reproduced the mechanism
   directly with a crafted payload during the audit. Fixed by passing the
   value through `env:` instead (GitHub Actions sets env vars as real
   environment variable values, never spliced into the script text) and
   referencing it in bash as `"$HEAD_REF"` / `"$BASE_REF"`.

   This test can't spin up a real Actions runner, so it asserts against the
   workflow file's own source text: the vulnerable literal splice patterns
   must be gone, and the env-var indirection must be in place at every spot
   that used to be vulnerable.

2. THE MERE-REQUEST-COUNTS-AS-AUTHORIZATION BUG (medium). The
   auto-authorize job's allowlist check treated being *assigned* to a PR or
   merely *requested* as a reviewer (neither implies the person did
   anything) the same as an actual approval -- an outside actor could
   request review from the one allowlisted login and get `is_allowed=True`
   with zero real involvement from that person. Fixed by dropping
   assignee/requested-reviewer logins from the authorization chain, leaving
   only actual approvals and self-authorship by an allowlisted login.
"""
from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "squad-alteration-gate.yml"


class ScriptInjectionFixTest(unittest.TestCase):
    def setUp(self):
        self.content = WORKFLOW.read_text(encoding="utf-8")

    def test_head_ref_no_longer_spliced_directly_into_run_blocks(self):
        vulnerable_snippets = [
            'git fetch origin "${{ github.event.pull_request.head.ref }}"',
            'git checkout "${{ github.event.pull_request.head.ref }}"',
            'git reset --hard "origin/${{ github.event.pull_request.head.ref }}"',
            'git fetch origin "${{ github.base_ref }}"',
        ]
        for snippet in vulnerable_snippets:
            with self.subTest(snippet=snippet):
                self.assertNotIn(snippet, self.content)

    def test_head_ref_and_base_ref_now_flow_through_env(self):
        required_snippets = [
            'HEAD_REF: ${{ github.event.pull_request.head.ref }}',
            'BASE_REF: ${{ github.base_ref }}',
            'git fetch origin "$HEAD_REF"',
            'git checkout "$HEAD_REF"',
            'git reset --hard "origin/$HEAD_REF"',
            'git fetch origin "$BASE_REF"',
        ]
        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, self.content)

    def test_checkout_pr_head_branch_step_declares_env(self):
        # The two run: steps that use $HEAD_REF must each declare it via
        # env: immediately above -- not just have the string floating
        # somewhere else in the file.
        self.assertIn(
            'env:\n          HEAD_REF: ${{ github.event.pull_request.head.ref }}\n        run: |\n'
            '          git fetch origin "$HEAD_REF"\n          git checkout "$HEAD_REF"',
            self.content,
        )
        self.assertIn(
            'env:\n          HEAD_REF: ${{ github.event.pull_request.head.ref }}\n        run: |\n'
            '          git fetch origin "$HEAD_REF"\n          git reset --hard "origin/$HEAD_REF"',
            self.content,
        )


class AssigneeAndRequestedReviewerNoLongerAuthorizeTest(unittest.TestCase):
    def setUp(self):
        self.content = WORKFLOW.read_text(encoding="utf-8")

    def test_authorization_chain_excludes_assignees_and_requested_reviewers(self):
        self.assertNotIn(
            "for login in assignee_logins + reviewer_logins + approved_reviewer_logins + [actor]:",
            self.content,
        )
        self.assertIn(
            "for login in approved_reviewer_logins + [actor]:",
            self.content,
        )

    def test_assignees_and_requested_reviewers_still_parsed_for_logging_only(self):
        # They should still be fetched/printed for visibility -- just not
        # used to compute is_allowed.
        self.assertIn('assignee_logins = parse_logins("ASSIGNEES_JSON")', self.content)
        self.assertIn('reviewer_logins = parse_logins("REVIEWERS_JSON")', self.content)


if __name__ == "__main__":
    unittest.main()

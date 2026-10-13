"""Feedback hook for failed checks. The LLM implementation comes later; nothing here
may influence a verdict."""

from __future__ import annotations

from typing import Protocol

from grader.flasher import Submission
from grader.plan import Plan
from grader.report import CheckResult


class FeedbackGenerator(Protocol):
    def explain(self, check: CheckResult, plan: Plan, submission: Submission) -> str | None:
        """Return student-facing text explaining a FAIL, or None if unavailable."""
        ...


class NullFeedback:
    """No feedback (no LLM, no network)."""

    def explain(self, check: CheckResult, plan: Plan, submission: Submission) -> str | None:
        return None

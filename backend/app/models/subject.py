"""Shared shape for a per-subject-workspace stats slot.

Not a runtime-enforced schema — MongoDB via Motor is schemaless, so nothing
here is validated on write. This factory is the single source of truth for
what a freshly-created subject workspace looks like. It replaces four
independently hand-copied dict literals that used to live in auth.py's
create_user, auth.py's get_current_user fallback (which had silently
drifted to be missing two keys — cumulative_score, total_attempts —
compared to the other three copies), app.py's module-level _EMPTY_SUBJECT,
and app.py's switch_subject.
"""
from typing import Dict


def default_subject_stats() -> Dict:
    """Return a fresh, empty stats dict for a new subject workspace."""
    return {
        "weak_topics": [],
        "strong_topics": [],
        "proficiency_score": 0,
        "engagement_score": 0,
        "cumulative_score": 0.0,
        "total_attempts": 0,
    }


def subject_data(user: dict, subject: str) -> dict:
    """Return subject-scoped stats with safe defaults for new subjects."""
    return dict(default_subject_stats(), **user.get("subjects", {}).get(subject, {}))

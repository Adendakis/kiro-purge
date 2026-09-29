"""Safety-tiered deletion suggestions (read-only).

Builds a :class:`SuggestionReport` on top of a :class:`ProjectView`. It assigns
each project group's bytes to a confidence tier and reports how much space could
be reclaimed at each level. It NEVER deletes anything — acting on a suggestion
means running the ``clean`` command separately, which still enforces retention
and protection.

Tiers (most confident first), per Requirement 14.2:
  - "safe"        cache / logs / crash_reports / temp — framework-disposable
  - "likely-safe" chats + sessions of a resolved project whose folder is GONE
                  from disk and whose newest activity is older than retention
  - "review"      chats + sessions of a resolved project that still EXISTS but
                  is older than retention; and (unknown-project) data older than
                  retention
  - "keep"        everything else: protected data (index), history/uncategorized,
                  and anything newer than its retention period
"""

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from kiro_cleaner.project_view import (
    GLOBAL_GROUP,
    UNKNOWN_PROJECT_GROUP,
    ProjectView,
)
from kiro_cleaner.retention import DEFAULT_RETENTION

TIER_SAFE = "safe"
TIER_LIKELY_SAFE = "likely-safe"
TIER_REVIEW = "review"
TIER_KEEP = "keep"

TIER_ORDER = [TIER_SAFE, TIER_LIKELY_SAFE, TIER_REVIEW, TIER_KEEP]

# Categories that are framework-disposable regardless of project (the --safe set).
_SAFE_CATEGORIES = {"cache", "logs", "crash_reports", "temp"}
# Categories that represent conversation / agent history.
_HISTORY_CATEGORIES = {"chats", "sessions"}
# Categories that are always kept (protected or too ambiguous to suggest).
#   index    -> protected code-intelligence data
#   history  -> local edit/undo snapshots (retained conservatively)
#   uncategorized -> unknown content incl. protected state.vscdb / workspace.json
_KEEP_CATEGORIES = {"index", "history", "uncategorized"}


@dataclass
class SuggestionItem:
    """One project group's contribution to the suggestion report."""

    group: str
    tier: str
    reclaimable_bytes: int
    categories: dict[str, int] = field(default_factory=dict)
    project_exists: bool | None = None
    newest_mtime: float | None = None
    clean_hint: str | None = None


@dataclass
class SuggestionReport:
    """Read-only, safety-tiered summary of reclaimable storage."""

    items: list[SuggestionItem]
    tier_totals: dict[str, int]
    total_bytes: int


def project_folder_exists(project: str) -> bool:
    """True if ``project`` is a real absolute path that currently exists on disk.

    The pseudo-groups "(global)" and "(unknown-project)" are not paths and return
    False.
    """
    if not project or not project.startswith("/"):
        return False
    try:
        return Path(project).is_dir()
    except OSError:
        return False


def _age_days(mtime: float | None, now: float) -> float | None:
    if mtime is None:
        return None
    return (now - mtime) / 86400.0


def _is_old(category: str, newest_mtime: float | None, now: float) -> bool:
    """Whether the group's newest activity is older than the category retention."""
    retention = DEFAULT_RETENTION.get(category, 0)
    age = _age_days(newest_mtime, now)
    if age is None:
        return False
    return age > retention


def _quote(value: str) -> str:
    """Quote a value for a shell command if it contains spaces or parens."""
    if any(c in value for c in " ()'\""):
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _project_clean_hint(group: str) -> str:
    """Project-scoped clean command that targets exactly this group's files.

    For a resolved project folder this is ``clean --project <folder>``; for the
    unknown-project pseudo-group it is ``clean --project-group "(unknown-project)"``.
    Uses --dry-run so the printed command only previews.
    """
    if group.startswith("/"):
        return f"kiro-cleaner clean --project {_quote(group)} --dry-run"
    # Pseudo-group (e.g. (unknown-project)).
    return f"kiro-cleaner clean --project-group {_quote(group)} --dry-run"


def build_suggestions(
    kiro_storage: Path,
    view: ProjectView,
    now: float | None = None,
) -> SuggestionReport:
    """Assign each project group's bytes to a Safety_Tier (read-only).

    Splits every group's per-category bytes into tiers so the sum across tiers
    equals the total scanned bytes (Property 18). ``now`` is injectable for tests.
    """
    if now is None:
        now = time.time()

    items: list[SuggestionItem] = []
    tier_totals: dict[str, int] = {t: 0 for t in TIER_ORDER}
    total = 0

    for group in view.groups:
        exists = (
            project_folder_exists(group.project)
            if group.project not in (GLOBAL_GROUP, UNKNOWN_PROJECT_GROUP)
            else None
        )
        is_resolved_project = group.project.startswith("/")

        # Accumulate this group's bytes into per-tier category maps.
        per_tier_cats: dict[str, dict[str, int]] = {t: {} for t in TIER_ORDER}

        for category, nbytes in group.category_bytes.items():
            if nbytes <= 0:
                continue
            total += nbytes

            if category in _SAFE_CATEGORIES:
                tier = TIER_SAFE
            elif category in _KEEP_CATEGORIES:
                tier = TIER_KEEP
            elif category in _HISTORY_CATEGORIES:
                old = _is_old(category, group.newest_mtime, now)
                if not old:
                    tier = TIER_KEEP
                elif is_resolved_project and exists is False:
                    tier = TIER_LIKELY_SAFE
                elif is_resolved_project and exists is True:
                    tier = TIER_REVIEW
                else:
                    # unknown-project (or global, which has no history) that is old
                    tier = TIER_REVIEW
            else:
                tier = TIER_KEEP

            per_tier_cats[tier][category] = per_tier_cats[tier].get(category, 0) + nbytes
            tier_totals[tier] += nbytes

        # Emit one SuggestionItem per (group, tier) that has bytes.
        for tier in TIER_ORDER:
            cats = per_tier_cats[tier]
            if not cats:
                continue
            reclaimable = sum(cats.values())
            hint = None
            if tier in (TIER_LIKELY_SAFE, TIER_REVIEW):
                # Project-scoped command: deletes exactly this project's data.
                hint = _project_clean_hint(group.project)
            items.append(
                SuggestionItem(
                    group=group.project,
                    tier=tier,
                    reclaimable_bytes=reclaimable,
                    categories=cats,
                    project_exists=exists,
                    newest_mtime=group.newest_mtime,
                    clean_hint=hint,
                )
            )

    # Sort by tier confidence, then by reclaimable size desc.
    items.sort(key=lambda it: (TIER_ORDER.index(it.tier), -it.reclaimable_bytes))

    return SuggestionReport(items=items, tier_totals=tier_totals, total_bytes=total)

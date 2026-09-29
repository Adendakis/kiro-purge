"""Tests for the safety-tiered deletion suggestions (suggest.py)."""

import time
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from kiro_cleaner.project_view import (
    GLOBAL_GROUP,
    UNKNOWN_PROJECT_GROUP,
    ProjectGroup,
    ProjectView,
)
from kiro_cleaner.suggest import (
    TIER_KEEP,
    TIER_LIKELY_SAFE,
    TIER_REVIEW,
    TIER_SAFE,
    build_suggestions,
    project_folder_exists,
)

NOW = 1_800_000_000.0  # fixed reference time for deterministic ageing
DAY = 86400.0


def _mtime(days_ago: float) -> float:
    return NOW - days_ago * DAY


def _view(*groups: ProjectGroup) -> ProjectView:
    total = sum(g.total_bytes for g in groups)
    return ProjectView(groups=list(groups), total_bytes=total)


def _group(project, categories, days_ago=400):
    return ProjectGroup(
        project=project,
        total_bytes=sum(categories.values()),
        category_bytes=dict(categories),
        newest_mtime=_mtime(days_ago),
    )


def _tier_of(report, group_name, category=None):
    """Return the tier(s) a group's bytes landed in."""
    tiers = set()
    for it in report.items:
        if it.group == group_name and (category is None or category in it.categories):
            tiers.add(it.tier)
    return tiers


class TestProjectFolderExists:
    def test_existing_dir(self, tmp_path):
        assert project_folder_exists(str(tmp_path)) is True

    def test_missing_dir(self, tmp_path):
        assert project_folder_exists(str(tmp_path / "gone")) is False

    def test_pseudo_groups_are_false(self):
        assert project_folder_exists(GLOBAL_GROUP) is False
        assert project_folder_exists(UNKNOWN_PROJECT_GROUP) is False

    def test_non_absolute_is_false(self):
        assert project_folder_exists("relative/path") is False


class TestTierAssignment:
    def test_safe_categories_always_safe(self):
        g = _group(GLOBAL_GROUP, {"cache": 100, "logs": 50, "crash_reports": 10, "temp": 5})
        report = build_suggestions(Path("/nonexistent"), _view(g), now=NOW)
        assert _tier_of(report, GLOBAL_GROUP) == {TIER_SAFE}
        assert report.tier_totals[TIER_SAFE] == 165

    def test_index_and_history_kept(self):
        g = _group(GLOBAL_GROUP, {"index": 1000, "history": 500, "uncategorized": 20})
        report = build_suggestions(Path("/nonexistent"), _view(g), now=NOW)
        assert _tier_of(report, GLOBAL_GROUP) == {TIER_KEEP}
        assert report.tier_totals[TIER_KEEP] == 1520

    def test_old_history_missing_folder_is_likely_safe(self, tmp_path):
        gone = str(tmp_path / "deleted_project")
        g = _group(gone, {"sessions": 2000, "chats": 1000}, days_ago=400)
        report = build_suggestions(tmp_path, _view(g), now=NOW)
        assert _tier_of(report, gone) == {TIER_LIKELY_SAFE}
        assert report.tier_totals[TIER_LIKELY_SAFE] == 3000

    def test_old_history_existing_folder_is_review(self, tmp_path):
        exists = str(tmp_path)  # tmp_path exists
        g = _group(exists, {"sessions": 2000}, days_ago=400)
        report = build_suggestions(tmp_path, _view(g), now=NOW)
        assert _tier_of(report, exists) == {TIER_REVIEW}

    def test_recent_history_is_kept_even_if_folder_missing(self, tmp_path):
        gone = str(tmp_path / "deleted_but_recent")
        # sessions retention is 90 days; 10 days old => not old => keep
        g = _group(gone, {"sessions": 5000}, days_ago=10)
        report = build_suggestions(tmp_path, _view(g), now=NOW)
        assert _tier_of(report, gone) == {TIER_KEEP}
        assert report.tier_totals[TIER_LIKELY_SAFE] == 0

    def test_unknown_project_old_is_review(self):
        g = _group(UNKNOWN_PROJECT_GROUP, {"sessions": 4000}, days_ago=400)
        report = build_suggestions(Path("/nonexistent"), _view(g), now=NOW)
        assert _tier_of(report, UNKNOWN_PROJECT_GROUP) == {TIER_REVIEW}

    def test_clean_hint_present_for_actionable_tiers(self, tmp_path):
        gone = str(tmp_path / "gone")
        g = _group(gone, {"sessions": 2000}, days_ago=300)
        report = build_suggestions(tmp_path, _view(g), now=NOW)
        item = next(it for it in report.items if it.group == gone)
        assert item.clean_hint is not None
        assert "--category sessions" in item.clean_hint
        assert "--keep-recent" in item.clean_hint
        assert "--dry-run" in item.clean_hint

    def test_mixed_group_splits_across_tiers(self, tmp_path):
        """A group with both disposable and old-history bytes splits safe + likely-safe."""
        gone = str(tmp_path / "gone2")
        g = _group(gone, {"cache": 100, "sessions": 900}, days_ago=400)
        report = build_suggestions(tmp_path, _view(g), now=NOW)
        assert _tier_of(report, gone, "cache") == {TIER_SAFE}
        assert _tier_of(report, gone, "sessions") == {TIER_LIKELY_SAFE}


# Feature: kiro-cleaner-python, Property 18: Suggestion safety invariant


CATEGORY_BYTES = st.dictionaries(
    keys=st.sampled_from(
        ["cache", "logs", "crash_reports", "temp", "chats", "sessions",
         "index", "history", "uncategorized"]
    ),
    values=st.integers(min_value=0, max_value=10000),
    max_size=6,
)


@st.composite
def project_group_strategy(draw):
    name = draw(st.sampled_from([
        "/Users/x/proj-exists", "/Users/x/proj-gone",
        GLOBAL_GROUP, UNKNOWN_PROJECT_GROUP,
    ]))
    cats = draw(CATEGORY_BYTES)
    days = draw(st.integers(min_value=0, max_value=1000))
    total = sum(cats.values())
    return ProjectGroup(
        project=name,
        total_bytes=total,
        category_bytes=cats,
        newest_mtime=_mtime(days),
    )


@pytest.mark.property
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(groups=st.lists(project_group_strategy(), max_size=6))
def test_suggestion_safety_invariant(tmp_path_factory, groups):
    """Property 18: Suggestion safety invariant.

    (a) Tier totals sum to the total scanned bytes.
    (b) Protected/keep categories (index, history, uncategorized) never land in
        likely-safe or review.
    (c) Data within its retention period never lands in likely-safe or review.

    **Validates: Requirements 14.1, 14.2, 14.5, 14.7**
    """
    # Make "/Users/x/proj-exists" actually exist; leave "proj-gone" missing.
    base = tmp_path_factory.mktemp("disk")
    existing = base / "proj-exists"
    existing.mkdir()

    # Remap group names onto real/absent paths for a deterministic folder signal.
    remapped = []
    for g in groups:
        project = g.project
        if project == "/Users/x/proj-exists":
            project = str(existing)
        elif project == "/Users/x/proj-gone":
            project = str(base / "proj-gone")  # does not exist
        remapped.append(
            ProjectGroup(
                project=project,
                total_bytes=g.total_bytes,
                category_bytes=g.category_bytes,
                newest_mtime=g.newest_mtime,
            )
        )
    view = ProjectView(groups=remapped, total_bytes=sum(g.total_bytes for g in remapped))

    report = build_suggestions(base, view, now=NOW)

    # (a) partition: tier totals sum to total scanned bytes.
    assert sum(report.tier_totals.values()) == view.total_bytes
    assert report.total_bytes == view.total_bytes

    # (b) & (c): inspect each emitted item.
    protected_cats = {"index", "history", "uncategorized"}
    for it in report.items:
        if it.tier in (TIER_LIKELY_SAFE, TIER_REVIEW):
            # No protected/keep category may be suggested.
            assert not (set(it.categories) & protected_cats)
            # Only history categories are ever suggested.
            assert set(it.categories) <= {"chats", "sessions"}
            # And only when older than retention (90d for sessions, 30d for chats).
            age_days = (NOW - it.newest_mtime) / DAY
            assert age_days > 30  # min retention among suggestable categories

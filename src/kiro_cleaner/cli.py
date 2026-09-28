"""CLI interface for Kiro Cleaner using Click."""

import sys
from datetime import datetime
from pathlib import Path

import click

from kiro_cleaner import __version__
import tarfile

from kiro_cleaner.backup import create_backup, restore_backup
from kiro_cleaner.chat_filter import ChatFilterCriteria, filter_chats
from kiro_cleaner.cleaner import CleanResult, ErrorType, clean_files
from kiro_cleaner.config_manager import load_config, update_config
from kiro_cleaner.platform import kill_kiro_processes, resolve_platform
from kiro_cleaner.project_view import ProjectView, build_project_view
from kiro_cleaner.retention import filter_by_retention
from kiro_cleaner.scanner import format_size, scan_storage

VALID_CATEGORIES = ["logs", "cache", "chats", "sessions", "index", "temp", "history", "crash_reports"]


@click.group()
@click.version_option(version=__version__)
def main():
    """Kiro Cleaner - Clean up Kiro IDE artefacts safely."""
    pass


def _display_project_view(view: ProjectView) -> None:
    """Render a project-aggregated storage report (read-only)."""
    import time

    click.echo(
        f"{'Project':<40} {'Total':>10} {'Chats':>10} "
        f"{'Sessions':>10} {'Other':>10} {'Last activity':<16}"
    )
    click.echo(f"{'-' * 40} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 16}")

    for group in view.groups:
        chats = group.category_bytes.get("chats", 0)
        sessions = group.category_bytes.get("sessions", 0)
        other = group.total_bytes - chats - sessions
        last = (
            time.strftime("%Y-%m-%d", time.localtime(group.newest_mtime))
            if group.newest_mtime is not None
            else "-"
        )
        project = group.project
        if len(project) > 40:
            project = "..." + project[-37:]
        click.echo(
            f"{project:<40} "
            f"{format_size(group.total_bytes):>10} "
            f"{format_size(chats):>10} "
            f"{format_size(sessions):>10} "
            f"{format_size(other):>10} "
            f"{last:<16}"
        )

    click.echo(f"{'-' * 40} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 16}")
    click.echo(f"{'Total':<40} {format_size(view.total_bytes):>10}")


@main.command()
@click.option(
    "--by-project",
    is_flag=True,
    help="Group storage usage by owning project folder (read-only report).",
)
def scan(by_project):
    """Scan Kiro storage and display disk usage by category."""
    platform_info = resolve_platform()
    kiro_storage = platform_info.kiro_storage

    if not kiro_storage.exists():
        click.echo(
            f"[ERROR] Kiro storage not found at {kiro_storage}. "
            "No Kiro installation detected.",
            err=True,
        )
        sys.exit(1)

    result = scan_storage(kiro_storage)

    if by_project:
        view = build_project_view(kiro_storage, result)
        _display_project_view(view)
        for warning in result.warnings:
            click.echo(f"[WARN] {warning}", err=True)
        return

    # Display category table
    # Header
    click.echo(f"{'Category':<16} {'Files':>8} {'Size':>12}")
    click.echo(f"{'-' * 16} {'-' * 8} {'-' * 12}")

    # Category rows
    for category_name, category_result in result.categories.items():
        click.echo(
            f"{category_result.name:<16} "
            f"{category_result.file_count:>8} "
            f"{format_size(category_result.total_bytes):>12}"
        )

    # Uncategorized row
    click.echo(
        f"{'Uncategorized':<16} "
        f"{result.uncategorized.file_count:>8} "
        f"{format_size(result.uncategorized.total_bytes):>12}"
    )

    # Separator
    click.echo(f"{'-' * 16} {'-' * 8} {'-' * 12}")

    # Total row (last)
    click.echo(
        f"{'Total':<16} "
        f"{result.total_files:>8} "
        f"{format_size(result.total_bytes):>12}"
    )

    # Display warnings
    for warning in result.warnings:
        click.echo(f"[WARN] {warning}", err=True)


@main.command()
@click.argument("key", required=False)
@click.argument("value", required=False)
def config(key, value):
    """View or update configuration settings."""
    if key is None:
        # No args: display all config key-value pairs
        cfg = load_config()
        for field_name in sorted(vars(cfg)):
            click.echo(f"{field_name} = {getattr(cfg, field_name)}")
        return

    if value is None:
        # Key only: display that key's current value
        cfg = load_config()
        if not hasattr(cfg, key):
            valid_keys = sorted(vars(cfg))
            click.echo(
                f"Error: Unrecognized configuration key: '{key}'. "
                f"Valid keys are: {', '.join(valid_keys)}",
                err=True,
            )
            sys.exit(1)
        click.echo(f"{key} = {getattr(cfg, key)}")
        return

    # Key + value: update and persist
    try:
        updated = update_config(key, value)
        click.echo(f"Updated {key} = {getattr(updated, key)}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except OSError as e:
        click.echo(f"Error: Could not write configuration: {e}", err=True)
        sys.exit(1)


def _validate_date(date_str: str, flag_name: str) -> None:
    """Validate a date string is in YYYY-MM-DD format.

    Args:
        date_str: The date string to validate.
        flag_name: The flag name for error messages.

    Raises:
        SystemExit: If the date format is invalid.
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        click.echo(
            f"[ERROR] Invalid date format for {flag_name}: '{date_str}'. "
            "Expected format: YYYY-MM-DD",
            err=True,
        )
        sys.exit(1)


def _interactive_category_select(scan_result) -> list[str]:
    """Present an interactive numbered list for category selection.

    Args:
        scan_result: The ScanResult from scanning storage.

    Returns:
        List of selected category names.
    """
    click.echo("\nAvailable categories:")
    click.echo(f"{'#':<4} {'Category':<16} {'Files':>8} {'Size':>12}")
    click.echo(f"{'-' * 4} {'-' * 16} {'-' * 8} {'-' * 12}")

    for i, cat_name in enumerate(VALID_CATEGORIES, 1):
        cat_result = scan_result.categories[cat_name]
        click.echo(
            f"{i:<4} {cat_name:<16} "
            f"{cat_result.file_count:>8} "
            f"{format_size(cat_result.total_bytes):>12}"
        )

    click.echo()
    selection = click.prompt(
        "Enter category numbers to clean (comma-separated, e.g. 1,3,5)",
        type=str,
    )

    selected: list[str] = []
    for part in selection.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            idx = int(part)
            if 1 <= idx <= len(VALID_CATEGORIES):
                cat_name = VALID_CATEGORIES[idx - 1]
                if cat_name not in selected:
                    selected.append(cat_name)
            else:
                click.echo(
                    f"[WARN] Invalid selection '{part}': "
                    f"out of range (1-{len(VALID_CATEGORIES)})",
                    err=True,
                )
        except ValueError:
            click.echo(f"[WARN] Invalid selection '{part}': not a number", err=True)

    return selected


def _display_clean_summary(result: CleanResult, dry_run: bool) -> None:
    """Display the deletion summary with counts and error breakdown.

    Args:
        result: The CleanResult from the cleaning operation.
        dry_run: Whether this was a dry-run operation.
    """
    action = "Would delete" if dry_run else "Deleted"

    click.echo(f"\n{'=' * 40}")
    click.echo("Cleaning Summary")
    click.echo(f"{'=' * 40}")
    click.echo(f"{action}: {result.deleted_count} files ({format_size(result.deleted_bytes)})")

    if result.skipped_protected:
        click.echo(f"Protected (skipped): {len(result.skipped_protected)} files")

    if result.errors:
        # Group errors by type
        permission_errors = sum(
            1 for e in result.errors if e.error_type == ErrorType.PERMISSION
        )
        not_found_errors = sum(
            1 for e in result.errors if e.error_type == ErrorType.NOT_FOUND
        )
        other_errors = sum(
            1 for e in result.errors if e.error_type == ErrorType.OTHER
        )

        click.echo(f"\nErrors ({len(result.errors)} total):")
        if permission_errors:
            click.echo(f"  Permission errors: {permission_errors}")
        if not_found_errors:
            click.echo(f"  File not found: {not_found_errors}")
        if other_errors:
            click.echo(f"  Other errors: {other_errors}")

    click.echo(f"{'=' * 40}")


# Categories that are safe to delete without losing project context
SAFE_CATEGORIES = ["cache", "logs", "crash_reports", "temp"]


@main.command()
@click.option(
    "--category",
    multiple=True,
    type=click.Choice(VALID_CATEGORIES, case_sensitive=False),
    help="Category to clean (can be specified multiple times).",
)
@click.option("--safe", is_flag=True, help="Only clean safe categories (cache, logs, crash_reports, temp) that don't affect project context.")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without deleting.")
@click.option("--force", is_flag=True, help="Skip confirmation prompts.")
@click.option("--backup", is_flag=True, help="Create backup before cleaning.")
@click.option("--keep-recent", type=int, default=None, help="Override retention period (days).")
@click.option(
    "--kill-kiro", is_flag=True, help="Terminate running Kiro processes before cleaning."
)
@click.option(
    "--filter-content", type=str, default=None, help="Filter chats by content substring."
)
@click.option(
    "--filter-before", type=str, default=None, help="Filter chats before date (YYYY-MM-DD)."
)
@click.option(
    "--filter-after", type=str, default=None, help="Filter chats after date (YYYY-MM-DD)."
)
def clean(
    category, safe, dry_run, force, backup, keep_recent, kill_kiro,
    filter_content, filter_before, filter_after,
):
    """Clean artefacts by category with optional filtering."""
    # Handle --safe flag: override categories with safe-only set
    if safe:
        if category:
            click.echo(
                "[WARN] --safe flag overrides --category selections. "
                f"Cleaning safe categories only: {', '.join(SAFE_CATEGORIES)}",
                err=True,
            )
        category = tuple(SAFE_CATEGORIES)

    # Step 1: Validate inputs
    if keep_recent is not None and keep_recent <= 0:
        click.echo(
            "[ERROR] --keep-recent must be a positive integer (greater than 0).",
            err=True,
        )
        sys.exit(1)

    if filter_before is not None:
        _validate_date(filter_before, "--filter-before")

    if filter_after is not None:
        _validate_date(filter_after, "--filter-after")

    # Step 2: Resolve platform and check kiro_storage exists
    platform_info = resolve_platform()
    kiro_storage = platform_info.kiro_storage

    if not kiro_storage.exists():
        click.echo(
            f"[ERROR] Kiro storage not found at {kiro_storage}. "
            "No Kiro installation detected.",
            err=True,
        )
        sys.exit(1)

    # Step 3: If --kill-kiro, terminate Kiro processes
    if kill_kiro:
        click.echo("Terminating Kiro processes...")
        warnings = kill_kiro_processes()
        for warning in warnings:
            click.echo(f"[WARN] {warning}", err=True)
        if not warnings:
            click.echo("Kiro processes terminated successfully.")

    # Step 4: Scan storage
    scan_result = scan_storage(kiro_storage)

    # Step 5: Determine categories to clean
    selected_categories: list[str] = list(category)

    if not selected_categories:
        # Interactive multi-select
        selected_categories = _interactive_category_select(scan_result)
        if not selected_categories:
            click.echo("No categories selected. Exiting.")
            return

    # Step 6 & 7: Collect files and apply retention filter per category
    files_after_retention: list[Path] = []
    for cat_name in selected_categories:
        cat_result = scan_result.categories.get(cat_name)
        if cat_result:
            eligible = filter_by_retention(
                cat_result.files,
                cat_name,
                keep_recent_days=keep_recent,
            )
            files_after_retention.extend(eligible)

    # Step 8: Apply chat filters if any filter flags are set (only for chats category)
    has_chat_filters = any([filter_content, filter_before, filter_after])
    if has_chat_filters and "chats" in selected_categories:
        # Separate chat files from non-chat files
        chat_files_in_result = []
        non_chat_files = []
        for f in files_after_retention:
            if f.suffix == ".chat":
                chat_files_in_result.append(f)
            else:
                non_chat_files.append(f)

        # Build filter criteria
        criteria = ChatFilterCriteria(
            content=filter_content,
            before=(
                datetime.strptime(filter_before, "%Y-%m-%d").date()
                if filter_before
                else None
            ),
            after=(
                datetime.strptime(filter_after, "%Y-%m-%d").date()
                if filter_after
                else None
            ),
        )

        # Apply chat filter
        filtered_chats = filter_chats(chat_files_in_result, criteria)

        # Recombine: non-chat files + filtered chat files
        files_after_retention = non_chat_files + filtered_chats

    # Step 9: If no files to delete, display message and exit
    if not files_after_retention:
        click.echo("No files eligible for cleaning. Nothing to do.")
        return

    # Step 10: If --backup, create backup before deletion
    if backup:
        app_config = load_config()
        backup_dir = Path(app_config.backup_dir).expanduser()
        click.echo(f"Creating backup of {len(files_after_retention)} files...")
        try:
            backup_result = create_backup(files_after_retention, kiro_storage, backup_dir)
            click.echo(
                f"Backup created: {backup_result.archive_path} "
                f"({backup_result.file_count} files, "
                f"{format_size(backup_result.total_bytes)})"
            )
        except OSError as e:
            click.echo(
                f"[ERROR] Backup creation failed: {e}. Aborting cleaning operation.",
                err=True,
            )
            sys.exit(1)

    # Step 11: If not --force and not --dry-run, display files and prompt for confirmation
    if not force and not dry_run:
        click.echo(f"\nFiles to be deleted ({len(files_after_retention)} files):")
        total_size = 0
        for f in files_after_retention:
            try:
                size = f.stat().st_size
                total_size += size
                click.echo(f"  {f} ({format_size(size)})")
            except OSError:
                click.echo(f"  {f} (size unknown)")

        click.echo(
            f"\nTotal: {len(files_after_retention)} files, {format_size(total_size)}"
        )

        if not click.confirm("Proceed with deletion?"):
            click.echo("Aborted.")
            return

    # Step 12: Call clean_files
    result = clean_files(files_after_retention, dry_run=dry_run)

    # Log protected file skips
    for protected_path in result.skipped_protected:
        click.echo(f"[SKIP] Protected: {protected_path}", err=True)

    # Log errors
    for error in result.errors:
        click.echo(
            f"[ERROR] {error.error_type.value}: {error.path} - {error.message}",
            err=True,
        )

    # Step 13: Display summary
    _display_clean_summary(result, dry_run)


@main.command()
@click.argument("archive_path", type=click.Path(exists=False))
@click.option("--force", is_flag=True, help="Overwrite existing files without prompting.")
def restore(archive_path, force):
    """Restore artefacts from a backup archive."""
    archive = Path(archive_path)

    # Validate archive exists
    if not archive.exists():
        click.echo(
            f"[ERROR] Backup archive not found: {archive_path}",
            err=True,
        )
        sys.exit(1)

    # Validate it's a valid tar.gz
    if not tarfile.is_tarfile(str(archive)):
        click.echo(
            f"[ERROR] Invalid or corrupted archive: {archive_path}",
            err=True,
        )
        sys.exit(1)

    # Resolve platform to get kiro_storage
    platform_info = resolve_platform()
    kiro_storage = platform_info.kiro_storage

    # Perform restore
    try:
        result = restore_backup(archive, kiro_storage, force=force)
    except FileNotFoundError as e:
        click.echo(f"[ERROR] {e}", err=True)
        sys.exit(1)
    except tarfile.ReadError as e:
        click.echo(f"[ERROR] {e}", err=True)
        sys.exit(1)

    # Display restore summary
    click.echo("Restore complete:")
    click.echo(f"  Files restored: {result.restored_count}")
    click.echo(f"  Files skipped:  {result.skipped_count}")
    if result.errors:
        click.echo(f"  Errors:         {len(result.errors)}")
        for error in result.errors:
            click.echo(f"    - {error}")

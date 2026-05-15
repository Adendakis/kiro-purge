# Kiro Cleaner

A cross-platform Python CLI tool that safely cleans up artefacts accumulated by [Kiro IDE](https://kiro.dev) over time. Reclaim disk space by removing cache files, old logs, crash reports, and more — without risking your project context or chat history.

## Quick Start

```bash
# Install
pip install -e .

# See what's using disk space
kiro-cleaner scan

# Preview what a safe clean would delete (nothing gets deleted)
kiro-cleaner clean --safe --dry-run --force

# Run the safe clean 
# deletes only cache, logs, crash reports, temp files
# keeps context (index, chats and file edit history)
kiro-cleaner clean --safe --force
```

## Features

- **Cross-platform** — Works on macOS, Windows, and Linux
- **Safe by default** — Protected files and directories are never deleted
- **Dry-run mode** — Preview what would be deleted before committing
- **Safe clean** — One-flag cleanup of non-essential data that preserves all project context
- **Category-based cleaning** — Target specific artefact types
- **Retention periods** — Only delete files older than configurable thresholds
- **Chat filtering** — Filter conversations by content or date before cleaning
- **Backup/restore** — Create archives before cleaning, restore if needed
- **Fail-safe deletion** — Files are deleted individually with full error reporting

## Installation

Requires Python 3.10+.

```bash
# From source (editable/development mode)
git clone https://github.com/Adendakis/kiro-purge.git
cd kiro-purge
pip install -e .

# With dev dependencies (for running tests)
pip install -e ".[dev]"
```

## Commands

### `kiro-cleaner scan`

Scan Kiro storage and display disk usage by category.

```bash
kiro-cleaner scan
```

Output:
```
Category            Files         Size
---------------- -------- ------------
logs                  947      1.09 GB
cache                 842    248.39 MB
chats               54029     10.15 GB
index               50498      4.08 GB
temp                    0          0 B
history             32835     394.8 MB
crash_reports          14     12.65 MB
Uncategorized       65433     18.73 GB
---------------- -------- ------------
Total              204598     34.68 GB
```

### `kiro-cleaner clean`

Clean artefacts by category with optional filtering.

```bash
# Safe clean — only non-essential categories (cache, logs, crash_reports, temp)
kiro-cleaner clean --safe --force

# Clean specific categories
kiro-cleaner clean --category cache --category logs --force

# Dry-run to preview without deleting
kiro-cleaner clean --category chats --dry-run --force

# Clean with backup
kiro-cleaner clean --safe --backup --force

# Clean old chats (older than 30 days by default)
kiro-cleaner clean --category chats --force

# Override retention period
kiro-cleaner clean --category logs --keep-recent 3 --force

# Filter chats by content before cleaning
kiro-cleaner clean --category chats --filter-content "test" --force

# Filter chats by date
kiro-cleaner clean --category chats --filter-before 2024-01-01 --force
kiro-cleaner clean --category chats --filter-after 2024-06-01 --force

# Interactive mode (prompts for category selection)
kiro-cleaner clean

# Kill Kiro processes before cleaning
kiro-cleaner clean --safe --kill-kiro --force
```

**Options:**

| Flag | Description |
|------|-------------|
| `--safe` | Clean only safe categories (cache, logs, crash_reports, temp) |
| `--category` | Specify category to clean (repeatable) |
| `--dry-run` | Show what would be deleted without deleting |
| `--force` | Skip confirmation prompts |
| `--backup` | Create tar.gz backup before cleaning |
| `--keep-recent N` | Override retention period to N days |
| `--kill-kiro` | Terminate running Kiro processes first |
| `--filter-content TEXT` | Only target chats containing TEXT |
| `--filter-before DATE` | Only target chats before DATE (YYYY-MM-DD) |
| `--filter-after DATE` | Only target chats after DATE (YYYY-MM-DD) |

### `kiro-cleaner restore`

Restore artefacts from a backup archive.

```bash
# Restore (skips files that already exist)
kiro-cleaner restore ~/.kiro-cleaner/backups/kiro-backup-2024-01-15T143022.tar.gz

# Restore with overwrite
kiro-cleaner restore path/to/backup.tar.gz --force
```

### `kiro-cleaner config`

View or update configuration settings.

```bash
# Show all settings
kiro-cleaner config

# Show a specific setting
kiro-cleaner config backup_dir

# Update a setting
kiro-cleaner config skip_confirm true
kiro-cleaner config keep_recent 14
kiro-cleaner config backup_dir /custom/path/
```

**Configuration keys:**

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `keep_logs` | bool | false | Preserve log files during cleaning |
| `keep_cache` | bool | false | Preserve cache files during cleaning |
| `keep_chats` | bool | false | Preserve chat files during cleaning |
| `keep_index` | bool | false | Preserve index files during cleaning |
| `keep_recent` | int | 0 | Default retention override (days) |
| `skip_confirm` | bool | false | Skip confirmation prompts |
| `backup_dir` | string | ~/.kiro-cleaner/backups/ | Backup archive directory |

## Categories

| Category | What it contains | Safe to delete? |
|----------|-----------------|-----------------|
| `cache` | Chromium browser cache (Cache/, CachedData/, GPUCache/) | ✅ Yes — rebuilt automatically |
| `logs` | Application log files (logs/) | ✅ Yes — diagnostic only |
| `crash_reports` | Crashpad dump files (Crashpad/) | ✅ Yes — for debugging Kiro itself |
| `temp` | Temporary files (*.tmp, *.temp) | ✅ Yes — transient data |
| `history` | File edit history (User/History/) | ⚠️ Caution — local undo snapshots |
| `chats` | Conversation history (*.chat files) | ❌ No — your project context |
| `index` | Code intelligence index (protected) | 🔒 Protected — never deleted |

## Protected Files & Directories

The following are **never deleted** regardless of flags or categories:

**Protected files:** `config.json`, `settings.json`, `mcp.json`, `sessions.json`, `state.vscdb`, `workspace.json`, `storage.json`

**Protected directories:** `index/`, `.migrations/`, `lancedb/`

## Retention Periods

Files are only deleted if they're older than the retention threshold:

| Category | Default retention |
|----------|------------------|
| logs | 7 days |
| crash_reports | 30 days |
| history | 30 days |
| chats | 30 days |
| cache | Always eligible |
| temp | Always eligible |

Use `--keep-recent N` to override the threshold for a specific operation.

## Kiro Storage Locations

| Platform | Path |
|----------|------|
| macOS | `~/Library/Application Support/kiro/` |
| Windows | `%APPDATA%\kiro\` |
| Linux | `~/.config/kiro/` |

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run only property-based tests
pytest -m property

# Run with verbose output
pytest -v
```

## License

MIT

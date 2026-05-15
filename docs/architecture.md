# Architecture

## Overview

Kiro Cleaner follows a layered architecture with clear separation between the CLI interface, business logic, and file system operations.

```
┌─────────────────────────────────────────────────┐
│              CLI Layer (cli.py)                  │
│  Click commands, argument parsing, user prompts │
├─────────────────────────────────────────────────┤
│            Service / Business Logic             │
│  Orchestration, retention rules, chat filters   │
├────────┬──────────┬──────────┬──────────────────┤
│Scanner │ Cleaner  │  Backup  │   Chat Parser    │
│        │          │  Manager │   & Filter       │
├────────┴──────────┴──────────┴──────────────────┤
│           Platform Layer (platform.py)          │
│  OS detection, path resolution, process mgmt   │
├─────────────────────────────────────────────────┤
│         Protection Guard (protection.py)        │
│  Protected file/directory enforcement           │
└─────────────────────────────────────────────────┘
```

## Module Responsibilities

### `cli.py` — CLI Layer
- Click command group with `scan`, `clean`, `restore`, `config` subcommands
- Argument validation and error display
- Interactive category selection
- Output formatting (tables, summaries)
- Exit code management

### `platform.py` — Platform Layer
- OS detection via `sys.platform`
- Kiro storage path resolution (macOS/Windows/Linux)
- Process discovery and termination (`kill_kiro_processes`)
- Graceful → force kill escalation with timeout

### `scanner.py` — Storage Scanner
- Recursive directory traversal using `os.scandir`
- File classification into exactly one category
- Size calculation and aggregation
- Permission error handling (warns and continues)

### `cleaner.py` — Deletion Engine
- Individual file deletion (no `shutil.rmtree`)
- Protection enforcement before each deletion
- Existence verification (race condition safety)
- Error classification: PERMISSION, NOT_FOUND, OTHER
- Dry-run mode (report without deleting)

### `retention.py` — Retention Filter
- Time-based filtering using file modification time
- Per-category default thresholds
- `--keep-recent` override support
- Always-eligible categories (cache, temp, index)

### `chat_parser.py` — Chat File Parser
- JSON parsing with structural validation
- Role validation (human, bot, tool)
- Metadata extraction (timestamps, model info)
- Round-trip preservation via `raw_data`

### `chat_filter.py` — Chat Filter
- Content substring matching (case-insensitive)
- Date-based filtering (before/after boundaries)
- Conjunction semantics (all filters must match)
- Graceful handling of files without timestamps

### `backup.py` — Backup Manager
- tar.gz archive creation with relative paths
- Timestamped filenames (`kiro-backup-YYYY-MM-DDTHHMMSS.tar.gz`)
- Restore with conflict detection
- Force overwrite option

### `config_manager.py` — Configuration
- JSON-based persistent configuration
- Type-validated updates (bool, int, str)
- Atomic writes (temp file + rename)
- Default creation on first use

### `protection.py` — Protection Guard
- Hardcoded protected file list (7 files)
- Hardcoded protected directory list (3 directories)
- Path component matching for nested protection
- Returns reason string for skip logging

## Data Flow: Clean Operation

```
1. Validate CLI inputs (dates, keep-recent)
2. Resolve platform → get kiro_storage path
3. [Optional] Kill Kiro processes
4. Scan storage → categorize all files
5. Select categories (from flags or interactive)
6. Apply retention filter per category
7. [Optional] Apply chat content/date filters
8. Check if any files remain
9. [Optional] Create backup archive
10. [Optional] Prompt for confirmation
11. Delete files individually:
    a. Check protection → skip if protected
    b. Check existence → skip if gone
    c. Get size → for reporting
    d. Unlink file → classify any errors
12. Display summary (deleted, skipped, errors)
```

## Error Handling Strategy

| Scenario | Behavior |
|----------|----------|
| Invalid CLI input | Fail fast, exit code 1 or 2 |
| Missing Kiro storage | Fail fast, exit code 1 |
| File deletion failure | Log, skip, continue |
| Permission error (scan) | Warn, continue scanning |
| Backup failure | Abort entire clean operation |
| Config write failure | Preserve previous config |
| Chat parse error | Skip file, continue |

## Dependencies

- **click** — CLI framework (commands, options, prompts)
- **pytest** — Test framework (dev only)
- **hypothesis** — Property-based testing (dev only)
- **Python stdlib** — pathlib, os, json, tarfile, subprocess, signal, datetime

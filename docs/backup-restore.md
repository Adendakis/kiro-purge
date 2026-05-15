# Backup & Restore

## Overview

Kiro Cleaner can create compressed archives of files before deleting them, and restore those archives later if needed. This provides a safety net for cleaning operations.

## Creating Backups

Add `--backup` to any clean command to create an archive before deletion:

```bash
# Safe clean with backup
kiro-cleaner clean --safe --backup --force

# Clean specific category with backup
kiro-cleaner clean --category chats --backup --force

# Dry-run does NOT create backups (nothing to back up)
kiro-cleaner clean --safe --backup --dry-run --force  # No backup created
```

### Backup Location

Archives are stored in the configured backup directory:
- Default: `~/.kiro-cleaner/backups/`
- Configurable: `kiro-cleaner config backup_dir /custom/path/`

### Backup Filename Format

```
kiro-backup-YYYY-MM-DDTHHMMSS.tar.gz
```

Example: `kiro-backup-2024-01-15T143022.tar.gz`

### Archive Contents

The archive preserves relative paths from the Kiro storage root:

```
kiro-backup-2024-01-15T143022.tar.gz
├── logs/
│   ├── 2024-01-10.log
│   └── 2024-01-11.log
├── Cache/
│   ├── data_0
│   └── data_1
└── Crashpad/
    └── crash_2024-01-10.dmp
```

### Backup Failure Handling

If backup creation fails (disk full, permission error, etc.), the **entire clean operation is aborted**. No files are deleted. This ensures you never lose data without a successful backup.

## Restoring from Backup

```bash
# Restore (skips files that already exist at target location)
kiro-cleaner restore ~/.kiro-cleaner/backups/kiro-backup-2024-01-15T143022.tar.gz

# Restore with overwrite (replaces existing files)
kiro-cleaner restore path/to/backup.tar.gz --force
```

### Conflict Handling

When restoring, if a file already exists at the target location:

- **Without `--force`**: The file is skipped (not overwritten)
- **With `--force`**: The existing file is overwritten with the backup version

### Restore Summary

After restoration, a summary is displayed:

```
Restore complete:
  Files restored: 42
  Files skipped:  3
  Errors:         0
```

### Error Handling

| Scenario | Behavior |
|----------|----------|
| Archive doesn't exist | Error message, exit code 1 |
| Invalid/corrupted archive | Error message, exit code 1 |
| Permission error during extraction | Skip file, log error, continue |
| Missing parent directory | Created automatically |

## Workflow Example

```bash
# 1. Check what's using space
kiro-cleaner scan

# 2. Clean with backup (safety net)
kiro-cleaner clean --category logs --category cache --backup --force

# 3. Realize you needed something from logs
kiro-cleaner restore ~/.kiro-cleaner/backups/kiro-backup-2024-01-15T143022.tar.gz --force

# 4. Files are back in their original locations
```

## Managing Backups

Backup archives accumulate over time. You can manage them manually:

```bash
# List backups
ls ~/.kiro-cleaner/backups/

# Check backup sizes
du -sh ~/.kiro-cleaner/backups/*

# Remove old backups manually
rm ~/.kiro-cleaner/backups/kiro-backup-2024-01-*.tar.gz
```

The tool does not automatically clean up old backups — this is intentional to avoid accidentally removing your safety net.

# Safety & Protection

## Design Philosophy

Kiro Cleaner is designed with a "fail-safe" approach. The tool prioritizes data safety over convenience:

1. **Protected files are never deleted** — regardless of flags or categories
2. **Individual file deletion** — no `rm -rf` style directory removal
3. **Errors don't stop the operation** — failed deletions are logged and skipped
4. **Dry-run by default** — use `--dry-run` to preview any operation
5. **Confirmation required** — unless `--force` is explicitly provided
6. **Backup before delete** — `--backup` creates an archive first

## Protected Files

These files are **never deleted**, even with `--force`:

| File | Purpose |
|------|---------|
| `config.json` | Kiro configuration |
| `settings.json` | User settings |
| `mcp.json` | MCP server configuration |
| `sessions.json` | Active session data |
| `state.vscdb` | Workbench state database |
| `workspace.json` | Workspace configuration |
| `storage.json` | Storage metadata |

Protection is based on **filename matching** — any file with these names, regardless of which directory it's in, is protected.

## Protected Directories

All files within these directories are **never deleted**:

| Directory | Purpose |
|-----------|---------|
| `index/` | Code intelligence vector index |
| `.migrations/` | Database migration state |
| `lancedb/` | Vector database storage |

Protection is based on **path component matching** — if any part of a file's path matches a protected directory name, the file is skipped.

## How Protection Works

Before every single file deletion, the cleaner checks:

1. Does the filename match any protected file? → Skip
2. Does any path component match a protected directory? → Skip
3. Does the file still exist? → Skip if gone (race condition safety)

Protected files that are encountered during cleaning are logged:
```
[SKIP] Protected: /path/to/config.json
```

## Safe Clean Mode

The `--safe` flag restricts cleaning to categories that have **zero impact** on project context:

```bash
kiro-cleaner clean --safe --force
```

Safe categories: `cache`, `logs`, `crash_reports`, `temp`

This will never touch:
- Chat history (your conversations with Kiro)
- File history (local undo snapshots)
- Index data (code intelligence)
- Configuration files

## Dry-Run Mode

Always preview before committing:

```bash
# See exactly what would be deleted
kiro-cleaner clean --safe --dry-run --force
```

In dry-run mode:
- No files are deleted
- No directories are removed
- No backups are created
- The full list of targeted files is displayed
- A summary shows count and total size

## Error Handling

| Error Type | Behavior |
|------------|----------|
| Permission denied | Skip file, log error, continue |
| File not found | Skip file, log error, continue |
| Other OS error | Skip file, log error, continue |
| Backup failure | **Abort entire operation** — no files deleted |

After completion, a summary shows:
```
========================================
Cleaning Summary
========================================
Deleted: 847 files (1.09 GB)
Protected (skipped): 3 files

Errors (2 total):
  Permission errors: 2
========================================
```

## Process Termination Safety

When using `--kill-kiro`:

1. **SIGTERM first** (graceful shutdown request)
2. **Wait up to 10 seconds** for process to exit
3. **SIGKILL only if needed** (force kill after timeout)
4. **Warning if kill fails** — cleaning continues anyway

On Windows: `taskkill` → wait → `taskkill /F`

## Recommendations

1. **First time?** Run `kiro-cleaner scan` to understand your storage
2. **Start safe:** Use `kiro-cleaner clean --safe --dry-run --force` to preview
3. **Use backups:** Add `--backup` when cleaning chats or history
4. **Trust retention:** Default retention periods protect recent files
5. **Check git first:** Ensure your code is committed before cleaning history

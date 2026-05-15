# Configuration

## Overview

Kiro Cleaner stores its configuration in a JSON file at `~/.kiro-cleaner/config.json`. The configuration file is created with default values on first use.

## Viewing Configuration

```bash
# Show all settings
kiro-cleaner config

# Output:
# backup_dir = ~/.kiro-cleaner/backups/
# keep_cache = False
# keep_chats = False
# keep_index = False
# keep_logs = False
# keep_recent = 0
# skip_confirm = False

# Show a specific setting
kiro-cleaner config backup_dir
# Output: backup_dir = ~/.kiro-cleaner/backups/
```

## Updating Configuration

```bash
# Set a boolean value
kiro-cleaner config skip_confirm true
kiro-cleaner config keep_logs false

# Set an integer value
kiro-cleaner config keep_recent 14

# Set a string value
kiro-cleaner config backup_dir /my/custom/backups/
```

## Configuration Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `keep_logs` | bool | `false` | If true, preserve log files during cleaning |
| `keep_cache` | bool | `false` | If true, preserve cache files during cleaning |
| `keep_chats` | bool | `false` | If true, preserve chat files during cleaning |
| `keep_index` | bool | `false` | If true, preserve index files during cleaning |
| `keep_recent` | int | `0` | Default retention override in days (0 = use category defaults) |
| `skip_confirm` | bool | `false` | If true, skip confirmation prompts (like --force) |
| `backup_dir` | string | `~/.kiro-cleaner/backups/` | Directory for backup archives |

## Type Validation

The config command validates types before saving:

- **Boolean fields** accept: `true`, `false`, `True`, `False`, `TRUE`, `FALSE`
- **Integer fields** accept: any valid integer string (e.g., `7`, `30`, `0`)
- **String fields** accept: any string value

Invalid values are rejected with an error message:

```bash
kiro-cleaner config keep_logs yes
# Error: Invalid value for 'keep_logs': expected 'true' or 'false', got 'yes'

kiro-cleaner config keep_recent abc
# Error: Invalid value for 'keep_recent': expected an integer, got 'abc'

kiro-cleaner config nonexistent_key value
# Error: Unrecognized configuration key: 'nonexistent_key'. Valid keys are: ...
```

## File Location

The configuration file is stored at:
```
~/.kiro-cleaner/config.json
```

The directory is created automatically if it doesn't exist.

## File Format

```json
{
  "keep_logs": false,
  "keep_cache": false,
  "keep_chats": false,
  "keep_index": false,
  "keep_recent": 0,
  "skip_confirm": false,
  "backup_dir": "~/.kiro-cleaner/backups/"
}
```

## Error Recovery

- If the config file contains invalid JSON, defaults are used
- If the config file is missing, defaults are used and the file is created on first write
- Writes use atomic operations (temp file + rename) to prevent corruption
- If a write fails, the previous configuration is preserved

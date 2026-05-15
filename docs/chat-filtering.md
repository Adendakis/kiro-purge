# Chat Filtering

## Overview

Kiro Cleaner provides fine-grained filtering for chat history files, allowing you to selectively clean conversations based on content and date criteria. This is useful when you want to remove specific conversations without wiping your entire chat history.

## Chat File Format

Chat files are JSON files with the `.chat` extension stored at:
```
User/globalStorage/kiro.kiroagent/*.chat
```

Structure:
```json
{
  "chat": [
    {"role": "human", "content": "message text"},
    {"role": "bot", "content": "response text"},
    {"role": "tool", "content": "tool output"}
  ],
  "metadata": {
    "modelId": "claude-3",
    "modelProvider": "anthropic",
    "workflow": "chat",
    "startTime": 1700000000000,
    "endTime": 1700000060000
  }
}
```

- `role` must be one of: `human`, `bot`, `tool`
- `startTime` and `endTime` are epoch milliseconds (optional)
- Additional fields are preserved during parsing

## Filter Options

### Content Filter (`--filter-content`)

Matches chat files where **any message** contains the search term as a case-insensitive substring.

```bash
# Delete chats mentioning "test" (older than 30 days)
kiro-cleaner clean --category chats --filter-content "test" --force

# Preview chats mentioning "debug"
kiro-cleaner clean --category chats --filter-content "debug" --dry-run --force
```

The match is performed on the `content` field of every message in the chat. If any single message contains the substring, the entire chat file is targeted.

### Before Filter (`--filter-before`)

Matches chat files with a `startTime` strictly earlier than midnight UTC of the specified date.

```bash
# Delete chats from before January 2024
kiro-cleaner clean --category chats --filter-before 2024-01-01 --force
```

- Date format: `YYYY-MM-DD`
- Comparison: `startTime < midnight UTC of the date`
- Files without `startTime` are **excluded** (not matched)

### After Filter (`--filter-after`)

Matches chat files with a `startTime` strictly later than 23:59:59 UTC of the specified date.

```bash
# Delete chats from after June 2024
kiro-cleaner clean --category chats --filter-after 2024-06-30 --force
```

- Date format: `YYYY-MM-DD`
- Comparison: `startTime > 23:59:59 UTC of the date`
- Files without `startTime` are **excluded** (not matched)

### Combining Filters (Conjunction)

When multiple filters are specified, **all must match** for a file to be targeted. This is a logical AND (conjunction).

```bash
# Delete chats mentioning "experiment" from before March 2024
kiro-cleaner clean --category chats \
  --filter-content "experiment" \
  --filter-before 2024-03-01 \
  --force

# Delete chats about "refactor" within a specific date range
kiro-cleaner clean --category chats \
  --filter-content "refactor" \
  --filter-after 2024-01-01 \
  --filter-before 2024-06-01 \
  --force
```

## Interaction with Retention

Chat filters are applied **after** the retention filter. The flow is:

1. Retention filter removes chats newer than 30 days (or `--keep-recent N` days)
2. Chat filters further narrow the remaining eligible chats
3. Only chats matching both retention AND all active filters are targeted

This means you cannot accidentally delete recent chats even with aggressive content filters — the retention period still protects them unless overridden.

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Chat file with malformed JSON | Skipped (not matched, not deleted) |
| Chat file missing `startTime` | Excluded from date filters, still eligible for content filter |
| Chat file with invalid roles | Skipped (parse error) |
| Empty search term (`""`) | Matches all files (empty string is substring of everything) |
| No chats match filters | "No files eligible for cleaning" message, nothing deleted |
| Filters without `--category chats` | Filters are ignored (only apply to chats category) |

## Examples

```bash
# Find how many chats mention a topic (dry-run)
kiro-cleaner clean --category chats --filter-content "kubernetes" --dry-run --force

# Clean old debugging conversations
kiro-cleaner clean --category chats \
  --filter-content "debug" \
  --filter-before 2024-01-01 \
  --backup --force

# Remove all chats from a specific time period
kiro-cleaner clean --category chats \
  --filter-after 2024-03-01 \
  --filter-before 2024-04-01 \
  --force
```

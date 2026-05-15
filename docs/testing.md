# Testing

## Overview

Kiro Cleaner uses a comprehensive testing strategy combining:

- **Unit tests** — Example-based tests for specific behaviors
- **Property-based tests** — Hypothesis-powered tests that verify universal correctness properties
- **Integration tests** — End-to-end CLI workflow tests using Click's CliRunner

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run only property-based tests
pytest -m property

# Run a specific test file
pytest tests/test_scanner.py

# Run with Hypothesis statistics
pytest --hypothesis-show-statistics

# Run with coverage
pytest --cov=kiro_cleaner --cov-report=html
```

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures (temp dirs, mock storage)
├── test_platform.py         # Platform detection and process management
├── test_protection.py       # Protection guard (unit + Property 2)
├── test_config.py           # Config manager (unit + Property 10)
├── test_scanner.py          # Scanner (unit + Properties 4, 5, 6)
├── test_retention.py        # Retention filter (unit + Property 3)
├── test_cleaner.py          # Cleaner engine (Properties 7, 8, 14)
├── test_chat_parser.py      # Chat parser (unit + Properties 1, 15)
├── test_chat_filter.py      # Chat filter (unit + Properties 11, 12, 13)
├── test_backup.py           # Backup manager (Property 9)
└── test_cli.py              # CLI integration tests
```

## Correctness Properties

The tool validates 15 formal correctness properties using Hypothesis:

| # | Property | Validates |
|---|----------|-----------|
| 1 | Chat parse/print round-trip | Parsing → printing → re-parsing yields equal objects |
| 2 | Protection invariant | Protected files are never deletable |
| 3 | Retention filter correctness | Files eligible iff older than threshold |
| 4 | Scan categorization correctness | Each file classified into exactly one category |
| 5 | Scan total invariant | Category counts sum to total |
| 6 | Size formatting correctness | Largest unit used, reversible within rounding |
| 7 | Dry-run no-deletion invariant | Dry-run never modifies filesystem |
| 8 | Category-based cleaning correctness | Only selected category files targeted |
| 9 | Backup/restore round-trip | Backup → restore reproduces original files |
| 10 | Config set/get round-trip | Set value → load → same value |
| 11 | Chat content filter correctness | Included iff message contains term |
| 12 | Chat date filter correctness | Before/after boundaries respected |
| 13 | Chat filter conjunction | Combined = intersection of individual filters |
| 14 | Error classification correctness | Exception type → error type mapping is deterministic |
| 15 | Chat structural validation | Invalid structures produce ParseError |

Each property test runs 100 examples with randomized inputs.

## Shared Fixtures

Key fixtures in `conftest.py`:

- `mock_kiro_storage` — Full realistic storage tree with files in all categories
- `mock_chat_file` — Single valid chat file
- `mock_config_dir` — Temp config directory
- `empty_kiro_storage` — Empty storage directory
- `mock_protected_storage` — Storage with only protected files/directories

## Integration Tests

CLI integration tests use Click's `CliRunner` with mocked `resolve_platform()` to avoid touching real Kiro storage:

- Scan → verify output format
- Clean → verify files deleted/preserved
- Backup → restore → verify round-trip
- Chat filter → clean → verify selective deletion
- Config → set/get round-trip
- Error cases → verify exit codes and messages

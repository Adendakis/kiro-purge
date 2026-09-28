#!/usr/bin/env bash
#
# install.sh — Install Kiro Cleaner from source (non-editable).
#
# This performs a regular install (a copy into site-packages), unlike
# `pip install -e .` which links back to the source tree. Use this when you
# want a self-contained install that does not depend on this checkout staying
# in place.
#
# Usage:
#   ./install.sh              # build a wheel and install it (with dev extras off)
#   ./install.sh --dev        # include dev dependencies (pytest, hypothesis)
#   ./install.sh --user       # install into the user site (pip --user)
#   ./install.sh --uninstall  # uninstall kiro-cleaner
#
# Options may be combined, e.g. `./install.sh --dev --user`.

set -euo pipefail

# Resolve the directory this script lives in so it works from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PACKAGE_NAME="kiro-cleaner"
INSTALL_EXTRAS=""
PIP_USER_FLAG=""
DO_UNINSTALL=0

for arg in "$@"; do
    case "$arg" in
        --dev)       INSTALL_EXTRAS="[dev]" ;;
        --user)      PIP_USER_FLAG="--user" ;;
        --uninstall) DO_UNINSTALL=1 ;;
        -h|--help)
            sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown option: $arg" >&2
            echo "Run './install.sh --help' for usage." >&2
            exit 2
            ;;
    esac
done

# Pick a Python interpreter (prefer python3).
if command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
else
    echo "Error: no 'python3' or 'python' interpreter found on PATH." >&2
    exit 1
fi

if [ "$DO_UNINSTALL" -eq 1 ]; then
    echo "Uninstalling $PACKAGE_NAME ..."
    "$PYTHON" -m pip uninstall -y "$PACKAGE_NAME"
    echo "Done."
    exit 0
fi

echo "Using interpreter: $($PYTHON --version 2>&1) ($PYTHON)"

# Ensure the modern build frontend is available, then build sdist + wheel.
echo "Ensuring 'build' is available ..."
"$PYTHON" -m pip install --quiet --upgrade build

echo "Building distribution artifacts into ./dist ..."
rm -rf dist
"$PYTHON" -m build

# Install the freshly built wheel (non-editable).
WHEEL="$(ls -t dist/*.whl 2>/dev/null | head -n 1 || true)"
if [ -z "$WHEEL" ]; then
    echo "Error: no wheel was produced in ./dist." >&2
    exit 1
fi

echo "Installing $WHEEL${INSTALL_EXTRAS} ..."
# `--force-reinstall` so re-running picks up local changes; the target is the
# built wheel path plus any extras (dev) requested.
"$PYTHON" -m pip install $PIP_USER_FLAG --force-reinstall "${WHEEL}${INSTALL_EXTRAS}"

echo
echo "Installed $PACKAGE_NAME. Verify with:"
echo "    kiro-cleaner --version"
echo "    kiro-cleaner scan --help"

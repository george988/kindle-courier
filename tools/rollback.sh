#!/usr/bin/env bash
# rollback.sh: re-activate the version recorded in $KINDLE_BASE/releases/previous (same atomic flip and lock).
set -euo pipefail
BASE="${KINDLE_BASE:-/workspace/kindle}"; R="$BASE/releases"
[ -f "$R/previous" ] || { echo "no previous release recorded" >&2; exit 2; }
P=$(cat "$R/previous"); [ -d "$R/$P/tools" ] || { echo "previous release $P is not staged" >&2; exit 2; }
exec bash "$R/activate.sh" "$P"

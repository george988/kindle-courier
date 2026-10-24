#!/usr/bin/env bash
# activate.sh VERSION: point $KINDLE_BASE/releases/current at VERSION with one atomic rename, under an exclusive
# $KINDLE_BASE/.release.lock (running tools hold it shared, so activation waits for them). Then make each Kindle
# Courier file in tools/ (listed in the release's tools/COURIER_FILES) a symlink into releases/current/tools.
# Unrelated files in tools/ (send_newspaper_check.sh, lib/, anything else) are never touched. Previous version is
# recorded in releases/previous for rollback.sh.
set -euo pipefail
V="$1"; BASE="${KINDLE_BASE:-/workspace/kindle}"; R="$BASE/releases"; TD="$BASE/tools"
[ -d "$R/$V/tools" ] || { echo "release $V is not staged under $R" >&2; exit 2; }
exec 9>"$BASE/.release.lock"; flock -w 600 9 || { echo "release lock busy" >&2; exit 1; }
(cd "$R/$V" && sha256sum -c --quiet SHA256SUMS) || { echo "release $V fails its SHA256SUMS" >&2; exit 3; }
ts=$(date +%Y%m%d-%H%M%S); cur=$(readlink "$R/current" 2>/dev/null || true)
if [ "$cur" != "$V" ]; then
  [ -n "$cur" ] && { echo "$cur" > "$R/.previous.new"; mv -T "$R/.previous.new" "$R/previous"; }
  ln -sfn "$V" "$R/.current.new" && mv -T "$R/.current.new" "$R/current"
fi
mkdir -p "$TD"
want=$(cat "$R/$V/tools/COURIER_FILES")
for f in $want; do
  tgt="../releases/current/tools/$f"
  if [ -e "$TD/$f" ] && [ ! -L "$TD/$f" ]; then mkdir -p "$BASE/backups/preactivate-$ts"; mv "$TD/$f" "$BASE/backups/preactivate-$ts/$f"; fi
  ln -sfn "$tgt" "$TD/.$f.new" && mv -T "$TD/.$f.new" "$TD/$f"
done
for l in "$TD"/*; do  # drop links into releases/current that the active release no longer provides
  [ -L "$l" ] || continue; case "$(readlink "$l")" in ../releases/current/tools/*) ;; *) continue;; esac
  echo "$want" | grep -qx "$(basename "$l")" || rm -f "$l"
done
if [ -f "$TD/SKILL-kindle-epub-build.md" ] && [ ! -L "$TD/SKILL-kindle-epub-build.md" ]; then
  mkdir -p "$BASE/backups/preactivate-$ts"; mv "$TD/SKILL-kindle-epub-build.md" "$BASE/backups/preactivate-$ts/"; fi
echo "$(date -Iseconds) activate $V (previous ${cur:-none})" >> "$R/activation.log"
echo "active: $V (previous: ${cur:-none})"

#!/usr/bin/env bash
# stage_release.sh SRC_DIR VERSION: copy a verified release folder (with tools/ and SHA256SUMS) into
# $KINDLE_BASE/releases/VERSION, make it read-only, and install activate.sh/rollback.sh into releases/. Does NOT activate.
set -euo pipefail
SRC="$1"; V="$2"; BASE="${KINDLE_BASE:-/workspace/kindle}"; R="$BASE/releases"
[ -d "$BASE" ] || { echo "KINDLE_BASE $BASE does not exist" >&2; exit 2; }
[[ "$V" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9]+)?$ ]] || { echo "bad version $V" >&2; exit 2; }
mkdir -p "$R"; exec 9>"$BASE/.release.lock"; flock -w 600 9
(cd "$SRC" && sha256sum -c --quiet SHA256SUMS) || { echo "source does not match its SHA256SUMS" >&2; exit 3; }
if [ -e "$R/$V" ]; then
  (cd "$R/$V" && sha256sum -c --quiet SHA256SUMS) && cmp -s "$SRC/SHA256SUMS" "$R/$V/SHA256SUMS" && { echo "already staged: $R/$V"; exit 0; }
  echo "$R/$V exists with different content; releases are immutable" >&2; exit 3
fi
T=$(mktemp -d "$R/.stage-XXXX"); mkdir -p "$T/tools"
while read -r sum path; do path="${path#\*}"; mkdir -p "$T/$(dirname "$path")"; cp -p "$SRC/$path" "$T/$path"; done < "$SRC/SHA256SUMS"
cp -p "$SRC/SHA256SUMS" "$T/SHA256SUMS"
(cd "$T" && sha256sum -c --quiet SHA256SUMS)
chmod -R a-w "$T"; chmod u+w "$T"; mv -T "$T" "$R/$V"; chmod a-w "$R/$V"
for s in activate.sh rollback.sh; do [ -f "$R/$V/tools/$s" ] && { cp "$R/$V/tools/$s" "$R/.$s.new"; chmod 755 "$R/.$s.new"; mv -T "$R/.$s.new" "$R/$s"; }; done
echo "staged $R/$V"

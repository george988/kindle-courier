#!/usr/bin/env bash
# make_baseline.sh BACKUP_TOOLS_TAR VERSION OUTDIR: package the pre-2.0 Kindle Courier tools from a backup tarball
# as a release folder (tools/ + COURIER_FILES + SHA256SUMS) so rollback.sh has a target. Unrelated files are skipped.
set -euo pipefail
TAR="$1"; V="$2"; OUT="$3"; T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
tar -xzf "$TAR" -C "$T" tools/article2epub.py tools/video2epub.py tools/ensure_tools.sh tools/epubcheck
mkdir -p "$OUT/tools"; cp -p "$T"/tools/{article2epub.py,video2epub.py,ensure_tools.sh,epubcheck} "$OUT/tools/"
printf '%s\n' article2epub.py video2epub.py ensure_tools.sh epubcheck > "$OUT/tools/COURIER_FILES"
echo "$V" > "$OUT/VERSION"
(cd "$OUT" && find . -type f ! -name SHA256SUMS | sed 's|^\./||' | sort | xargs sha256sum > SHA256SUMS)
echo "baseline $V at $OUT"

#!/usr/bin/env bash
# rebuild_from_skills.sh OUTDIR SKILL.md [SKILL.md ...]: portable reconstruction after a box reset. Extracts every
# "### file: tools/NAME" code block from the given skills into OUTDIR/tools, writes OUTDIR/SHA256SUMS from the embedded
# "### file: SHA256SUMS" block, and verifies the files against it. Then: stage_release.sh OUTDIR VERSION, activate.sh.
set -euo pipefail
OUT="$1"; shift; mkdir -p "$OUT/tools"
python3 - "$OUT" "$@" <<'PY'
import os, re, sys
out = sys.argv[1]; n = 0; F = '`' * 4
for sk in sys.argv[2:]:
    lines = open(sk, encoding='utf-8').read().split('\n'); i = 0
    while i < len(lines):
        m = re.match(r'^### file: ((?:tools/)?[\w.-]+)$', lines[i])
        if m and i + 1 < len(lines) and lines[i + 1].startswith(F):
            j = i + 2; body = []
            while lines[j] != F: body.append(lines[j]); j += 1
            p = os.path.join(out, m.group(1)); os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'w', encoding='utf-8', newline='\n').write('\n'.join(body) + '\n'); n += 1; i = j
        i += 1
print(f'extracted {n} files')
PY
for f in "$OUT"/tools/*.sh "$OUT"/tools/*.py "$OUT"/tools/epubcheck; do chmod +x "$f"; done
(cd "$OUT" && sha256sum -c --quiet SHA256SUMS) && echo "verified against SHA256SUMS"

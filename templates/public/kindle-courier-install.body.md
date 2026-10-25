# Kindle Courier 2.0.1: install the verified release

Installs the verified Kindle Courier 2.0.1 release (tools/VERSION `2.0.1`) from the public repo
george988/kindle-courier, pinned to one commit. It downloads exactly 24 files (20 tools, SHA256SUMS, 3 reviewed skills),
checks each against the sha256 written below, and runs nothing until all 24 verify. Then it runs the reviewed
first-run block (kindle-epub-build section 0 part 1) from the downloaded skill: rebuild and verify the tools, stage, activate, ensure_tools.
Run it before first use, after a box reset, or when `$B/tools/presend_gate.py` is missing. Rerunning is safe: a staged
2.0.1 that verifies is never restaged. It never writes recipients or the ledger (kindle-courier-getting-started does, with the owner's addresses).
Any line starting with REFUSED means stop and tell the owner. Never edit the pins or skip a check.

<!-- kc:install -->
```bash
set -euo pipefail
KC_COMMIT=f1baf0f3cd149ce5cb20da61ebe1442254ee1fc5
KC_URL="https://raw.githubusercontent.com/george988/kindle-courier/$KC_COMMIT"
B="${KINDLE_BASE:-/workspace/kindle}"; export KINDLE_BASE="$B"
die(){ echo "REFUSED (Kindle Courier install): $*" >&2; exit 3; }
[[ "$KC_COMMIT" =~ ^[0-9a-f]{40}$ ]] && [[ "$KC_COMMIT" != 0000000000000000000000000000000000000000 ]] || die "bad commit pin $KC_COMMIT"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT; mkdir "$W/src"
cat > "$W/pins" <<'PINS'
b55b652ca3bc36e5d5e3da16b2b6dc211882b668f9d31ff86c61a5591e4778d0  tools/COURIER_FILES
fe840f52fb5578d3f77eb497115eb02c6036601c3a53e60df7995c7276baa77a  tools/VERSION
62c52b9b6df4d5d954682a23165e44b545b9443ad6a46a20e66f85286ae413f9  tools/activate.sh
121c37e15fcb80691b431b4eda54772bc98d25fb8a2549129d205a7242911fd5  tools/article2epub.py
e30eab6f583b65f7379d10ec180ad79f4ba1797fb2582c157579b1e2c31d6c58  tools/courier_common.py
d53bdc27e28cef4f9acb0939f6481a0e97db6662033309854adb2f1c1473fefa  tools/deps.lock
51af24dd583454bcbf5038150502b2a46051f7ca6255bc557df72eb9c88a4f00  tools/ensure_tools.sh
26c230135601b34defe47f722076c422d2df85328acbd5a63ae155714d64c310  tools/epubcheck
9c53ac23be436abd0e852812371b443078f7ff3d3d284a4bcee3bdb93112e65e  tools/make_baseline.sh
46180193abbd6c357a9e246a8a52b413d5dd56570673e0be64f630149f3bd661  tools/presend_gate.py
94fceaf8c47cbc2429de9019b2a903390f2626f7d356418410c298f412e3cfa7  tools/rebuild_from_skills.sh
18b6f36c30986a2c9398d0c82eb815d88f119f6afad7b0d98049ba14fb60e40f  tools/requirements-video.in
76919291c1490863d7296cc9678e1d6da7d5409cea613fe87b7bceb80d304ede  tools/requirements-video.lock
9256b91944bacd399c489c4d1b5d3b29f65b1a818f9d7761b4edc7d6da1c52b1  tools/requirements.in
3674f30b639d35a25b0d32218b6dac256bcb6151bf775273fc20e64240bdecc7  tools/requirements.lock
028a785cb0bf603207b6fe385c9b80b9a35daa27406d5689de32fda2dd36cd4c  tools/rollback.sh
db505b23dc10ecc9f9b9a6aee75a86d21862101cbc63f6fa71d3ad3d1fb5aded  tools/stage_release.sh
00969408afe58afa257be8a306cdff6f331e1e5e2d7031b8a166816b8d0a329c  tools/system-packages.txt
ee020e8aa4f837855cc7da1791614bc3536a8491f7da0deb7b32c4a08758a90b  tools/verify_lock.py
5c0b0b779c4709d4e8dcd264eb78bed62efb5e6ede4c06c14d5bd1466b028bae  tools/video2epub.py
df03e6204a62aed3f455e73db9c023ac7ab8ebbd076ee5fd1bd1c793b9a569cf  SHA256SUMS
1a88001c2d65200c1ae6ee7c65741d7e270cd15619340a4fb291e4a7c29e2b33  skills/kindle-courier-getting-started/SKILL.md
f4eba766ba7160c0ffc9ed5dfe59dd4011b12a51fac0077c2899141133c900bd  skills/kindle-epub-build/SKILL.md
20ef2dff67563d6d6afcf1a1a20592687710a04b9b166a6aada8e9263dd22dba  skills/kindle-video-build/SKILL.md
PINS
[ "$(wc -l < "$W/pins")" = 24 ] || die "pin list damaged"
while read -r sum path; do
  [[ "$path" =~ ^(tools/[A-Za-z0-9_.-]+|SHA256SUMS|skills/[a-z-]+/SKILL\.md)$ ]] || die "bad pinned path $path"
  mkdir -p "$W/src/$(dirname "$path")"
  if [ -n "${KC_LOCAL_ROOT:-}" ]; then cp -- "$KC_LOCAL_ROOT/$path" "$W/src/$path" 2>/dev/null || die "missing $path"
  else code=$(curl -fsS --proto '=https' --tlsv1.2 --max-filesize 1000000 -o "$W/src/$path" -w '%{http_code}' "$KC_URL/$path") || die "download failed: $path"
    [ "$code" = 200 ] || die "HTTP $code for $path"; fi
  echo "$sum  $W/src/$path" | sha256sum -c --status || die "sha256 mismatch: $path"
done < "$W/pins"
grep -v '  SHA256SUMS$\|  skills/' "$W/pins" | cmp -s - "$W/src/SHA256SUMS" || die "SHA256SUMS does not list exactly the pinned tools"
echo "verified 24/24 files at commit $KC_COMMIT"
# Canonical first-run block (section 0 part 1) from the verified reviewed skill, using the downloaded skills.
export EPUB_SKILL="$W/src/skills/kindle-epub-build/SKILL.md" VIDEO_SKILL="$W/src/skills/kindle-video-build/SKILL.md"
python3 - "$EPUB_SKILL" "$W/part1.sh" <<'PY'
import sys
L = open(sys.argv[1], encoding='utf-8').read().split('\n'); i = L.index('<!-- kc:first-run-1 -->')
assert L[i + 1] == '```bash'; j = L.index('```', i + 2); open(sys.argv[2], 'w').write('\n'.join(L[i + 2:j]) + '\n')
PY
bash -eo pipefail "$W/part1.sh" || die "first-run block failed (see above)"
(cd "$B/releases/2.0.1" && sha256sum -c --quiet SHA256SUMS) || die "installed release does not verify"
for f in "$W"/src/tools/*; do cmp -s "$f" "$B/releases/2.0.1/tools/${f##*/}" || die "installed ${f##*/} differs from the pinned download"; done
echo "Kindle Courier 2.0.1 installed and active ($(readlink "$B/releases/current")). Tool sha256:"; cat "$B/releases/2.0.1/SHA256SUMS"
```
For video, then run `bash "$B/tools/ensure_tools.sh" --video`.

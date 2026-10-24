#!/usr/bin/env bash
# ensure_tools.sh (Kindle Courier 2.0.0) [--video] [--check] [--version]
# Idempotent setup under $KINDLE_BASE (default /workspace/kindle): pinned pandoc + epubcheck in deps/, a venv with
# hash-pinned Python packages (and yt-dlp/faster-whisper for --video), system packages via apt when possible.
# Checks the venv and deps specifically (global or ~/.local installs do not count). Never writes into tools/.
# Offline: set KC_OFFLINE_DIR to a folder holding the wheels plus the pandoc/epubcheck archives from deps.lock.
# One line per item: OK / INSTALLED / FAILED / OPTIONAL-MISSING / ON-DEMAND. Exit 1 if a required item FAILED.
VER=2.0.0
[ "$1" = "--version" ] && { echo "ensure_tools $VER"; exit 0; }
BASE="${KINDLE_BASE:-/workspace/kindle}"; T="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
DEPS="$BASE/deps"; VENV="$BASE/venv"; PY="$VENV/bin/python"
VIDEO=0; CHECK=0; for a in "$@"; do [ "$a" = --video ] && VIDEO=1; [ "$a" = --check ] && CHECK=1; done
mkdir -p "$BASE" "$DEPS/bin" "$BASE/work" "$BASE/locks"
exec 9>"$BASE/.setup.lock"; flock -w 900 9 || { echo "setup lock busy"; exit 1; }   # builds hold it shared
export PATH="$VENV/bin:$DEPS/bin:$PATH"
FAIL=0; SUDO=""; [ "$(id -u)" != 0 ] && sudo -n true 2>/dev/null && SUDO="sudo -n"
say(){ printf '%-16s %s\n' "$1" "$2"; [ "$2" = FAILED ] && FAIL=1; }
APTUP=0
apt_i(){ [ $CHECK = 1 ] && return 1; command -v apt-get >/dev/null || return 1
  [ $APTUP = 1 ] || { $SUDO apt-get update -qq >/dev/null 2>&1; APTUP=1; }
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq "$@" >/dev/null 2>&1; }
check(){ if eval "$2" >/dev/null 2>&1; then say "$1" OK
  elif [ $CHECK = 0 ] && eval "$3" >/dev/null 2>&1 && eval "$2" >/dev/null 2>&1; then say "$1" INSTALLED
  else say "$1" FAILED; fi; }
opt(){ if eval "$2" >/dev/null 2>&1; then say "$1" OK
  elif [ $CHECK = 0 ] && eval "$3" >/dev/null 2>&1 && eval "$2" >/dev/null 2>&1; then say "$1" INSTALLED
  else say "$1" OPTIONAL-MISSING; fi; }
lockv(){ awk -v n="$1" '$1==n{print $'"$2"'}' "$T/deps.lock"; }
fetch(){ # fetch NAME DEST: offline dir first, else download; verify sha256 from deps.lock
  local url sha f; url=$(lockv "$1" 3); sha=$(lockv "$1" 4); f="$KC_OFFLINE_DIR/$(basename "$url")"
  if [ -n "$KC_OFFLINE_DIR" ] && [ -f "$f" ]; then cp "$f" "$2"; else curl -sfL -o "$2" "$url" || return 1; fi
  echo "$sha  $2" | sha256sum -c --status; }
inst_pandoc(){ local tmp; tmp=$(mktemp -d) || return 1
  fetch pandoc "$tmp/p.tgz" && tar -xzf "$tmp/p.tgz" -C "$tmp" && rm -rf "$DEPS/pandoc-3.5" && mv "$tmp/pandoc-3.5" "$DEPS/pandoc-3.5" &&
  ln -sfn "$DEPS/pandoc-3.5/bin/pandoc" "$DEPS/bin/.pandoc.new" && mv -T "$DEPS/bin/.pandoc.new" "$DEPS/bin/pandoc"; local r=$?; rm -rf "$tmp"; return $r; }
inst_epc(){ local tmp; tmp=$(mktemp -d) || return 1
  fetch epubcheck "$tmp/e.zip" && unzip -oq "$tmp/e.zip" -d "$tmp" && rm -rf "$DEPS/epubcheck-5.1.0" && mv "$tmp/epubcheck-5.1.0" "$DEPS/epubcheck-5.1.0"; local r=$?; rm -rf "$tmp"; return $r; }
pipi(){ [ $CHECK = 1 ] && return 1
  if [ -n "$KC_OFFLINE_DIR" ]; then "$PY" -m pip install -q --require-hashes --no-index --find-links "$KC_OFFLINE_DIR" -r "$1"
  else "$PY" -m pip install -q --require-hashes -r "$1"; fi; }

check curl     'command -v curl'  'apt_i curl ca-certificates'
check unzip    'command -v unzip' 'apt_i unzip'
check java11+  'v=$(java -version 2>&1 | sed -n "s/.*version \"\([0-9]*\).*/\1/p" | head -1); [ "${v:-0}" -ge 11 ]' 'apt_i default-jre-headless'
check poppler  'command -v pdfinfo && command -v pdftotext && command -v pdfimages' 'apt_i poppler-utils'
binsha(){ [ "$(sha256sum "$2" 2>/dev/null | cut -d' ' -f1)" = "$(lockv "$1" 4)" ]; }
check pandoc-3.5 '[ "$("$DEPS/bin/pandoc" --version 2>/dev/null | head -1)" = "pandoc 3.5" ] && binsha pandoc-bin "$(readlink -f "$DEPS/bin/pandoc")"' 'inst_pandoc'
check epubcheck-5.1.0 'binsha epubcheck-jar "$DEPS/epubcheck-5.1.0/epubcheck.jar" && "$T/epubcheck" --version | grep -q "EPUBCheck v5.1.0"' 'inst_epc'
check fonts    'ls /usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf' 'apt_i fonts-dejavu-core'
opt   fonts-cjk 'ls /usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc' 'apt_i fonts-noto-cjk'
opt   tesseract 'command -v tesseract && tesseract --list-langs 2>&1 | grep -qx eng' 'apt_i tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim'
opt   ocr-chi_sim 'tesseract --list-langs 2>&1 | grep -qx chi_sim' 'apt_i tesseract-ocr-chi-sim'
# The wheel locks are for CPython 3.13 on Linux x86_64 only: any other interpreter is refused with a clear message.
SYSPY="${KC_PYTHON:-python3}"
"$SYSPY" "$T/verify_lock.py" --platform-only >/dev/null 2>&1 || { say python3.13 FAILED; "$SYSPY" "$T/verify_lock.py" --platform-only; echo "set KC_PYTHON to a CPython 3.13 interpreter"; exit 1; }
check venv     '[ -x "$PY" ] && "$PY" "$T/verify_lock.py" --platform-only' '{ "$SYSPY" -m venv "$VENV" || { apt_i python3-venv && "$SYSPY" -m venv "$VENV"; }; }'
check py-libs  '"$PY" "$T/verify_lock.py" "$T/requirements.lock" && "$PY" -c "import playwright, bs4, lxml, readability, PIL"' 'pipi "$T/requirements.lock"'
browser(){ for b in "$CHROME_PATH" /usr/bin/google-chrome /usr/bin/chromium /usr/bin/chromium-browser; do [ -n "$b" ] && [ -x "$b" ] && return 0; done
  ls "${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"/chromium*/chrome-linux*/chrome >/dev/null 2>&1; }
check chromium 'browser' '"$VENV/bin/playwright" install chromium'
vid(){ if [ $VIDEO = 1 ]; then check "$1" "$2" "$3"; elif eval "$2" >/dev/null 2>&1; then say "$1" OK; else say "$1" ON-DEMAND; fi; }
vid ffmpeg       'command -v ffmpeg && command -v ffprobe' 'apt_i ffmpeg'
vid venv-yt-dlp  '[ -x "$VENV/bin/yt-dlp" ] && "$PY" "$T/verify_lock.py" "$T/requirements-video.lock"' 'pipi "$T/requirements-video.lock"'
vid venv-faster-whisper '"$PY" "$T/verify_lock.py" "$T/requirements-video.lock" && "$PY" -c "import faster_whisper"' 'pipi "$T/requirements-video.lock"'
exit $FAIL

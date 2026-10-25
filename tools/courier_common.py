#!/usr/bin/env python3
"""courier_common: shared helpers for Kindle Courier tools (version, venv, source identity, slugs,
language units, OCR, EPUB metadata, digests). Imported by article2epub.py, video2epub.py, presend_gate.py."""
import hashlib, html as H, json, os, re, shutil, subprocess, sys, unicodedata, zipfile
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

VERSION = '2.0.0'
TOOLS_DIR = os.path.dirname(os.path.realpath(__file__))  # realpath: a release flip mid-run cannot mix versions
DEFAULT_BASE = '/workspace/kindle'
BASE = os.environ.get('KINDLE_BASE') or DEFAULT_BASE
VENV = os.path.join(BASE, 'venv')
DEPS = os.path.join(BASE, 'deps')
_LOCKS = []

def lock(name, shared=True, timeout=600):
  """flock on $KINDLE_BASE/<name>. Tools hold shared locks on .release.lock (activation flips) and
  .setup.lock (venv/deps installs) for their whole run; activate.sh / ensure_tools.sh take them exclusively."""
  import fcntl, time
  check_base()
  fd = os.open(os.path.join(BASE, name), os.O_RDWR | os.O_CREAT, 0o644)
  mode = (fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
  t0 = time.time()
  while True:
    try: fcntl.flock(fd, mode | fcntl.LOCK_NB); break
    except BlockingIOError:
      if time.time() - t0 > timeout: os.close(fd); sys.exit(f'timed out waiting for lock {name}')
      time.sleep(0.2)
  _LOCKS.append(fd); return fd

def check_base():
  """A missing or misspelled base is an error (ensure_tools.sh creates it); an unset KINDLE_BASE is logged."""
  if not os.environ.get('KINDLE_BASE') and not os.environ.get('KC_BASE_LOGGED'):
    print(f'KINDLE_BASE not set; using default {DEFAULT_BASE}', file=sys.stderr); os.environ['KC_BASE_LOGGED'] = '1'
  if not os.path.isdir(BASE): sys.exit(f'KINDLE_BASE {BASE} does not exist; run ensure_tools.sh to initialise it')

def ensure_venv():
  """Re-exec the calling script inside $KINDLE_BASE/venv (if it exists), put venv/bin and deps/bin first on
  PATH so subprocesses (yt-dlp, playwright, pandoc) come from the pipeline, then take the shared run locks."""
  vp = os.path.join(VENV, 'bin', 'python')
  path = os.environ.get('PATH', '')
  pre = [os.path.join(VENV, 'bin'), os.path.join(DEPS, 'bin')]
  os.environ['PATH'] = os.pathsep.join(pre + [p for p in path.split(os.pathsep) if p and p not in pre])
  if os.path.exists(vp) and os.path.realpath(sys.prefix) != os.path.realpath(VENV) and not os.environ.get('KC_NO_REEXEC'):
    if os.environ.get('KC_REEXEC') == '1': sys.exit('venv re-exec loop: %s did not become the interpreter' % vp)
    os.environ['KC_REEXEC'] = '1'
    os.execv(vp, [vp] + sys.argv)
  os.environ.pop('KC_REEXEC', None)
  lock('.release.lock'); lock('.setup.lock')

OVERRIDES = ('KC_ALLOW_SYSTEM_PANDOC', 'KC_NO_REEXEC', 'KC_ALLOW_PRIVATE_FETCH', 'KC_DISABLE_OCR')
EPUBCHECK_JAR_SHA256 = 'e03657179297d35885336474b8c7929957e3a073b5b95c6bf8765b9408a0de9f'

def build_env():
  """Everything outside the inputs that changes output: recorded in job.json and part of the build identity."""
  pv = ''
  try: pv = subprocess.run([pandoc_bin(), '--version'], capture_output=True, text=True, timeout=30).stdout.splitlines()[0]
  except BaseException: pv = 'unavailable'
  jar = os.path.join(DEPS, 'epubcheck-5.1.0', 'epubcheck.jar')
  return {'version': VERSION, 'pandoc': pv, 'epubcheck_jar_sha256': sha256_file(jar) if os.path.exists(jar) else None,
          'python': sys.version.split()[0], 'overrides': {k: os.environ[k] for k in OVERRIDES if os.environ.get(k)}}

def pandoc_bin():
  """Pinned pandoc from deps (installed by ensure_tools.sh). Fail closed if absent: output differs by version."""
  p = os.path.join(DEPS, 'bin', 'pandoc')
  if os.path.exists(p): return p
  if os.environ.get('KC_ALLOW_SYSTEM_PANDOC') and shutil.which('pandoc'): return shutil.which('pandoc')
  sys.exit('pinned pandoc missing: run ensure_tools.sh')

EPUBCHECK = os.path.join(TOOLS_DIR, 'epubcheck')  # unit tests may point this at a labelled fake

def run_epubcheck(path, jsonfile):
  """Run the pinned epubcheck and accept its verdict only from a fresh, well-formed report about this exact file.
  Returns (counts, messages) when the report is trustworthy (counts may contain errors), else (None, reason).
  Fail closed: nonzero exit without reported errors, missing/stale/empty/malformed report, or a report naming
  another file all return None."""
  import time
  if os.path.exists(jsonfile): os.remove(jsonfile)
  t0 = time.time() - 1
  try: r = subprocess.run([EPUBCHECK, path, '--json', jsonfile], capture_output=True, text=True, timeout=600)
  except Exception as e: return None, f'epubcheck did not run: {e}'
  if not os.path.exists(jsonfile): return None, f'epubcheck wrote no report (exit {r.returncode}): {(r.stderr or r.stdout)[-300:]}'
  if os.path.getmtime(jsonfile) < t0: return None, 'stale epubcheck report'
  try: rep = json.load(open(jsonfile))
  except Exception as e: return None, f'malformed epubcheck report: {e}'
  msgs = rep.get('messages') if isinstance(rep, dict) else None
  chk = rep.get('checker') if isinstance(rep, dict) else None
  if not isinstance(msgs, list) or not isinstance(chk, dict): return None, 'epubcheck report lacks messages/checker'
  if chk.get('filename') != os.path.basename(path): return None, f"epubcheck report is about {chk.get('filename')!r}, not {os.path.basename(path)!r}"
  cnt = {k: sum(1 for m in msgs if isinstance(m, dict) and m.get('severity') == k.upper()) for k in ('fatal', 'error', 'warning')}
  if (chk.get('nFatal', 0), chk.get('nError', 0)) != (cnt['fatal'], cnt['error']) and not (cnt['fatal'] or cnt['error']):
    cnt['fatal'] = max(cnt['fatal'], chk.get('nFatal', 0) or 0); cnt['error'] = max(cnt['error'], chk.get('nError', 0) or 0)
  if r.returncode != 0 and not (cnt['fatal'] or cnt['error']): return None, f'epubcheck exited {r.returncode} without reporting errors'
  return cnt, msgs

def check_url(u):
  """Only http(s) URLs reach yt-dlp/fetchers (a leading '-' could be parsed as an option)."""
  if not re.match(r'^https?://[^\s/]+', u or '') or u.startswith('-'):
    raise ValueError(f'refusing non-http(s) URL: {u!r}')
  return u

class FetchError(Exception): pass

def resolve_vetted(host, port):
  """Resolve once and return one vetted IP. Every address must be public (no loopback/private/link-local/metadata),
  unless KC_ALLOW_PRIVATE_FETCH is set (tests only; recorded in job.json)."""
  import ipaddress, socket
  try: infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
  except socket.gaierror as e: raise FetchError(f'DNS resolution failed for {host}: {e}')
  ips = []
  for i in infos:
    ip = ipaddress.ip_address(i[4][0].split('%')[0])
    if not os.environ.get('KC_ALLOW_PRIVATE_FETCH') and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
      raise FetchError(f'non-public address refused: {host} -> {ip}')
    ips.append(str(ip))
  if not ips: raise FetchError(f'DNS returned no address for {host}')
  return ips[0]

def safe_fetch(url, max_bytes=40 * 1024 * 1024, max_hops=5, timeout=60, headers=None):
  """GET with an SSRF guard: http(s) only; every hop (redirects are followed by hand) is re-validated; the connection
  goes to the vetted IP (Host header and TLS SNI/certificate check use the hostname), defeating DNS rebinding;
  the body is capped. Returns bytes and the final URL."""
  import http.client, socket, ssl
  from urllib.parse import urljoin as _uj
  for hop in range(max_hops + 1):
    try: check_url(url)
    except ValueError as e: raise FetchError(str(e))
    p = urlsplit(url); host = p.hostname; port = p.port or (443 if p.scheme == 'https' else 80)
    ip = resolve_vetted(host, port)
    if p.scheme == 'https':
      ctx = ssl.create_default_context()
      class Conn(http.client.HTTPSConnection):
        def connect(self):
          sock = socket.create_connection((ip, port), timeout)
          self.sock = ctx.wrap_socket(sock, server_hostname=host)
      conn = Conn(host, port, timeout=timeout, context=ctx)
    else:
      class Conn(http.client.HTTPConnection):
        def connect(self): self.sock = socket.create_connection((ip, port), timeout)
      conn = Conn(host, port, timeout=timeout)
    path = (p.path or '/') + (('?' + p.query) if p.query else '')
    try:
      conn.request('GET', path, headers=dict({'Host': p.netloc, 'User-Agent': 'Mozilla/5.0 (KindleCourier)'}, **(headers or {})))
      r = conn.getresponse()
      if r.status in (301, 302, 303, 307, 308):
        loc = r.getheader('Location'); conn.close()
        if not loc: raise FetchError('redirect without Location')
        url = _uj(url, loc); continue
      if r.status != 200: raise FetchError(f'HTTP {r.status} for {url}')
      cl = r.getheader('Content-Length')
      if cl and cl.isdigit() and int(cl) > max_bytes: raise FetchError(f'response too large ({cl} bytes)')
      data = r.read(max_bytes + 1)
      if len(data) > max_bytes: raise FetchError(f'response larger than {max_bytes} bytes')
      return data, url, r.getheader('Content-Type') or ''
    except (OSError, http.client.HTTPException) as e: raise FetchError(f'fetch failed for {url}: {e}')
    finally: conn.close()
  raise FetchError(f'too many redirects (> {max_hops})')

def tool_hash(*names):
  """Short hash of tool source files: cache keys change whenever the code changes."""
  h = hashlib.sha256(VERSION.encode())
  for n in names or ('courier_common.py',):
    p = os.path.join(TOOLS_DIR, n)
    h.update(open(p, 'rb').read() if os.path.exists(p) else n.encode())
  return h.hexdigest()[:12]

def sha256_file(p):
  h = hashlib.sha256()
  with open(p, 'rb') as f:
    for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
  return h.hexdigest()

def sha256_text(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()

def key_of(*parts):
  return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

X_TRACKING = re.compile(r'^(s|t|utm_.*|ref_src|ref_url)$', re.I)

def _on(host, dom): return host == dom or host.endswith('.' + dom)

def normalize_source(u):
  """Stable identity for a source. Known hosts only (exact host or subdomain, parsed with urllib):
  x.com/twitter.com status/article -> 'x:<id>'; youtube.com/youtu.be -> 'youtube:<id>'.
  Every other URL keeps its full path and query (only the #fragment is dropped): generic query params are content."""
  u = (u or '').strip()
  if not u: return ''
  if u.startswith('upload:'): return u
  if not re.match(r'^[a-z][a-z0-9+.-]*://', u, re.I):
    return 'file:' + os.path.realpath(u) if os.path.exists(u) else u
  p = urlsplit(u); host = (p.hostname or '').lower()
  if _on(host, 'x.com') or _on(host, 'twitter.com'):
    m = re.match(r'^/(?:[^/]+/status|i/status|i/web/status|i/article|[^/]+/article)/(\d+)', p.path)
    if m: return 'x:' + m.group(1)
    q = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not X_TRACKING.match(k)])
    return urlunsplit(('https', 'x.com', p.path.rstrip('/') or '/', q, ''))
  if _on(host, 'youtube.com') or _on(host, 'youtube-nocookie.com'):
    if p.path == '/watch':
      v = dict(parse_qsl(p.query)).get('v', '')
      if re.fullmatch(r'[\w-]{11}', v): return 'youtube:' + v
    m = re.match(r'^/(?:shorts|live|embed|v)/([\w-]{11})(?:[/?]|$)', p.path)
    if m: return 'youtube:' + m.group(1)
  if host == 'youtu.be':
    m = re.match(r'^/([\w-]{11})(?:/|$)', p.path)
    if m: return 'youtube:' + m.group(1)
  # Generic sites: host (including www.), path (including a trailing slash) and the full query are kept exactly; only the
  # #fragment is dropped. A missed merge only costs a harmless duplicate build; a wrong merge could mix sources.
  netloc = host + (f':{p.port}' if p.port else '')
  return urlunsplit((p.scheme.lower(), netloc, p.path or '/', p.query, ''))

def source_key(u): return hashlib.sha256(normalize_source(u).encode()).hexdigest()[:16]

def slugify(title, source=None, maxlen=60):
  """Filesystem-safe slug that keeps CJK/Unicode letters; a source-hash suffix keeps different sources apart."""
  s = unicodedata.normalize('NFKC', title or '').lower()
  s = re.sub(r'[^\w\s-]', '', s)  # Unicode-aware: CJK characters are \w and survive
  s = re.sub(r'[\s_-]+', '-', s).strip('-')[:maxlen].strip('-') or 'untitled'
  return f'{s}-{source_key(source)[:10]}' if source else s

CJK = re.compile('[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af\U00020000-\U0002fa1f]')

def count_units(text):
  """Language-aware size: CJK ideographs, kana and hangul count one unit each; other text counts words.
  Mixed text = words + CJK characters."""
  text = text or ''
  cjk = len(CJK.findall(text))
  words = len([w for w in CJK.sub(' ', text).split() if re.search(r'\w', w)])
  return {'words': words, 'cjk_chars': cjk, 'units': words + cjk}

def min_units_for(c, latin=150, cjk=300):
  """Adequacy threshold: 150 words for word-based text; 300 characters when CJK characters dominate
  (one CJK character carries roughly half an English word); proportional in between."""
  if not c['units']: return latin
  share = c['cjk_chars'] / c['units']
  return round(latin + (cjk - latin) * share)

def norm_text(s):
  s = unicodedata.normalize('NFKC', H.unescape(s or ''))
  return re.sub(r'\s+', ' ', s).strip()

def norm_key(s):
  """Loose comparison key for titles/headings: casefold, drop punctuation, emoji and spaces."""
  return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', s or '').casefold())

def pick_lang_info(tracks, pref):
  """(track, fallback) where fallback is True when the chosen track is not the preferred language."""
  k = pick_lang(tracks, pref)
  return k, bool(pref and k and lang_base(k) != lang_base(pref))

def lang_base(code): return re.split(r'[-_]', (code or '').lower())[0]

def pick_lang(tracks, pref):
  """Choose a caption track: exact pref (and its -orig), then same-language variants
  (zh-CN -> zh, zh-Hans, zh-TW, ...; -orig first), then original-language tracks when no pref,
  then English, then anything."""
  keys = list(tracks or {})
  if not keys: return None
  low = {k.lower(): k for k in keys}
  if pref:
    p = pref.lower()
    for c in (p, p + '-orig'):
      if c in low: return low[c]
    base = lang_base(p)
    same = [k for k in keys if lang_base(k) == base]
    if base == 'zh':  # script-aware ordering for Chinese
      simp = ('hans', 'cn', 'sg', 'my'); trad = ('hant', 'tw', 'hk', 'mo')
      want = simp if any(x in p for x in simp) else trad if any(x in p for x in trad) else ()
      same.sort(key=lambda k: (0 if k.lower() in (base, base + '-orig') else 1 if any(x in k.lower() for x in want) else 2, '-orig' not in k.lower(), k))
    else:
      same.sort(key=lambda k: (k.lower() not in (base, base + '-orig'), '-orig' not in k.lower(), k))
    if same: return same[0]
  else:
    orig = [k for k in keys if k.lower().endswith('-orig')]
    if orig: return orig[0]
  for c in ('en', 'en-orig', 'en-us', 'en-gb'):
    if c in low: return low[c]
  en = [k for k in keys if lang_base(k) == 'en']
  return en[0] if en else keys[0]

# ---------- OCR ----------
def ocr_langs(lang):
  try: have = set(subprocess.run(['tesseract', '--list-langs'], capture_output=True, text=True, timeout=30).stdout.split())
  except Exception: return None
  want = ['chi_sim', 'eng'] if lang_base(lang) == 'zh' else ['jpn', 'eng'] if lang_base(lang) == 'ja' else ['eng', 'chi_sim']
  got = [l for l in want if l in have]
  return '+'.join(got) if got else None

def ocr_available(lang='en'):
  return bool(shutil.which('tesseract')) and bool(ocr_langs(lang)) and not os.environ.get('KC_DISABLE_OCR')

def ocr_image(path, lang='en', min_chars=40):
  """Return (status, text). status: 'text' (text-heavy), 'little-text', 'unavailable', 'error'."""
  if not ocr_available(lang): return 'unavailable', ''
  try:
    r = subprocess.run(['tesseract', path, 'stdout', '-l', ocr_langs(lang), '--psm', '3'], capture_output=True, text=True, timeout=180)
  except Exception as e: return 'error', str(e)
  if r.returncode: return 'error', r.stderr.strip()[-300:]
  txt = '\n'.join(l.rstrip() for l in r.stdout.splitlines())
  txt = re.sub(r'\n{3,}', '\n\n', txt).strip()
  signal = len(re.findall(r'[A-Za-z0-9]', txt)) + 2 * len(CJK.findall(txt))
  return ('text' if signal >= min_chars else 'little-text'), txt

def ocr_block_html(txt):
  paras = [p.strip() for p in re.split(r'\n\s*\n', txt) if p.strip()]
  body = ''.join('<p>' + H.escape(p).replace('\n', '<br/>') + '</p>' for p in paras)
  return ('<div class="ocr"><p class="ocr-label"><em>Machine-transcribed text from the image above (OCR; may contain errors, '
          'the image is the original):</em></p>' + body + '</div>')

# ---------- EPUB inspection ----------
def epub_meta(path):
  """dc:title, dc:creator, dc:language, dc:source, dc:identifier from the OPF."""
  with zipfile.ZipFile(path) as z:
    cont = z.read('META-INF/container.xml').decode('utf-8', 'replace')
    opf_name = re.search(r'full-path="([^"]+)"', cont).group(1)
    opf = z.read(opf_name).decode('utf-8', 'replace')
  g = lambda tag: [H.unescape(x).strip() for x in re.findall(rf'<dc:{tag}\b[^>]*>(.*?)</dc:{tag}>', opf, re.S)]
  return {'title': (g('title') or [''])[0], 'creator': (g('creator') or [''])[0], 'language': (g('language') or [''])[0],
          'source': (g('source') or [''])[0], 'identifiers': g('identifier')}

def epub_text(path):
  with zipfile.ZipFile(path) as z:
    return '\n'.join(z.read(n).decode('utf-8', 'replace') for n in sorted(z.namelist()) if re.search(r'\.x?html$', n))

def content_digest(path):
  """Digest of a book's content that ignores build timestamps (dcterms:modified, dc:date with time)."""
  h = hashlib.sha256()
  if not zipfile.is_zipfile(path):
    return sha256_file(path)
  with zipfile.ZipFile(path) as z:
    for n in sorted(z.namelist()):
      b = z.read(n)
      if n.endswith('.opf'):
        b = re.sub(rb'<meta property="dcterms:modified">[^<]*</meta>', b'', b)
        b = re.sub(rb'(<dc:date[^>]*>\d{4}-\d{2}-\d{2})T[^<]*(</dc:date>)', rb'\1\2', b)
      h.update(n.encode() + b'\0' + hashlib.sha256(b).digest())
  return h.hexdigest()

def sniff_mime(path):
  with open(path, 'rb') as f: head = f.read(64)
  if head.startswith(b'%PDF-'): return 'application/pdf'
  if head.startswith(b'PK\x03\x04'):
    try:
      with zipfile.ZipFile(path) as z:
        first = z.infolist()[0]
        if first.filename == 'mimetype' and z.read('mimetype').strip() == b'application/epub+zip': return 'application/epub+zip'
      return 'application/zip'
    except Exception: return 'application/octet-stream'
  return 'application/octet-stream'

def classify_pdf(path):
  """'prose' (mostly running text: reflow is OK) or 'layout-heavy' (keep as PDF). Conservative: unknown -> layout-heavy."""
  try:
    info = subprocess.run(['pdfinfo', path], capture_output=True, text=True, timeout=60)
    pages = int(re.search(r'^Pages:\s+(\d+)', info.stdout, re.M).group(1))
    txt = subprocess.run(['pdftotext', '-layout', path, '-'], capture_output=True, text=True, timeout=120).stdout
    imgs = subprocess.run(['pdfimages', '-list', path], capture_output=True, text=True, timeout=60).stdout.splitlines()[2:]
  except Exception as e:
    return {'class': 'layout-heavy', 'reason': f'could not analyse ({e})'}
  chars_pp = len(re.sub(r'\s', '', txt)) / max(pages, 1)
  lines = [l for l in txt.splitlines() if l.strip()]
  multicol = sum(1 for l in lines if re.search(r'\S {4,}\S', l.strip())) / max(len(lines), 1)
  imgs_pp = len(imgs) / max(pages, 1)
  cls = 'prose' if chars_pp >= 800 and multicol < 0.25 and imgs_pp < 1 else 'layout-heavy'
  return {'class': cls, 'pages': pages, 'chars_per_page': round(chars_pp), 'multicolumn_line_share': round(multicol, 2),
          'images_per_page': round(imgs_pp, 2)}

def status_stages(built=False, validated=False):
  """Honest delivery stages. email_sent is set only by the ledger after a send; device_confirmed is never
  set by any tool (only an owner's explicit confirmation, recorded by hand)."""
  return {'built': bool(built), 'validated': bool(validated), 'email_sent': False, 'device_confirmed': False}

def write_json(path, obj):
  tmp = path + '.tmp'
  with open(tmp, 'w', encoding='utf-8') as f: json.dump(obj, f, ensure_ascii=False, indent=1); f.write('\n')
  os.replace(tmp, path)

# ---------- output locks, commit and manifest binding ----------
def lock_path(path, timeout=600):
  """Exclusive per-output-path lock ($KINDLE_BASE/locks/<hash of the absolute path>.lock) with a timeout."""
  import fcntl, time
  os.makedirs(os.path.join(BASE, 'locks'), exist_ok=True)
  fd = os.open(os.path.join(BASE, 'locks', sha256_text(os.path.abspath(path))[:24] + '.lock'), os.O_RDWR | os.O_CREAT, 0o644); t0 = time.time()
  while True:
    try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); return fd
    except BlockingIOError:
      if time.time() - t0 > timeout: os.close(fd); raise TimeoutError(f'another build of {path} holds the lock (waited {timeout}s)')
      time.sleep(0.2)

def review_name(out): return re.sub(r'\.epub$', '', out) + '.needs-review.epub'

STATUSES = ('complete', 'needs_review', 'incomplete', 'text_only')
MANIFEST_SCHEMA = {'tool': str, 'version': str, 'job_id': str, 'source_id': str, 'epub_sha256': str, 'status': str, 'complete': bool,
                   'review_needed': bool, 'failures': list, 'omissions': list, 'review_reasons': list, 'review': dict}

def validate_manifest(m):
  """Schema check: required keys with the right types, an allowed status, and complete/status consistency."""
  errs = []
  if not isinstance(m, dict): return ['manifest is not a JSON object']
  for k, t in MANIFEST_SCHEMA.items():
    if k not in m: errs.append(f'manifest lacks {k}')
    elif not isinstance(m[k], t): errs.append(f'manifest {k} is not {t.__name__}')
  if errs: return errs
  if m['status'] not in STATUSES: errs.append(f"manifest status {m['status']!r} not allowed")
  if m['complete'] != (m['status'] == 'complete'): errs.append('manifest complete flag contradicts its status')
  if m['status'] == 'complete' and (m['failures'] or m['omissions'] or m['review_reasons'] or m['review_needed']):
    errs.append('manifest says complete but lists failures/omissions/review reasons')
  if not re.fullmatch(r'[0-9a-f]{64}', m['epub_sha256']): errs.append('manifest epub_sha256 malformed')
  return errs

def commit_book(tmp_out, final, job, manifest, crash=lambda name: None):
  """Atomic commit of book + manifest + job. Binding: manifest records job_id, source_id and the EPUB sha256; job.json
  (written last, the commit record) records the EPUB sha256 and the manifest's sha256. The gate recomputes all of them
  from the files, so a crash between steps or an edited/forged sidecar is rejected."""
  sha = sha256_file(tmp_out)
  manifest.update(job_id=job['job_id'], source_id=job['source_id'], epub_sha256=sha, epub=final)
  manifest.setdefault('review', {'acknowledged': False})
  errs = validate_manifest(manifest)
  if errs: raise ValueError('internal: invalid manifest: ' + '; '.join(errs))
  job.update(epub=final, epub_sha256=sha, content_digest=content_digest(tmp_out))
  for f in (final + '.job.json',):
    if os.path.exists(f): os.remove(f)  # an old commit record must not vouch for the new book
  os.replace(tmp_out, final); crash('after-book')
  write_json(final + '.manifest.json', manifest); crash('after-manifest')
  job['manifest_sha256'] = sha256_file(final + '.manifest.json')
  write_json(final + '.job.json', job)
  return sha

def check_binding(path, job, manifest_path):
  """Gate-side verification of commit_book's binding; returns a list of errors (empty = bound)."""
  errs = []
  if not isinstance(job, dict): return ['job file is not a JSON object']
  for k in ('job_id', 'source_id', 'epub_sha256', 'manifest_sha256'):
    if not isinstance(job.get(k), str) or not job.get(k): errs.append(f'job lacks {k}')
  if errs: return errs
  if not os.path.exists(manifest_path): return ['content manifest missing']
  if sha256_file(manifest_path) != job['manifest_sha256']: errs.append('manifest bytes do not match the job record (edited or from another build)')
  try: m = json.load(open(manifest_path, encoding='utf-8'))
  except Exception as e: return errs + [f'manifest unreadable: {e}']
  errs += validate_manifest(m)
  if errs: return errs
  actual = sha256_file(path)
  if job['epub_sha256'] != actual: errs.append('file sha256 does not match the job record (stale or foreign file)')
  if m['epub_sha256'] != actual: errs.append('manifest describes another file')
  if m['job_id'] != job['job_id'] or m['source_id'] != job['source_id']: errs.append('manifest job_id/source_id do not match the job')
  return errs

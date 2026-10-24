---
name: kindle-video-build
description: >-
  Kindle Courier only: turn a public video link (X, YouTube or another yt-dlp-supported site) into a transcript EPUB
  from captions or, failing that, faster-whisper speech-to-text. Text only: the visuals are not in the book.
---
# Kindle video build (Kindle Courier 2.0.0)

Base dir `${KINDLE_BASE:-/workspace/kindle}` (`$B`). Requires `bash "$B/tools/ensure_tools.sh" --video` first (yt-dlp, faster-whisper and ffmpeg are checked inside the venv).

1. Write a JSON job file (never put titles or URLs in a shell command): `url`, optional `title`, `author`, `date`, `lang`, `post_text`, `frames` (0..3), `out`.
2. `python3 "$B/tools/video2epub.py" --job /path/job.json`. It re-executes inside the venv; `--doctor` shows which yt-dlp/whisper it uses.
3. Exit 0 = complete; 3 = too little speech (no book; the JSON shows the counted units: CJK characters count one each, other text counts words, threshold 150 words or up to 300 CJK characters); 2 = refused (bad URL, workdir/output from another source); 4 = epubcheck failed (`.broken`); 5 = held for review (e.g. captions only in another language).
4. Then follow kindle-epub-build steps 3 to 5 (gate, ledger, honest report). Tell the owner the transcript method; speech-to-text can be wrong, and the video's visuals are not included.

Caches are keyed by the video's identity, language, model, captions mode and tool version, and checked before reuse, so different videos never share files even with the same or all-Chinese titles.

## Embedded files (byte-identical to the 2.0.0 tools)

### file: tools/video2epub.py
````python
#!/usr/bin/env python3
"""video2epub (Kindle Courier): a video URL that yt-dlp supports -> transcript EPUB (text only; visuals are not included
except optional frames). Captions first (published, then auto-generated, best language match), faster-whisper fallback.

Usage: video2epub.py --job JOB.json   (preferred: values never pass through a shell)
   or: video2epub.py URL [--title T] [--author A] [--date YYYY-MM-DD] [--publisher P] [--post-text TEXT] [--lang xx]
                     [--model small] [--frames 0..3] [--workdir DIR] [--out FILE.epub] [--min-units N] [--no-captions] [--force]
       video2epub.py --doctor | --version

Media and transcripts are cached per source identity (normalized URL / video id) and per options (lang, model, captions
mode) and tool version; every cached file carries a sidecar that is checked before reuse. Workdirs are keyed the same way,
so equal or all-Chinese titles never share files. Adequacy counts CJK characters/kana as units (mixed = words + CJK).
Exit: 0 ok; 2 input/refused (bad URL, workdir or output belongs to another source); 3 too little speech (no EPUB);
4 epubcheck errors or could not run (.broken, nothing at --out); 5 built but incomplete/needs review.
"""
import argparse, glob, html, json, os, re, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import courier_common as C
if __name__ == '__main__':
  if '--version' in sys.argv: print('video2epub', C.VERSION); sys.exit(0)
  C.ensure_venv()
BASE = C.BASE
EMOJI = re.compile('[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U000E0000-\U000E007F\uFE0E\uFE0F\u200D\u20E3\u2300-\u23FF]')
def noemoji(s): return re.sub(r'\s+', ' ', EMOJI.sub('', s or '')).strip(' -|')
def log(*a): print(*a, file=sys.stderr)
PLAYER_CLIENTS = [None, 'default', 'tv,web_safari', 'mweb', 'android_vr', 'ios', 'web_embedded']
TOOL_HASH = C.tool_hash('video2epub.py', 'courier_common.py')

def run(cmd, **kw):
  """Run a command; yt-dlp is retried with alternate YouTube player clients. The URL always follows '--'."""
  if cmd[0] != 'yt-dlp':
    log('+', ' '.join(cmd)); return subprocess.run(cmd, check=True, **kw)
  last = None
  for i, pc in enumerate(PLAYER_CLIENTS):
    c2 = cmd[:1] + (['--extractor-args', f'youtube:player_client={pc}'] if pc else []) + cmd[1:]
    log('+', ' '.join(c2))
    try: return subprocess.run(c2, check=True, **kw)
    except subprocess.CalledProcessError as e: last = e; time.sleep(min(2 + i, float(os.environ.get('KC_RETRY_SLEEP', 6))))
  raise last

def ts(sec):
  sec = int(sec); h, r = divmod(sec, 3600); m, s = divmod(r, 60)
  return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'

def slugify(s, source=None): return C.slugify(s, source)
def pick_lang(tracks, pref): return C.pick_lang(tracks, pref)

def parse_vtt(path, touch=0.05, blip=0.05):
  """Return [(start_sec, text)] from a WebVTT file.
  Parsing: blocks are separated by blank lines; WEBVTT header, NOTE, STYLE and REGION blocks are ignored; a line
  before the '-->' timing line is the cue identifier (never text).
  Dedupe only on evidence of rolling/overlapping captions, never on equal text alone:
  - real overlap: same text as an emitted line that ends after this cue starts (start < previous end - 50 ms; touching
    cues with float jitter are not overlap);
  - rolling evidence: a multi-line cue whose first line repeats the previous emitted line in contiguous time
    (YouTube auto-captions carry the old line on top), or a <=50 ms transition cue repeating it;
  - prefix continuation: a line that extends the previous emitted line in contiguous time replaces it.
  Separate repeated utterances, including touching cues such as 0-1 'Go.' and 1-2 'Go.', are kept."""
  tre = re.compile(r'^(?:(\d+):)?(\d+):(\d+)[.,](\d+)\s*-->\s*(?:(\d+):)?(\d+):(\d+)[.,](\d+)')
  sec = lambda h, m, s, ms: int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, '0')[:3]) / 1000
  text = open(path, encoding='utf-8-sig', errors='replace').read().replace('\r\n', '\n').replace('\r', '\n')
  cues = []
  for block in re.split(r'\n[ \t]*\n', text):
    lines = [l.strip() for l in block.split('\n') if l.strip()]
    if not lines or re.match(r'^(WEBVTT|NOTE|STYLE|REGION)\b', lines[0]): continue
    ti = 0 if '-->' in lines[0] else 1 if len(lines) > 1 and '-->' in lines[1] else None
    if ti is None: continue
    m = tre.match(lines[ti])
    if not m: continue
    g = m.groups(); st, en = sec(*g[:4]), sec(*g[4:])
    body = [html.unescape(re.sub(r'<[^>]+>', '', l)).strip() for l in lines[ti + 1:]]
    cues.append((st, en, [b for b in body if b]))
  out = []          # [start, text, last_end]
  for st, en, lines in cues:
    transition = (en - st) <= blip
    for i, l in enumerate(lines):
      prev = out[-1] if out else None
      overl = next((o for o in reversed(out[-6:]) if o[1] == l and st < o[2] - touch), None)
      if overl: overl[2] = max(overl[2], en); continue
      contiguous = prev is not None and prev[2] >= st - touch
      if contiguous and prev[1] == l and ((i == 0 and len(lines) > 1) or transition):
        prev[2] = max(prev[2], en); continue
      if contiguous and l.startswith(prev[1]) and len(l) > len(prev[1]):
        prev[1] = l; prev[2] = max(prev[2], en); continue
      out.append([st, l, en])
  return [(o[0], o[1]) for o in out]

def media(kind, url, source_id, cache, fmt=None):
  """Cached audio/video for this source only: the sidecar must name the same source identity and format and the
  file hash must match; otherwise the file is discarded and downloaded again."""
  os.makedirs(cache, exist_ok=True)
  path = os.path.join(cache, 'audio.m4a' if kind == 'audio' else 'video.mp4'); side = path + '.json'
  if os.path.exists(path):
    try:
      sc = json.load(open(side))
      if sc.get('source_id') == source_id and sc.get('format') == fmt and sc.get('sha256') == C.sha256_file(path): return path
      log(f'cache rejected for {kind}: sidecar does not match this source/options')
    except Exception: log(f'cache rejected for {kind}: missing/invalid sidecar')
    os.remove(path)
  tmpd = tempfile.mkdtemp(dir=cache)
  try:
    if kind == 'audio':
      run(['yt-dlp', '-N', '8', '-f', 'bestaudio/worst', '-x', '--audio-format', 'm4a', '-o', os.path.join(tmpd, 'audio.%(ext)s'), '--', url])
      got = os.path.join(tmpd, 'audio.m4a')
    else:
      got = os.path.join(tmpd, 'video.mp4'); run(['yt-dlp', '-N', '8', '-f', fmt, '-o', got, '--', url])
    if not os.path.exists(got): raise RuntimeError(f'{kind} download produced no file')
    os.replace(got, path); C.write_json(side, {'source_id': source_id, 'url': url, 'format': fmt, 'sha256': C.sha256_file(path)})
  finally: shutil.rmtree(tmpd, ignore_errors=True)
  return path

def get_captions(url, wd, lang_pref, meta):
  pref = lang_pref or meta.get('language') or None
  for flag, key in (('--write-subs', 'subtitles'), ('--write-auto-subs', 'automatic_captions')):
    tracks = {k: v for k, v in (meta.get(key) or {}).items() if k != 'live_chat'}
    if not tracks: continue
    lang, fallback = C.pick_lang_info(tracks, pref)
    sd = tempfile.mkdtemp(prefix='subs-', dir=wd)
    try:
      run(['yt-dlp', '--skip-download', flag, '--sub-langs', lang, '--sub-format', 'vtt/srt/best',
           '--convert-subs', 'vtt', '-o', os.path.join(sd, 'subs.%(ext)s'), '--', url])
    except subprocess.CalledProcessError: shutil.rmtree(sd, ignore_errors=True); continue
    files = sorted(glob.glob(os.path.join(sd, 'subs*.vtt')))
    if files:
      segs = parse_vtt(files[0]); shutil.rmtree(sd, ignore_errors=True)
      return segs, ('auto-generated captions' if 'auto' in flag else 'published captions'), lang.replace('-orig', ''), fallback
    shutil.rmtree(sd, ignore_errors=True)
  return None, None, None, False

def whisper(url, source_id, cache, model, lang):
  audio = media('audio', url, source_id, cache)
  from faster_whisper import WhisperModel
  m = WhisperModel(model, device='cpu', compute_type='int8', cpu_threads=os.cpu_count())
  import numpy as np
  pcm = subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-i', audio, '-f', 's16le', '-ac', '1', '-ar', '16000', '-'],
                       capture_output=True, check=True).stdout
  samples = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
  segs, info = m.transcribe(samples, language=lang, vad_filter=True, beam_size=1)
  out = []; t0 = time.time()
  for s in segs:
    out.append((s.start, s.text.strip()))
    if len(out) % 50 == 0: log(f'  {ts(s.end)} transcribed ({time.time()-t0:.0f}s)')
  return out, f'faster-whisper "{model}" model (CPU, int8, VAD)', info.language

def paragraphs(segs, max_units=110, stamp_every=60):
  """Group segments into paragraphs by language-aware units; break on sentence end; timestamp ~every minute."""
  paras, cur, cur_t, last_stamp = [], [], None, -10**9
  for t, s in segs:
    if cur_t is None: cur_t = t
    cur.append(s)
    c = C.count_units(' '.join(cur)); lim = max_units * (2 if c['cjk_chars'] > c['words'] else 1)
    if (c['units'] >= lim and re.search(r'[.!?。！？]["”’)]?$', s)) or c['units'] >= 1.8 * lim:
      paras.append((cur_t, ' '.join(cur))); cur, cur_t = [], None
  if cur: paras.append((cur_t, ' '.join(cur)))
  out = []
  for t, p in paras:
    stamp = t - last_stamp >= stamp_every
    if stamp: last_stamp = t
    out.append((t if stamp else None, re.sub(r'\s+', ' ', p).strip()))
  return out

def doctor():
  import importlib.util
  info = {'version': C.VERSION, 'python': sys.executable, 'prefix': sys.prefix, 'venv': C.VENV,
          'yt_dlp': shutil.which('yt-dlp'), 'ffmpeg': shutil.which('ffmpeg'),
          'faster_whisper': bool(importlib.util.find_spec('faster_whisper')), 'pandoc': os.path.join(C.DEPS, 'bin', 'pandoc')}
  info['ok'] = bool(info['yt_dlp'] and info['yt_dlp'].startswith(C.VENV) and info['faster_whisper'] and os.path.realpath(sys.prefix) == os.path.realpath(C.VENV))
  print(json.dumps(info, indent=1)); return 0 if info['ok'] else 1

WORK_RETENTION_DAYS = 7
def prune_workdirs(root, keep=None, days=WORK_RETENTION_DAYS):
  """Retention: video workdirs untouched for more than `days` are removed (caches under cache/ are kept, so a rerun
  reuses media and transcripts). Busy workdirs are skipped (their lock is held)."""
  import fcntl
  if not os.path.isdir(root): return
  for d in os.listdir(root):
    p = os.path.join(root, d)
    if p == keep or not os.path.isdir(p) or time.time() - os.path.getmtime(p) < days * 86400: continue
    lf = os.path.join(BASE, 'locks', C.sha256_text(p)[:24] + '.lock')
    try:
      fd = os.open(lf, os.O_RDWR | os.O_CREAT, 0o644); fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
      shutil.rmtree(p, ignore_errors=True); os.close(fd)
    except (BlockingIOError, OSError): pass

def load_job(a):
  if not a.job: return a
  j = json.load(open(a.job, encoding='utf-8'))
  for k, v in j.items():
    k2 = k.replace('-', '_')
    if getattr(a, k2, None) in (None, False, '', 0): setattr(a, k2, v)
  return a

def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument('url', nargs='?'); ap.add_argument('--job'); ap.add_argument('--version', action='store_true'); ap.add_argument('--doctor', action='store_true')
  ap.add_argument('--title'); ap.add_argument('--author')
  ap.add_argument('--date'); ap.add_argument('--publisher'); ap.add_argument('--post-text', default='')
  ap.add_argument('--lang', default=None, help='preferred language (default: the video metadata language)')
  ap.add_argument('--model', default=None); ap.add_argument('--frames', type=int, default=0)
  ap.add_argument('--workdir'); ap.add_argument('--out'); ap.add_argument('--min-units', type=int, default=0)
  ap.add_argument('--min-words', type=int, default=0, help='DEPRECATED alias of --min-units')
  ap.add_argument('--no-captions', action='store_true'); ap.add_argument('--force', action='store_true')
  ap.add_argument('--keep-work', action='store_true', help='keep the workdir after a complete build')
  a = load_job(ap.parse_args(argv))
  if a.version: print('video2epub', C.VERSION); return 0
  if a.doctor: return doctor()
  a.model = a.model or 'small'
  try: url = C.check_url(a.url)
  except ValueError as e: log('ERROR:', e); return 2
  if not 0 <= a.frames <= 3: log('ERROR: --frames must be 0..3'); return 2
  source_id = C.normalize_source(url); skey = C.source_key(url)
  meta = json.loads(run(['yt-dlp', '-J', '--', url], capture_output=True, text=True).stdout)
  if not re.match(r'^(x|youtube):', source_id):
    # Extractor ids are not globally unique (the generic extractor uses file basenames), so other sites are identified
    # by the normalized page URL (yt-dlp's webpage_url when it gives one) plus the extractor and its id.
    page = C.normalize_source(meta.get('webpage_url') or url)
    source_id = f"{(meta.get('extractor_key') or 'generic').lower()}:{meta.get('id') or ''}@{page}"; skey = C.sha256_text(source_id)[:16]
  dur = meta.get('duration')
  title = noemoji(a.title or f"{meta.get('title') or 'Video'} — Transcript")
  author = noemoji(a.author or meta.get('uploader') or meta.get('channel') or 'Unknown')
  ud = meta.get('upload_date')
  date = a.date or (f'{ud[:4]}-{ud[4:6]}-{ud[6:]}' if ud else time.strftime('%Y-%m-%d'))
  publisher = a.publisher or meta.get('extractor_key', '')
  opts = {'lang': a.lang, 'model': a.model, 'no_captions': bool(a.no_captions), 'tool': TOOL_HASH}
  optkey = C.key_of(source_id, opts)[:16]
  cache = os.path.join(BASE, 'cache', 'video', skey)
  wd = os.path.abspath(a.workdir or os.path.join(BASE, 'work', 'video', f'{slugify(title)[:48]}-{skey[:10]}-{optkey[:8]}'))
  prune_workdirs(os.path.join(BASE, 'work', 'video'), keep=wd)
  os.makedirs(os.path.join(wd, 'img'), exist_ok=True)
  import fcntl
  os.makedirs(os.path.join(BASE, 'locks'), exist_ok=True)
  lfd = os.open(os.path.join(BASE, 'locks', C.sha256_text(wd)[:24] + '.lock'), os.O_RDWR | os.O_CREAT, 0o644); fcntl.flock(lfd, fcntl.LOCK_EX)
  wmeta = os.path.join(wd, 'workdir.json')
  if os.path.exists(wmeta):
    wm = json.load(open(wmeta))
    if wm.get('source_id') != source_id or wm.get('optkey') != optkey:
      log(f'ERROR: workdir {wd} belongs to another source/options ({wm.get("source_id")}); refusing to reuse'); return 2
  else: C.write_json(wmeta, {'source_id': source_id, 'url': url, 'optkey': optkey, 'opts': opts})
  tcache = os.path.join(cache, f'transcript-{optkey}.json'); os.makedirs(cache, exist_ok=True)
  segs = None; fallback = False
  if os.path.exists(tcache):
    try:
      c = json.load(open(tcache))
      if c.get('source_id') == source_id and c.get('opts') == opts and c.get('tool') == TOOL_HASH:
        segs, method, lang, fallback = c['segs'], c['method'], c['lang'], c.get('lang_fallback', False)
      else: log('cache rejected for transcript: source/options/tool version mismatch')
    except Exception: log('cache rejected for transcript: unreadable')
  if segs is None:
    method = lang = None
    if not a.no_captions: segs, method, lang, fallback = get_captions(url, wd, a.lang, meta)
    if not segs: segs, method, lang = whisper(url, source_id, cache, a.model, a.lang); fallback = bool(a.lang and C.lang_base(lang) != C.lang_base(a.lang))
    C.write_json(tcache, {'source_id': source_id, 'url': url, 'opts': opts, 'tool': TOOL_HASH, 'segs': segs, 'method': method, 'lang': lang, 'lang_fallback': fallback})
  if not dur and segs: dur = segs[-1][0]
  units = C.count_units(' '.join(s for _, s in segs))
  need = a.min_units or a.min_words or C.min_units_for(units)
  log(f'method={method} lang={lang} units={units} threshold={need} duration={dur}')
  if units['units'] < need:
    print(json.dumps({'status': C.status_stages(), 'error': 'too little speech', 'units': units, 'threshold': need, 'method': method, 'lang': lang}, ensure_ascii=False))
    log('Too little speech; no EPUB written.'); return 3
  out = os.path.abspath(a.out or os.path.join(BASE, f'{slugify(title, source_id)}.epub'))
  if not out.endswith('.epub') or out.endswith('.needs-review.epub'): log('ERROR: --out must end in .epub'); return 2
  try: ofd = C.lock_path(out)  # per OUTPUT PATH: two jobs (any workdir) writing the same book serialize here
  except TimeoutError as e: log('ERROR:', e); return 2
  job_id = C.key_of('video', source_id, opts, a.frames, title, author, lang, date, segs, C.VERSION, C.build_env())[:24]
  for cand in (out, C.review_name(out)):
    if not os.path.exists(cand): continue
    try: prev = json.load(open(cand + '.job.json'))
    except Exception: prev = {}
    if prev.get('job_id') == job_id and not C.check_binding(cand, prev, cand + '.manifest.json') and not a.force:
      print(json.dumps(dict(prev.get('summary', {}), reused=True), ensure_ascii=False)); return 0 if cand == out else 5
  if os.path.exists(out) and not a.force:
    log(f'ERROR: output exists from a different job or input: {out} (choose a new --out or pass --force)'); return 2
  frames_html = []; fails = []; omissions = []; inherent = ['video visuals not included (transcript text only)']
  if a.frames and dur:
    try:
      video = media('video', url, source_id, cache, 'worstvideo[height>=360]/best[height<=480]/worst')
      for i in range(a.frames):
        t = dur * (i + 1) / (a.frames + 1); fn = f'img/frame{i+1}.jpg'
        run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(t), '-i', video, '-frames:v', '1', '-q:v', '4', '-vf', 'scale=960:-2', os.path.join(wd, fn)])
        frames_html.append((t, fn))
    except Exception as e: fails.append(f'frames not included: {e}')
  body = []; fr = list(frames_html)
  for t, p in paragraphs(segs):
    while fr and t is not None and t >= fr[0][0]:
      ft, fn = fr.pop(0); body.append(f'<p class="frame"><img src="{fn}" alt="Frame at {ts(ft)}"/></p>')
    stamp = f'<span class="ts">[{ts(t)}]</span> ' if t is not None else ''
    body.append(f'<p>{stamp}{html.escape(p)}</p>')
  for ft, fn in fr: body.append(f'<p class="frame"><img src="{fn}" alt="Frame at {ts(ft)}"/></p>')
  hdr = [f'<h1>{html.escape(title)}</h1><div class="header">', f'<p>{html.escape(author)} · {html.escape(date)}</p>']
  if a.post_text: hdr.append(f'<p><strong>Post:</strong> {html.escape(a.post_text)}</p>')
  hdr.append(f'<p><strong>Video length:</strong> {ts(dur) if dur else "unknown"}</p>')
  hdr.append(f'<p><strong>Transcript method:</strong> {html.escape(str(method))}; language: {html.escape(str(lang))}'
             + (' (fallback: preferred language not available)' if fallback else '') + '. Speech-to-text output, lightly paragraphed; may contain recognition errors.</p>')
  hdr.append(f'<p><strong>Source:</strong> <a href="{html.escape(url, quote=True)}">{html.escape(url)}</a></p></div><hr/>')
  doc = f'<html><head><meta charset="utf-8"/><title>{html.escape(title)}</title></head><body>{"".join(hdr)}<h2>Transcript</h2>{chr(10).join(body)}</body></html>'
  open(os.path.join(wd, 'transcript.html'), 'w', encoding='utf-8').write(doc)
  open(os.path.join(wd, 'epub-meta.xml'), 'w', encoding='utf-8').write(
    f'<dc:identifier id="BookId">urn:kindle-courier:job:{job_id}</dc:identifier>\n<dc:source>{html.escape(url)}</dc:source>\n'
    f'<dc:publisher>{html.escape(publisher)}</dc:publisher>\n')
  open(os.path.join(wd, 'style.css'), 'w').write(
    'body{font-family:serif;line-height:1.45;margin:0 .5em}p{margin:.6em 0;text-align:left}'
    '.header p{font-size:.9em;margin:.3em 0}.ts{font-family:sans-serif;font-size:.75em;color:#555}'
    'h1,h2{font-family:sans-serif}img{max-width:100%;height:auto;display:block;margin:.8em auto}a{color:inherit}')
  os.makedirs(os.path.dirname(out), exist_ok=True)
  tmp_out = out + f'.tmp-{os.getpid()}.epub'
  try:
    run([C.pandoc_bin(), 'transcript.html', '-f', 'html', '-t', 'epub3', '--epub-title-page=false', '--epub-metadata=epub-meta.xml',
         '-M', f'title={title}', '-M', f'author={author}', '-M', f'date={date}', '-M', f'lang={lang or "en"}', '--css', 'style.css', '-o', tmp_out], cwd=wd)
    cnt, msgs = C.run_epubcheck(tmp_out, os.path.join(wd, 'epubcheck.json'))
    if cnt is None or cnt['fatal'] or cnt['error']:
      os.replace(tmp_out, out + '.broken'); log('EPUBCHECK FAILED or could not run:', msgs if cnt is None else [m.get('message') for m in msgs if m.get('severity') in ('FATAL', 'ERROR')][:10]); return 4
    m = C.epub_meta(tmp_out)
    bad = [k for k, ok in (('title', m['title'] == title), ('creator', m['creator'] == author), ('source', m['source'] == url),
                           ('job', f'urn:kindle-courier:job:{job_id}' in m['identifiers'])) if not ok]
    if bad: os.replace(tmp_out, out + '.broken'); log('ERROR: metadata mismatch:', bad); return 4
    review = (['captions are in a fallback language'] if fallback else [])
    status = 'incomplete' if fails else 'needs_review' if review else 'complete'
    manifest = {'tool': 'video2epub', 'version': C.VERSION, 'job_id': job_id, 'source_id': source_id, 'method': method, 'lang': lang,
                'lang_fallback': fallback, 'units': units, 'threshold': need,
                'frames': {'expected': a.frames if dur else 0, 'included': len(frames_html)},
                'failures': fails, 'omissions': omissions, 'inherent_limits': inherent, 'review_reasons': review + (['frames missing'] if fails else []),
                'review_needed': bool(review or fails),
                'complete': status == 'complete', 'status': status, 'cache': cache, 'workdir': wd}
    final = out if status == 'complete' else C.review_name(out)
    summary = {'epub': final, 'bytes': os.path.getsize(tmp_out), 'title': title, 'method': method, 'lang': lang, 'units': units,
               'duration_s': dur, 'epubcheck': cnt, 'manifest_status': status, 'complete': status == 'complete',
               'failures': fails, 'omissions': omissions, 'inherent_limits': inherent, 'status': C.status_stages(True, True), 'job_id': job_id, 'version': C.VERSION}
    job = {'job_id': job_id, 'tool': 'video2epub', 'version': C.VERSION, 'source_url': url, 'source_id': source_id, 'title': title,
           'author': author, 'lang': lang, 'date': date, 'format': 'epub', 'options': dict(opts, frames=a.frames),
           'build_env': C.build_env(), 'summary': summary}
    C.commit_book(tmp_out, final, job, manifest)
    for stale in [out + '.broken'] + ([C.review_name(out) + x for x in ('', '.job.json', '.manifest.json')] if final == out else []):
      if os.path.exists(stale): os.remove(stale)
    if status == 'complete' and not a.keep_work: shutil.rmtree(wd, ignore_errors=True)  # transcripts stay in cache/
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if status == 'complete' else 5
  finally:
    if os.path.exists(tmp_out): os.remove(tmp_out)

if __name__ == '__main__':
  sys.exit(main())
````

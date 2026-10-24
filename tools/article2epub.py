#!/usr/bin/env python3
"""article2epub (Kindle Courier): web article / X Article / saved or self-built HTML / X JSON / prose PDF -> checked EPUB.
Prefer --job FILE.json (values never pass through a shell). Run ensure_tools.sh first.
Outputs next to --out: <out>.job.json (job metadata, sha256, content digest) and <out>.manifest.json
(expected vs included sections/posts/images, failures, omissions, OCR, complete flag).
Exit: 0 built+validated+complete; 2 input/fetch/refused; 3 epubcheck errors or could not run (.broken, nothing at --out);
4 metadata mismatch (.broken); 5 built+validated but incomplete or needs review (presend_gate blocks it)."""
import argparse, io, json, os, re, shutil, subprocess, sys, tempfile, zipfile, html as H
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import courier_common as C
if __name__ == '__main__':
  if '--version' in sys.argv: print('article2epub', C.VERSION); sys.exit(0)
  C.ensure_venv()
try: from bs4 import BeautifulSoup, Comment
except ImportError: sys.exit('missing python libs: run ensure_tools.sh')
BASE = C.BASE
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36'
CSS = """body{font-family:serif;line-height:1.45;margin:0 .5em}
h1,h2,h3,h4{font-family:sans-serif;line-height:1.25;page-break-after:avoid}h3{font-size:1.15em;margin-top:1.4em}
p{margin:.6em 0;text-align:left}div.byline p{font-size:.9em;color:#333}div.source p{font-size:.85em;word-break:break-all}
img{max-width:100%;height:auto;display:block;margin:.8em auto}a{color:inherit}
pre{font-family:monospace;font-size:.75em;line-height:1.3;white-space:pre-wrap;word-wrap:break-word;border:1px solid #888;padding:.5em;margin:1em 0}
code{font-family:monospace}table{border-collapse:collapse;margin:1em 0;font-size:.85em}td,th{border:1px solid #888;padding:.2em .4em}
blockquote{border-left:3px solid #555;margin:1em .5em;padding-left:.7em}p.caption,figcaption{text-align:center;font-size:.85em;font-style:italic}
div.ocr{border:1px dashed #888;padding:.3em .6em;margin:.5em 0 1em;font-size:.85em}div.ocr p{margin:.3em 0}"""
EMOJI = re.compile('[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U0001F1E6-\U0001F1FF'
         '\U000E0000-\U000E007F\uFE0E\uFE0F\u200D\u20E3\u2300-\u23FF]')
def noemoji(s): return re.sub(r'\s+', ' ', EMOJI.sub('', s or '')).strip().strip('|·').strip()  # a leading '-' is kept
def log(*a): print(*a, file=sys.stderr)
class Fail(Exception):
  def __init__(self, msg, code=2): super().__init__(msg); self.code = code
def die(msg, code=2): raise Fail(msg, code)
def is_x(u): return C.normalize_source(u).startswith('x:')  # exact host match (x.com / twitter.com)

def browser_html(url, wait_sel=None):
  from playwright.sync_api import sync_playwright
  exe = next((p for p in [os.environ.get('CHROME_PATH'), '/usr/bin/google-chrome', '/usr/bin/chromium'] if p and os.path.exists(p)), None)
  with sync_playwright() as p:
    b = p.chromium.launch(executable_path=exe, args=['--no-sandbox'])
    pg = b.new_page(viewport={'width': 1000, 'height': 1400}, user_agent=UA)
    pg.goto(url, wait_until='domcontentloaded', timeout=60000)
    if wait_sel: pg.wait_for_selector(wait_sel, timeout=45000)
    else: pg.wait_for_timeout(4000)
    h = pg.evaluate('document.body.scrollHeight')
    for y in range(0, h, 600): pg.evaluate(f'window.scrollTo(0,{y})'); pg.wait_for_timeout(150)
    pg.wait_for_timeout(2500); out = pg.content(); b.close(); return out

def http_get(url, binary=False):
  """SSRF-guarded GET (C.safe_fetch: per-hop validation, pinned IP, size cap)."""
  data, final, ctype = C.safe_fetch(url)
  if binary: return data
  m = re.search(r'charset=([\w-]+)', ctype); return data.decode(m.group(1) if m else 'utf-8', 'replace')

def x_article(page):
  """X Article -> (body html, cover url, embedded post count)."""
  s = BeautifulSoup(page, 'lxml'); body = s.select_one('.x-article-body')
  if not body: return None, None, 0
  cov = s.find('img', alt=re.compile('cover image', re.I)); out = []; posts = 0
  for c in body.children:
    if not getattr(c, 'name', None): continue
    cls = c.get('class') or []
    if 'x-article-code' in cls:
      pre = c.find('pre'); out.append('<pre><code>' + H.escape(pre.get_text().rstrip('\n')) + '</code></pre>'); continue
    if 'contents' in cls: out += [str(x) for x in c.children if getattr(x, 'name', None)]; continue
    imgs = [i for i in c.find_all('img') if 'pbs.twimg.com/media' in i.get('src', '')]
    link = next(('https://x.com' + a['href'] for a in c.find_all('a', href=True) if re.match(r'^/\w+/status/\d+$', a['href'])), '')
    if c.find('article') or (link and not imgs):  # embedded post card -> preview
      posts += 1
      bits = [t for t in c.get_text('\x01', strip=True).split('\x01') if t != 'Show more' and not re.fullmatch(r'[\d.,]+[KMB]?|/?\s*\d{1,2}:\d{2}', t)]
      out.append('<blockquote class="kc-embedded"><p><b>Embedded post (preview)</b> — ' + H.escape(' · '.join(bits[:3])) + '</p>' +
           ''.join('<p>' + H.escape(t) + '</p>' for t in bits[3:]) + (f'<p><a href="{link}">{link}</a></p>' if link else '') + '</blockquote>')
    else: out.append(str(c))
  return '\n'.join(out), (cov['src'] if cov else None), posts

def json_article(d):
  """X JSON fallback (plain_text + entities.code): text and code only, never images."""
  txt = d.get('plain_text') or ''; codes = [c.get('code', '') for c in (d.get('entities') or {}).get('code', [])]
  out = []
  for para in re.split(r'\n+', txt):
    hit = next((c for c in codes if c and para.strip() and para.strip() in c), None)
    if hit:
      if not out or out[-1] != hit: out.append(hit)
    elif para.strip(): out.append(para)
  return '\n'.join('<pre><code>' + H.escape(o) + '</code></pre>' if o in codes else '<p>' + H.escape(o) + '</p>' for o in out)

def generic(page, url):
  """Readability extraction; math is swapped for tokens first (readability drops it), then restored."""
  s = BeautifulSoup(page, 'lxml'); og = s.find('meta', property='og:image') or s.find('meta', attrs={'name': 'twitter:image'})
  for sc in s.find_all('script', type=re.compile('math/tex')):
    disp = 'display' in sc.get('type', ''); m = s.new_tag('span', attrs={'class': 'math ' + ('display' if disp else 'inline')})
    m.string = ('\\[' if disp else '\\(') + sc.get_text() + ('\\]' if disp else '\\)'); sc.replace_with(m)
  for k in s.select('.katex-html, .MathJax_Preview, mjx-assistive-mml, img[class*=math-fallback]'): k.decompose()
  maths = []
  for m in s.select('math, span.math'):
    if m.parent is None or m.find_parent('math'): continue
    tgt = m
    for par in list(m.parents)[:3]:
      if par.name in ('span', 'div') and re.search(r'math|katex', ' '.join(par.get('class') or []), re.I): tgt = par
    maths.append(str(m)); tgt.replace_with(f'qqMATH{len(maths) - 1}qq')
  from readability import Document
  out = Document(str(s), url=url).summary(html_partial=True)
  out = re.sub(r'qqMATH(\d+)qq', lambda g: maths[int(g.group(1))], out)
  return out, (urljoin(url, og['content']) if og and og.get('content') else None)

def trusted_body(page):
  """Self-built HTML (threads, PDF text): use the body as is, no readability."""
  s = BeautifulSoup(page, 'lxml'); return (s.body or s).decode_contents()

CELL = ['tr', 'td', 'th', 'tbody', 'thead', 'tfoot']
KEEP = {'a': ['href'], 'img': ['src', 'alt'], 'ol': ['start'], 'li': ['value'], 'td': ['colspan', 'rowspan'], 'th': ['colspan', 'rowspan'],
        'math': ['display', 'xmlns'], 'blockquote': ['class'], 'div': ['class']}
JUNK = re.compile(r'(^|[-_ ])(comment|share|social|related|newsletter|subscribe|advert|promo|sponsor|cookie|popup|sidebar|footer|nav)s?($|[-_ ])', re.I)

class Fetcher:
  """Image fetching: http(s) through the SSRF guard; local files only from an explicit allow-list of exact files
  (images the saved HTML references inside its own folder, or the --cover file)."""
  def __init__(self, files=()): self.files = {os.path.realpath(f) for f in files if f}
  def get(self, url):
    if re.match('https?://', url): return http_get(url, binary=True)
    if url.startswith('kc-outside:'): raise ValueError('local path outside the HTML file folder (refused)')
    if url.startswith('kc-missing:'): raise ValueError('local file referenced by the HTML is missing (not fetched from the network)')
    p = os.path.realpath(url[7:] if url.startswith('file://') else url)
    if p not in self.files: raise ValueError('local path not referenced by the input (refused)')
    return open(p, 'rb').read()

def localize(page, html_dir):
  """Before extraction, point relative image refs of a saved HTML file at the files next to it (file://), only inside
  its folder (no ../ escape). Missing local refs become kc-missing: so they are reported, never fetched from the web."""
  allowed = set(); root = os.path.realpath(html_dir)
  def sub(m):
    attr, q, src = m.group(1), m.group(2), m.group(3)
    if re.match(r'^(?:[a-z][a-z0-9+.-]*:|//)', src, re.I): return m.group(0)
    if src.startswith('/'): return f'{attr}={q}kc-outside:{src}{q}'
    p = os.path.realpath(os.path.join(root, H.unescape(src).split('#')[0].split('?')[0]))
    if not p.startswith(root + os.sep): return f'{attr}={q}kc-outside:{src}{q}'
    if os.path.isfile(p): allowed.add(p); return f'{attr}={q}file://{p}{q}'
    return f'{attr}={q}kc-missing:{src}{q}'
  page = re.sub(r"""\b(src|data-src)=(["'])([^"']+)\2""", sub, page)
  return page, allowed

def decorative(w, h, el=None):
  """Explicit decorative classification (recorded in the manifest): tiny spacers/icons only."""
  if el is not None and (el.get('aria-hidden') == 'true' or el.get('role') == 'presentation'): return True, 'marked aria-hidden/presentation'
  if w and h and (w * h < 1500 or (w <= 32 and h <= 32)): return True, f'icon/spacer size {w}x{h}'
  return False, ''

def fetch_img(fetcher, url, wd, stem, is_cover=False):
  """URL or allowed local file -> Kindle-safe JPEG/PNG in wd. Returns (relpath|None, reason, (w,h))."""
  if 'pbs.twimg.com/media' in url: url = re.sub(r'\?.*', '', url) + '?format=jpg&name=large'
  try:
    data = fetcher.get(url)
    from PIL import Image
    im = Image.open(io.BytesIO(data)); size = im.size
    if not is_cover and (im.width < 80 or im.height < 50): return None, f'too small ({im.width}x{im.height})', size
    png = im.mode in ('RGBA', 'LA', 'P') and im.format == 'PNG'
    fn = stem + ('.png' if png else '.jpg'); im = im if png else im.convert('RGB')
    if max(im.size) > 1600: im.thumbnail((1600, 1600))
    im.save(os.path.join(wd, fn), quality=85); return fn, 'embedded', size
  except Exception as e: return None, f'fetch/decode failed: {e}', None

def clean(frag, base_url, wd, fetcher, title, rep):
  s = BeautifulSoup(frag, 'lxml'); root = s.body or s
  for c in root.find_all(string=lambda t: isinstance(t, Comment)): c.extract()
  for t in root.find_all('svg'):
    dims = [int(re.match(r'^\d+', str(t.get(k))).group()) if re.match(r'^\d+', str(t.get(k, ''))) else 0 for k in ('width', 'height')]
    dec, why = decorative(dims[0], dims[1], t) if t.find('text') is None else (False, '')
    rep['images'].append({'src': 'inline <svg>', 'status': 'dropped', 'classification': 'decorative' if dec else 'content',
                          'reason': why or 'inline SVG is not supported on Kindle'})
    t.decompose()
  for t in root.find_all(['video', 'audio', 'iframe']):
    rep['omissions'].append(f"{t.name} not included (cannot be shown on Kindle): {t.get('src') or t.get('data-src') or ''}"); t.decompose()
  for t in root.find_all(['script', 'style', 'nav', 'aside', 'footer', 'form', 'button', 'noscript', 'input', 'map']): t.decompose()
  for tb in root.find_all('table'):
    if tb.parent is None: continue
    cells = [c for c in tb.find_all(['td', 'th']) if c.find_parent('table') is tb]
    if tb.find('table') or len(cells) < 2 or (not tb.find('th') and max(len(c.get_text()) for c in cells) > 400):
      for x in [x for x in tb.find_all(CELL) if x.find_parent('table') is tb]: x.unwrap()
      tb.unwrap()
  for x in root.find_all(CELL):
    if x.find_parent('table') is None: x.unwrap()
  for t in root.find_all(True):
    if t.attrs is not None and JUNK.search(' '.join(t.get('class') or []) + ' ' + (t.get('id') or '')) and t.name not in ('body', 'html', 'pre', 'code', 'math'): t.decompose()
  for t in root.find_all(['span', 'font', 'div', 'section', 'article', 'header', 'main', 'center', 'picture', 'source']):
    if t.name == 'span' and 'math' in (t.get('class') or []): continue
    if t.name == 'source': t.decompose()
    else: t.unwrap()
  for t in root.find_all(['b', 'i']): t.name = {'b': 'strong', 'i': 'em'}[t.name]
  for a in root.find_all('a', attrs={'name': True}): a['id'] = a['name']
  for a in root.find_all('a', href=True):
    if a['href'].startswith(base_url.split('#')[0] + '#'): a['href'] = '#' + a['href'].split('#', 1)[1]
  for m in root.find_all('math'):
    for i in m.parent.find_all('img'): i.decompose()
  n = 0; os.makedirs(os.path.join(wd, 'img'), exist_ok=True)
  for img in root.find_all('img'):
    src = img.get('data-src') or img.get('src') or ''
    if not src and img.get('srcset'): src = img['srcset'].split(',')[-1].split()[0]
    if not src: img.decompose(); continue
    if src.startswith('data:'):
      rep['images'].append({'src': src[:40] + '…', 'status': 'dropped', 'classification': 'content', 'reason': 'inline data: image not supported'}); img.decompose(); continue
    full = src if re.match(r'^(https?|file|kc-missing|kc-outside):', src) else urljoin(base_url, src) if re.match('https?://', base_url) else 'kc-missing:' + src
    fn, why, size = fetch_img(fetcher, full, wd, f'img/fig{n + 1:02d}')
    if fn:
      n += 1; img['src'] = fn; rep['images'].append({'src': full, 'status': 'embedded', 'file': fn})
    elif why.startswith('too small'):
      dec, dwhy = decorative(size[0], size[1], img)
      rep['images'].append({'src': full, 'status': 'dropped', 'classification': 'decorative' if dec else 'content', 'reason': dwhy or why})
      img.decompose()
    else:
      rep['images'].append({'src': full, 'status': 'failed', 'reason': why}); rep['failures'].append(f'image not included: {full} ({why})'); img.decompose()
  for t in [root] + root.find_all(True):
    if t.name == 'span' and 'math' in (t.get('class') or []): continue
    t.attrs = {k: v for k, v in t.attrs.items() if k in KEEP.get(t.name, []) or k == 'id'}
    if t.name == 'a' and t.get('href') and not t['href'].startswith('#'): t['href'] = urljoin(base_url, t['href'])
  regroup(s, root)
  for p in root.find_all(['p', 'li', 'h2', 'h3', 'h4', 'strong', 'em']):
    if not p.get_text(strip=True) and not p.find(['img', 'math']): p.decompose()
  # the title is printed once by the builder: drop a leading source heading that repeats it
  heads = [h for h in root.find_all(['h1', 'h2', 'h3'])][:1]
  for h in heads:
    before = [x for x in h.find_all_previous(['p', 'pre', 'blockquote', 'ul', 'ol', 'img']) if root in x.parents]
    if not before and C.norm_key(h.get_text()) == C.norm_key(title): rep['dropped_title_heading'] = True; h.decompose()
  for h in root.find_all('h1'): h.name = 'h2'
  seen = set()
  for t in root.find_all(id=True):
    if t['id'] in seen: del t['id']
    else: seen.add(t['id'])
  used = set()
  for a in root.find_all('a', href=re.compile('^#')):
    if a['href'][1:] in seen: used.add(a['href'][1:])
    else: del a['href']
  for t in root.find_all(id=True):
    if t['id'] not in used: del t['id']
    elif t.name not in ('a', 'span', 'div', 'h2', 'h3', 'h4', 'h5', 'h6', 'table'):
      sp = s.new_tag('span', attrs={'id': t['id']}); del t['id']; t.insert(0, sp)
  return s, root, n

BLOCK = {'p', 'pre', 'table', 'ul', 'ol', 'dl', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'figure', 'img', 'math', 'div'}
def regroup(s, el):
  """<br><br>-separated text (old pages) -> <p> paragraphs."""
  for c in [c for c in el.find_all(['blockquote', 'li', 'td']) if c.find('br')]: regroup(s, c) if c is not el else None
  kids = list(el.contents)
  if el.name in ('li', 'td') and not any(getattr(k, 'name', '') == 'br' for k in kids): return
  out, cur = [], []
  def flush():
    if any((getattr(k, 'name', None) or str(k).strip()) for k in cur):
      p = s.new_tag('p')
      while cur and getattr(cur[-1], 'name', '') == 'br': cur.pop()
      for k in cur: p.append(k)
      out.append(p)
    cur.clear()
  for i, k in enumerate(kids):
    k.extract()
    nxt = next((x for x in kids[i + 1:] if getattr(x, 'name', None) or str(x).strip()), None)
    if getattr(k, 'name', '') == 'br' and (getattr(nxt, 'name', '') == 'br' or (cur and getattr(cur[-1], 'name', '') == 'br')):
      if cur and getattr(cur[-1], 'name', '') == 'br': cur.pop()
      flush() if getattr(nxt, 'name', '') != 'br' else cur.append(k)
    elif getattr(k, 'name', '') in BLOCK: flush(); out.append(k)
    else: cur.append(k)
  flush()
  for k in out: el.append(k)

def add_ocr(s, root, wd, lang, rep):
  """OCR each embedded image; text-heavy ones get a labelled machine-transcribed block after the image."""
  imgs = root.find_all('img')
  if not imgs: return
  if not C.ocr_available(lang):
    rep['ocr'] = 'unavailable'; rep['review'].append(f'{len(imgs)} image(s) not OCR-checked (OCR unavailable)'); return
  rep['ocr'] = 'ran'
  for img in imgs:
    st, txt = C.ocr_image(os.path.join(wd, img['src']), lang)
    rec = next((r for r in rep['images'] if r.get('file') == img['src']), None)
    if rec is not None: rec['ocr'] = st
    if st == 'text':
      blk = BeautifulSoup(C.ocr_block_html(txt), 'lxml').div
      anchor = img
      while anchor.parent is not None and anchor.parent is not root: anchor = anchor.parent
      anchor.insert_after(blk)
    elif st == 'error': rep['review'].append(f"OCR failed on {img['src']}: {txt[:120]}")

def text_cover(title, author, path, header=None):
  """Portrait 1200x1800 cover. Wraps per character inside CJK runs and breaks over-long words, so no line is cut off."""
  from PIL import Image, ImageDraw, ImageFont
  im = Image.new('RGB', (1200, 1800), 'white'); d = ImageDraw.Draw(im); y = 300
  if header:
    h = Image.open(header).convert('RGB'); h = h.resize((1200, round(h.height * 1200 / h.width)))
    im.paste(h.crop((0, 0, 1200, min(h.height, 1000))), (0, 0)); y = min(h.height, 1000) + 120
  def font(sz):
    for f in ['/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc', '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf']:
      if os.path.exists(f): return ImageFont.truetype(f, sz)
    return ImageFont.load_default()
  def wrap(text, f, width=1000):
    toks = re.findall(r'[\u3000-\u30ff\u3400-\u9fff\uf900-\ufaff\uff00-\uffef]|[^\s\u3000-\u30ff\u3400-\u9fff\uf900-\ufaff\uff00-\uffef]+|\s+', text)
    lines, line = [], ''
    for t in toks:
      cand = line + t
      if d.textlength(cand.strip(), font=f) <= width: line = cand; continue
      if line.strip(): lines.append(line.strip()); line = t.lstrip()
      while d.textlength(line, font=f) > width:  # a single over-long token: hard-break it
        k = len(line)
        while k > 1 and d.textlength(line[:k], font=f) > width: k -= 1
        lines.append(line[:k]); line = line[k:]
    if line.strip(): lines.append(line.strip())
    return lines
  f = font(84 if len(title) < 60 else 68)
  for ln in wrap(title, f)[:9]: d.text((100, y), ln, fill='black', font=f); y += 115
  fa = font(56)
  for ln in wrap(author, fa)[:2]: d.text((100, y + 80), ln, fill='#333', font=fa); y += 70
  im.save(path, quality=90)

def raw_inventory(page, kind, jsonfile, trusted):
  """Content counted from the raw source DOM before extraction (article/main/X body scope)."""
  if jsonfile: return {'blocks': [], 'images': 0, 'embeds': []}
  s = BeautifulSoup(page or '', 'lxml')
  scope = s.select_one('.x-article-body') if kind == 'x' else None
  if scope is None and not trusted: scope = s.find('article') or s.find('main')
  scope = scope or s.body or s
  for t in scope.find_all(['script', 'style', 'noscript', 'nav', 'footer']): t.decompose()
  blocks = [C.norm_text(b.get_text(' ')) for b in scope.find_all(['p', 'li', 'pre', 'blockquote', 'h2', 'h3', 'h4'])
            if not b.find(['p', 'li', 'pre', 'blockquote']) and len(C.norm_text(b.get_text(' '))) >= 40]
  embeds = [f"{t.name} {t.get('src') or t.get('data') or ''}".strip() for t in scope.find_all(['iframe', 'video', 'audio', 'embed', 'object'])]
  return {'blocks': blocks, 'images': len(scope.find_all('img')) + len(scope.find_all('svg')), 'embeds': embeds}

def para_keys(html_frag):
  s = BeautifulSoup(html_frag, 'lxml')
  return [C.norm_text(p.get_text(' ')) for p in s.find_all(['p', 'li', 'pre', 'h2', 'h3', 'h4']) if len(C.norm_text(p.get_text(' '))) >= 12]

BOOL = ('no_cover', 'browser', 'trusted_html', 'force', 'force_reflow', 'keep_work')
INT = ('expect_posts', 'expect_images')
def load_job(a):
  """Job file values fill unset options; types are validated (a string forbid becomes a one-item list)."""
  if not a.job: return a
  j = json.load(open(a.job, encoding='utf-8'))
  if not isinstance(j, dict): die('job file must be a JSON object')
  for k, v in j.items():
    k2 = k.replace('-', '_')
    if k2 == 'forbid': v = [v] if isinstance(v, str) else v
    if k2 == 'forbid' and not (isinstance(v, list) and all(isinstance(x, str) for x in v)): die('job forbid must be a string or list of strings')
    elif k2 in BOOL and not isinstance(v, bool): die(f'job {k} must be true/false')
    elif k2 in INT and not (isinstance(v, int) and not isinstance(v, bool)): die(f'job {k} must be an integer')
    elif k2 not in BOOL + INT + ('forbid',) and v is not None and not isinstance(v, str): die(f'job {k} must be a string')
    if not hasattr(a, k2): die(f'unknown job key {k}')
    if getattr(a, k2, None) in (None, False, [], 0): setattr(a, k2, v)
  return a

def lock_output(out):
  try: return C.lock_path(out)
  except TimeoutError as e: die(str(e))

review_name = C.review_name

def crash_point(name):
  if os.environ.get('KC_TEST_CRASH') == name: os._exit(9)  # crash-injection hook used by the tests

def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument('--version', action='store_true')
  ap.add_argument('--job', help='JSON job file with the same keys as the options (preferred: no shell quoting of titles)')
  ap.add_argument('--url'); ap.add_argument('--html', help='saved or self-built HTML file')
  ap.add_argument('--json', help='X-article JSON (title/plain_text/entities); alone, or with --url as fallback')
  ap.add_argument('--from-pdf', help='prose PDF to reflow; layout-heavy PDFs are refused (send the PDF as is)')
  ap.add_argument('--force-reflow', action='store_true', help='reflow a PDF classified layout-heavy (owner asked)')
  for k in ('title', 'author', 'date', 'source_url', 'lang', 'out'): ap.add_argument('--' + k.replace('_', '-'))
  ap.add_argument('--cover'); ap.add_argument('--no-cover', action='store_true'); ap.add_argument('--browser', action='store_true')
  ap.add_argument('--trusted-html', action='store_true', help='--html is self-built (thread/PDF text): skip readability')
  ap.add_argument('--expect-posts', type=int, default=0, help='posts the HTML should contain (elements with class kc-post)')
  ap.add_argument('--expect-images', type=int, default=0)
  ap.add_argument('--ocr', choices=['auto', 'off'], default='auto')
  ap.add_argument('--force', action='store_true', help='replace an existing --out built from a different job')
  ap.add_argument('--forbid', action='append', default=[], help='DEPRECATED: checked only against title/author/byline, word-bounded')
  ap.add_argument('--keep-work', action='store_true')
  wd = None; tmp_out = None; lockfd = None; a = None
  try:
    a = load_job(ap.parse_args(argv))
    if a.version: print('article2epub', C.VERSION); return 0
    miss = [k for k in ('title', 'author', 'date', 'source_url', 'lang', 'out') if not getattr(a, k)]
    if miss: die('missing required values: ' + ', '.join(miss))
    a.jsonfile = a.json if not (a.url or a.html or a.from_pdf) else None
    if not (a.url or a.html or a.json or a.from_pdf): die('need --url, --html, --json or --from-pdf')
    if a.url:
      try: C.check_url(a.url)
      except ValueError as e: die(f'refused: {e}')
    title, author = noemoji(a.title), noemoji(a.author)
    if not title or not author: die('title/author empty after emoji strip')
    if a.forbid: log('WARNING: --forbid is deprecated; job metadata validation replaces it (checked only in title/author/byline).')
    out = os.path.abspath(a.out)
    if not out.endswith('.epub') or out.endswith('.needs-review.epub'): die('--out must end in .epub (not .needs-review.epub)')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    opts = {'kind_hint': 'url' if a.url else 'html' if a.html else 'pdf' if a.from_pdf else 'json', 'cover': a.cover or '', 'no_cover': a.no_cover,
            'ocr': a.ocr, 'expect_posts': a.expect_posts, 'expect_images': a.expect_images, 'trusted_html': a.trusted_html,
            'browser': a.browser, 'force_reflow': a.force_reflow}
    source_id = C.normalize_source(a.source_url)
    lockfd = lock_output(out)
    rep = {'images': [], 'failures': [], 'omissions': [], 'review': [], 'ocr': 'not-needed', 'dropped_title_heading': False}
    page = None; kind = 'web'; cover_url = None; posts_embedded = 0; html_dir = None; pdfclass = None; allowed = set()
    if a.from_pdf:
      pdfclass = C.classify_pdf(a.from_pdf)
      if pdfclass['class'] != 'prose' and not a.force_reflow:
        die(f"PDF is layout-heavy ({pdfclass}); send the PDF as is (or pass --force-reflow if the owner asked)")
      txt = subprocess.run(['pdftotext', '-layout', a.from_pdf, '-'], capture_output=True, text=True, check=True).stdout
      paras = [re.sub(r'\s+', ' ', p).strip() for p in re.split(r'\n\s*\n', txt) if p.strip()]
      page = '<html><body>' + ''.join('<p>' + H.escape(p) + '</p>' for p in paras) + '</body></html>'; a.trusted_html = True; kind = 'pdf'
    elif a.html:
      page = open(a.html, encoding='utf-8', errors='replace').read(); html_dir = os.path.dirname(os.path.abspath(a.html))
      page, allowed = localize(page, html_dir)
      kind = 'x' if is_x(a.source_url) and BeautifulSoup(page, 'lxml').select_one('.x-article-body') else 'web'
    elif a.jsonfile: page = None
    elif is_x(a.url):
      kind = 'x'; m = re.search(r'/(?:status|article)/(\d+)', a.url)
      try: page = browser_html(f'https://x.com/i/article/{m.group(1)}', '.x-article-body')
      except Exception as e:
        if not a.json: die(f'X page failed ({e}); pass --json fallback')
        log('X page failed, using --json fallback:', e); page = None; a.jsonfile = a.json
    else:
      try: page = browser_html(a.url) if a.browser else http_get(a.url)
      except C.FetchError as e: die(f'fetch refused/failed: {e}')
      except Exception as e: die(f'fetch failed: {e}')
    if a.jsonfile:
      kind = 'x-json'; d = json.load(open(a.jsonfile, encoding='utf-8')); body = json_article(d)
      nmed = len(d.get('media_entities') or [])
      if nmed: rep['failures'].append(f'{nmed} image(s) not available in the JSON fallback (text only)')
    elif kind == 'x': body, cover_url, posts_embedded = x_article(page)
    elif a.trusted_html: body = trusted_body(page)
    else: body, cover_url = generic(page, a.source_url)
    if not body or len(BeautifulSoup(body, 'lxml').get_text(strip=True)) < 200: die('extracted article text is empty/too short')
    # Build identity = source + exact input bytes (fetched page or HTML/JSON/PDF file, local images, cover file) + all
    # options + tool code + build environment. Remote pages are always refetched; reuse only when the bytes are identical.
    ih = C.hashlib.sha256()
    for blob in (page or '', open(a.jsonfile, 'rb').read() if a.jsonfile else b'', open(a.from_pdf, 'rb').read() if a.from_pdf else b''):
      ih.update(blob.encode('utf-8') if isinstance(blob, str) else blob); ih.update(b'\0')
    for f in sorted(allowed): ih.update(f.encode() + b'\0' + open(f, 'rb').read())
    if a.cover and os.path.isfile(a.cover): ih.update(b'cover\0' + open(a.cover, 'rb').read())
    input_digest = ih.hexdigest(); benv = C.build_env()
    job_id = C.key_of('article', source_id, input_digest, title, author, a.lang, a.date, a.source_url, opts, a.forbid,
                      C.tool_hash('article2epub.py', 'courier_common.py'), benv)[:24]
    for cand in (out, review_name(out)):
      if not os.path.exists(cand): continue
      try: prev = json.load(open(cand + '.job.json'))
      except Exception: prev = {}
      if prev.get('job_id') == job_id and not C.check_binding(cand, prev, cand + '.manifest.json') and not a.force:
        summ = dict(prev.get('summary', {}), reused=True); print(json.dumps(summ, ensure_ascii=False, indent=1))
        return 0 if cand == out else 5
    if os.path.exists(out) and not a.force: die(f'output exists from a different job or input: {out} (choose a new --out or pass --force)')
    raw = raw_inventory(page, kind, a.jsonfile, a.trusted_html)
    pre = BeautifulSoup(body, 'lxml')
    expected_posts = a.expect_posts or 0
    post_keys = [C.norm_text(p.get_text(' '))[:60] for p in pre.select('.kc-post') if p.get_text(strip=True)]
    exp_sections = [C.norm_text(h.get_text(' ')) for h in pre.find_all(['h1', 'h2', 'h3', 'h4']) if C.norm_key(h.get_text()) != C.norm_key(title)]
    os.makedirs(os.path.join(BASE, 'work'), exist_ok=True)
    wd = tempfile.mkdtemp(prefix=re.sub(r'\W+', '-', os.path.basename(out))[:40] + '-', dir=os.path.join(BASE, 'work'))
    fetcher = Fetcher(allowed)
    s, root, nimg = clean(body, a.source_url, wd, fetcher, title, rep)
    if a.ocr == 'off' and root.find_all('img'): rep['ocr'] = 'off'; rep['review'].append('OCR turned off: images not checked for text')
    elif a.ocr != 'off': add_ocr(s, root, wd, a.lang, rep)
    body_html = root.decode_contents()
    cover = None; cover_kind = 'none'
    if not a.no_cover:
      if a.cover or cover_url:
        cf = Fetcher([a.cover] if a.cover and not re.match('https?://', a.cover) else [])
        cover, why, _ = fetch_img(cf, a.cover or cover_url, wd, 'cover', True)
        if a.cover and not cover: die(f'--cover could not be loaded: {why}')
      if not cover: cover = 'cover.jpg'; text_cover(title, author, os.path.join(wd, cover)); cover_kind = 'generated'
      else:
        cover_kind = 'image'
        from PIL import Image
        w, h = Image.open(os.path.join(wd, cover)).size
        if w > h * 0.9: text_cover(title, author, os.path.join(wd, 'cover-portrait.jpg'), os.path.join(wd, cover)); cover = 'cover-portrait.jpg'; cover_kind = 'image+title'
    src = H.escape(a.source_url, quote=True)
    doc = (f'<html><head><meta charset="utf-8"/><title>{H.escape(title)}</title></head><body>\n<h1>{H.escape(title)}</h1>\n'
       f'<div class="byline"><p>{H.escape(author)} · {H.escape(a.date)}</p></div>\n{body_html}\n<hr/>\n'
       f'<div class="source"><p>Source: <a href="{src}">{H.escape(a.source_url)}</a></p></div>\n</body></html>')
    open(os.path.join(wd, 'article.html'), 'w', encoding='utf-8').write(doc)
    open(os.path.join(wd, 'style.css'), 'w').write(CSS)
    open(os.path.join(wd, 'epub-meta.xml'), 'w', encoding='utf-8').write(
      f'<dc:identifier id="BookId">urn:kindle-courier:job:{job_id}</dc:identifier>\n<dc:source>{H.escape(a.source_url)}</dc:source>\n')
    tmp_out = out + f'.tmp-{os.getpid()}.epub'
    cmd = [C.pandoc_bin(), 'article.html', '-f', 'html', '-t', 'epub3', '--epub-title-page=false', '--mathml', '--css', 'style.css', '-o', tmp_out,
       '--epub-metadata=epub-meta.xml', '-M', f'title={title}', '-M', f'author={author}', '-M', f'date={a.date}', '-M', f'lang={a.lang}']
    if cover: cmd += ['--epub-cover-image', cover]
    r = subprocess.run(cmd, cwd=wd, capture_output=True, text=True)
    if r.returncode: die('pandoc failed: ' + r.stderr)
    cnt, msgs = C.run_epubcheck(tmp_out, os.path.join(wd, 'epubcheck.json'))
    if cnt is None or cnt['fatal'] or cnt['error']:
      os.replace(tmp_out, out + '.broken'); tmp_out = None
      if cnt is not None: [log('EPUBCHECK', m.get('ID'), m.get('message')) for m in msgs if m.get('severity') in ('FATAL', 'ERROR')]
      die((msgs if cnt is None else 'epubcheck errors') + f'; nothing written to {os.path.basename(out)} (see .broken), do not send', 3)
    meta = C.epub_meta(tmp_out); book = C.epub_text(tmp_out)
    bad = []
    if meta['title'] != title: bad.append(f"dc:title {meta['title']!r} != {title!r}")
    if meta['creator'] != author: bad.append(f"dc:creator {meta['creator']!r} != {author!r}")
    if C.lang_base(meta['language']) != C.lang_base(a.lang): bad.append(f"dc:language {meta['language']!r} != {a.lang!r}")
    if meta['source'] != a.source_url: bad.append(f"dc:source {meta['source']!r} != {a.source_url!r}")
    if f'urn:kindle-courier:job:{job_id}' not in meta['identifiers']: bad.append('job id marker missing')
    hdr = ' '.join([meta['title'], meta['creator']] + re.findall(r'<div class="byline">(.*?)</div>', book, re.S))
    hdr = C.norm_text(re.sub(r'<[^>]+>', ' ', hdr))
    for f in a.forbid:
      if f and re.search(r'(?<!\w)' + re.escape(C.norm_text(f)) + r'(?!\w)', hdr, re.I): bad.append(f'deprecated --forbid hit in title/author/byline: {f!r}')
    if bad:
      os.replace(tmp_out, out + '.broken'); tmp_out = None; die('metadata mismatch: ' + '; '.join(bad), 4)
    btxt = C.norm_text(re.sub(r'<[^>]+>', ' ', book))
    for k in [k for k in para_keys(body_html) if k[:80] not in btxt][:20]: rep['failures'].append(f'text block missing from book: {k[:80]!r}')
    sec_inc = [x for x in exp_sections if x and x in btxt]
    for x in exp_sections:
      if x and x not in btxt: rep['failures'].append(f'section heading missing: {x[:80]!r}')
    posts_inc = sum(1 for k in post_keys if k and k in btxt)
    if expected_posts and posts_inc < expected_posts: rep['failures'].append(f'posts: expected {expected_posts}, included {posts_inc}')
    if posts_embedded: rep['omissions'].append(f'{posts_embedded} embedded post(s) kept as preview only')
    # raw source vs book: anything substantive the extractor dropped is an omission (never certified complete)
    dropped_blocks = [b for b in raw['blocks'] if b[:80] not in btxt]
    for b in dropped_blocks[:20]: rep['omissions'].append(f'text block from the source not in the book: {b[:80]!r}')
    if len(dropped_blocks) > 20: rep['omissions'].append(f'... and {len(dropped_blocks) - 20} more dropped text blocks')
    for e in raw['embeds']:
      if not any(e.split(' ', 1)[-1] in o for o in rep['omissions']): rep['omissions'].append(f'{e} not included (cannot be shown on Kindle)')
    img_emb = sum(1 for i in rep['images'] if i['status'] == 'embedded')
    img_dec = sum(1 for i in rep['images'] if i.get('classification') == 'decorative')
    if a.expect_images and img_emb < a.expect_images: rep['failures'].append(f'images: expected {a.expect_images}, embedded {img_emb}')
    for i in rep['images']:
      if i['status'] == 'dropped' and i.get('classification') != 'decorative': rep['omissions'].append(f"image dropped: {i['src']} ({i['reason']})")
    unaccounted = raw['images'] - len(rep['images'])
    if unaccounted > 0: rep['omissions'].append(f'{unaccounted} image(s) in the source were removed by extraction')
    if rep['omissions']: rep['review'].append('content was omitted; review the omissions list before sending')
    if any(i.get('ocr') == 'text' for i in rep['images']): rep['review'].append('machine-transcribed (OCR) text was added; it may contain errors')
    status = 'text_only' if kind == 'x-json' else 'incomplete' if rep['failures'] else 'needs_review' if rep['review'] else 'complete'
    final = out if status == 'complete' else review_name(out)
    manifest = {'tool': 'article2epub', 'version': C.VERSION, 'source_kind': kind, 'source_id': source_id,
      'raw_source': {'text_blocks': len(raw['blocks']), 'images': raw['images'], 'embeds': raw['embeds'], 'dropped_text_blocks': len(dropped_blocks)},
      'sections': {'expected': len(exp_sections), 'included': len(sec_inc)},
      'posts': {'expected': expected_posts or len(post_keys), 'included': posts_inc, 'embedded_previews': posts_embedded},
      'images': {'expected': max(raw['images'], a.expect_images), 'embedded': img_emb, 'decorative_skipped': img_dec, 'items': rep['images']},
      'ocr': rep['ocr'], 'dropped_duplicate_title_heading': rep['dropped_title_heading'], 'pdf_class': pdfclass,
      'failures': rep['failures'], 'omissions': rep['omissions'], 'review_reasons': rep['review'],
      'review_needed': bool(rep['review']), 'complete': status == 'complete', 'status': status, 'review': {'acknowledged': False}}
    summary = {'path': final, 'bytes': os.path.getsize(tmp_out), 'images': img_emb, 'cover': cover_kind, 'epubcheck': cnt, 'lang': a.lang,
       'title': title, 'author': author, 'source_kind': kind, 'manifest_status': status, 'complete': status == 'complete',
       'review_needed': bool(rep['review']), 'failures': rep['failures'], 'omissions': rep['omissions'],
       'status': C.status_stages(built=True, validated=True), 'job_id': job_id, 'version': C.VERSION}
    job = {'job_id': job_id, 'tool': 'article2epub', 'version': C.VERSION, 'source_url': a.source_url, 'source_id': source_id,
       'input_digest': input_digest, 'title': title, 'author': author, 'lang': a.lang, 'date': a.date, 'format': 'epub', 'options': opts,
       'build_env': benv, 'pdf_class': (pdfclass or {}).get('class'), 'force_reflow': bool(a.force_reflow),
       'summary': summary}
    # Commit: book, manifest, then job.json (the commit record binding both by sha256); see C.commit_book.
    t, tmp_out = tmp_out, None
    C.commit_book(t, final, job, manifest, crash_point)
    for stale in ([out + '.broken'] + ([review_name(out), review_name(out) + '.job.json', review_name(out) + '.manifest.json'] if final == out else [])):
      if os.path.exists(stale): os.remove(stale)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if status == 'complete' else 5
  except Fail as e:
    log('ERROR:', e); return e.code
  finally:
    if tmp_out and os.path.exists(tmp_out): os.remove(tmp_out)
    if wd and not (a and a.keep_work): shutil.rmtree(wd, ignore_errors=True)
    if lockfd is not None: os.close(lockfd)

if __name__ == '__main__':
  sys.exit(main())

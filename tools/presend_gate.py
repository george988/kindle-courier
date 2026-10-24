#!/usr/bin/env python3
"""presend_gate (Kindle Courier): deterministic pre-send checks and a durable delivery ledger.

  intake    --file F   record a file the owner sent (path, sha256, size, MIME) the moment it arrives; refuses files the
            courier built (job sidecar, build marker, or under work/outbox). Required before --kind upload|pdf.
  init      create the delivery ledger once (setup). A missing ledger is never recreated silently: every other command
            fails closed (exit 5) so dedupe history cannot be lost without noticing.
  check     --file F --to ADDR [--to ADDR2] --route gmail|grok-inbox|custom [--job F.job.json]
            [--kind built|upload|pdf] [--original-sha256 H]   (one file per send in 2.0.0)
            Recipients must be on the owner-approved allowlist $KINDLE_BASE/config/recipients.json:
            {"recipients": [{"address": "...", "label": "...", "kind": "kindle"|"other", "default": true|false}]}
            (written at setup with the owner; a missing or malformed list blocks every send). [--dest-kind kindle|other] [--route-limit-bytes N]
            [--confirm-unknown-limit] [--resend-approved]
  promote   --file X.needs-review.epub --evidence TEXT   record the owner's review of a held book and move it to its
            sendable name (the review, omissions and failures it accepted are kept in the manifest)
  reserve   same options as check; on success atomically reserves the ledger key (status 'reserved') and prints it
  record    --key K --status sent|unknown|failed [--message-id ID] [--reason TEXT]
  verify-sent --key K --size N --mime M [--sha256 H]     compare the sent message's attachment with the reserved file
  reconcile --key K --status sent|failed --evidence JSON   resolve an 'unknown'/stale reservation. Evidence comes from a
            Sent-folder lookup: {"source": "sent-folder", "searched_after": <unix time, not before the reservation>,
            "found": true|false, "message_id": "...", "recipients": [...], "attachment": {"size": N, "sha256": "..."?}}
  mark-device-confirmed --key K --evidence TEXT          only after the owner says the book is on the device
  encode    --key K   base64 of the reserved file into $KINDLE_BASE/outbox (deleted by record)
  repair-epub --in F --out G   explicit, owner-requested repair into a NEW file (never in place)
  list      [--key K]

Ledger key = sha256(source identity, content digest, destinations, format, options). Titles never dedupe.
Statuses: reserved -> sent | unknown | failed. 'unknown' (and a reservation whose lease expired) blocks every retry until
reconciled. 'device_confirmed' is never set automatically. Exit: 0 ok, 5 blocked, 2 usage error."""
import argparse, base64, json, math, os, re, sqlite3, subprocess, sys, tempfile, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import courier_common as C
if __name__ == '__main__':
  if '--version' in sys.argv: print('presend_gate', C.VERSION); sys.exit(0)
  C.ensure_venv()
BASE = C.BASE
LEASE_S = 15 * 60
MB = 1000 * 1000
# Sender routes: limit in bytes and what it applies to. Personal Gmail: 25 MB counted on the encoded message, so the
# base64 size is checked. The Grok Bot inbox provider limit is not documented: unknown, fail closed unless confirmed.
ROUTES = {'gmail': {'limit': 25 * MB, 'measure': 'encoded'}, 'grok-inbox': None, 'custom': None}
# Destination limits: Send to Kindle by email: <= 50 MB per email, <= 25 attachments.
DESTS = {'kindle': {'total': 50 * MB, 'max_attachments': 25}, 'other': None}
ALLOWED_MIME = {'.epub': 'application/epub+zip', '.pdf': 'application/pdf',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}

def encoded_size(n): b = 4 * math.ceil(n / 3); return b + 2 * math.ceil(b / 76)

class Blocked(Exception): pass
LEDGER = os.path.join(BASE, 'ledger', 'deliveries.sqlite')
ALLOWLIST = os.path.join(BASE, 'config', 'recipients.json')

def load_allowlist():
  """Owner-approved recipients: {address: entry}. Missing or malformed -> ({}, error) so every send is blocked."""
  if not os.path.exists(ALLOWLIST): return {}, f'recipient allowlist missing ({ALLOWLIST}): set it up with the owner first'
  try:
    d = json.load(open(ALLOWLIST, encoding='utf-8')); rs = d['recipients']; out = {}
    if not isinstance(rs, list) or not rs: raise ValueError('recipients must be a non-empty list')
    for r in rs:
      addr = r['address']
      if not isinstance(addr, str) or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', addr): raise ValueError(f'bad address {addr!r}')
      if not isinstance(r.get('label'), str) or r.get('kind') not in ('kindle', 'other') or not isinstance(r.get('default'), bool):
        raise ValueError(f'entry for {addr} needs label (string), kind (kindle|other) and default (true|false)')
      out[addr.strip().lower()] = r
    return out, None
  except Exception as e: return {}, f'recipient allowlist malformed: {e}'

def db(create=False):
  if not create and not os.path.exists(LEDGER):
    raise Blocked(f'delivery ledger missing ({LEDGER}); it is never recreated silently. If this is a new setup, run: presend_gate.py init')
  os.makedirs(os.path.join(BASE, 'ledger'), exist_ok=True)
  c = sqlite3.connect(LEDGER, timeout=60, isolation_level=None)
  c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA synchronous=FULL')
  c.execute('''CREATE TABLE IF NOT EXISTS deliveries(key TEXT PRIMARY KEY, source_id TEXT, content_digest TEXT, destinations TEXT,
    format TEXT, options TEXT, files TEXT, title TEXT, status TEXT, attempts INTEGER, reserved_at REAL, lease_until REAL, updated_at REAL,
    message_id TEXT, attachment_verified TEXT, device_confirmed INTEGER DEFAULT 0, evidence TEXT, history TEXT)''')
  c.execute('CREATE TABLE IF NOT EXISTS uploads(path TEXT, sha256 TEXT, size INTEGER, mime TEXT, t REAL, PRIMARY KEY(path, sha256))')
  return c

def courier_built(path):
  """Reasons a file is a courier build (so it must go through --kind built with its job), else []."""
  why = []; rp = os.path.realpath(path)
  for d in ('work', 'outbox', 'cache', 'releases'):
    if rp.startswith(os.path.realpath(os.path.join(BASE, d)) + os.sep): why.append(f'lives under {d}/')
  for side in ('.job.json', '.manifest.json'):
    if os.path.exists(path + side): why.append(f'has a {side} sidecar')
  if re.search(r'\.(broken|needs-review\.epub)$|\.tmp-\d+\.epub$', path): why.append('builder temp/held name')
  if C.sniff_mime(path) == 'application/epub+zip':
    try:
      if any(i.startswith('urn:kindle-courier:job:') for i in C.epub_meta(path)['identifiers']): why.append('carries a courier build marker')
    except Exception: pass
  return why

def intake(path):
  if not os.path.isfile(path): raise SystemExit(f'missing file {path}')
  why = courier_built(path)
  if why: raise SystemExit('not an owner upload (' + '; '.join(why) + '): send it as --kind built with its job')
  rec = {'path': os.path.realpath(path), 'sha256': C.sha256_file(path), 'size': os.path.getsize(path), 'mime': sniff(path), 't': time.time()}
  c = db()
  try: c.execute('INSERT OR IGNORE INTO uploads VALUES(?,?,?,?,?)', tuple(rec.values()))
  finally: c.close()
  return rec

def row(c, key):
  r = c.execute('SELECT * FROM deliveries WHERE key=?', (key,)).fetchone()
  return dict(zip([d[0] for d in c.execute('SELECT * FROM deliveries LIMIT 0').description], r)) if r else None

def sniff(path):
  m = C.sniff_mime(path)
  if m == 'application/zip':
    try:
      with zipfile.ZipFile(path) as z:
        if 'word/document.xml' in z.namelist(): return ALLOWED_MIME['.docx']
    except Exception: pass
  return m

def evaluate(a):
  """All checks; returns (ok, report). Never modifies any input file."""
  errs, warns, files = [], [], []
  dests = sorted({t.strip().lower() for t in a.to if t.strip()})
  if not dests: errs.append('no destination')
  allow, aerr = load_allowlist()
  if aerr: errs.append(aerr)
  else:
    for d in dests:
      if d not in allow: errs.append(f'recipient {d} is not on the owner-approved allowlist (config/recipients.json)')
  if not a.file: errs.append('no file')
  if len(a.file) > 1: errs.append('one file per send in this release (multi-file sends are not verified per file): send them separately')
  kinds = {allow[d]['kind'] for d in dests if not aerr and d in allow}
  dkind = 'kindle' if kinds == {'kindle'} else 'other'
  job = None
  if a.job:
    try: job = json.load(open(a.job, encoding='utf-8'))
    except Exception as e: errs.append(f'job file unreadable: {e}')
    if job is not None and not isinstance(job, dict): errs.append('job file is not a JSON object'); job = None
  manifest = None
  for f in a.file:
    rec = {'path': os.path.abspath(f)}; files.append(rec)
    if not os.path.isfile(f): errs.append(f'missing file: {f}'); continue
    if re.search(r'\.(broken|tmp-\d+\.epub|needs-review\.epub)$', f):
      errs.append(f'refusing a .broken/temp/needs-review file: {f} (review it, then run promote)'); continue
    rec.update(sha256=C.sha256_file(f), size=os.path.getsize(f), mime=sniff(f))
    ext = os.path.splitext(f)[1].lower()
    if ext not in ALLOWED_MIME: errs.append(f'unsupported file type for this gate: {ext or "(none)"}')
    elif rec['mime'] != ALLOWED_MIME[ext]: errs.append(f'MIME mismatch: {f} looks like {rec["mime"]}, extension says {ALLOWED_MIME[ext]}')
    if rec['size'] == 0: errs.append(f'empty file: {f}')
    if rec['mime'] == 'application/epub+zip':
      with tempfile.TemporaryDirectory() as td:
        cnt, msgs = C.run_epubcheck(f, os.path.join(td, 'e.json'))
      rec['epubcheck'] = cnt
      if cnt is None: errs.append(f'epubcheck could not run: {msgs}')
      elif cnt['fatal'] or cnt['error']:
        errs.append(f'epubcheck {cnt["fatal"]} fatal / {cnt["error"]} errors in {os.path.basename(f)}' +
                    ('; the upload is NOT repaired automatically (owner may ask for repair-epub into a new file)' if a.kind == 'upload' else ''))
    if rec['mime'] == 'application/pdf':
      r = subprocess.run(['pdfinfo', f], capture_output=True, text=True)
      if r.returncode: errs.append(f'pdfinfo cannot read {f}')
  f0 = files[0] if files else {}
  # Kind is derived from the ledger (intake record), the build marker/sidecars and the MIME; --kind is only an assertion
  # that must agree with it.
  if f0.get('sha256'):
    c = db(); intook = c.execute('SELECT 1 FROM uploads WHERE path=? AND sha256=?', (os.path.realpath(f0['path']), f0['sha256'])).fetchone(); c.close()
    derived = 'built' if courier_built(f0['path']) else ('pdf' if f0['mime'] == 'application/pdf' else 'upload') if intook else None
    if derived is None: errs.append('unknown file: neither a courier build (job sidecar/marker) nor an intake-recorded upload')
    elif a.kind and a.kind != derived and not (a.kind == 'upload' and derived == 'pdf'):
      errs.append(f'--kind {a.kind} does not match the file (derived: {derived})')
    a.kind = derived or a.kind or 'built'
    if a.kind == 'built' and not a.job: a.job = f0['path'] + '.job.json'
    if a.job and job is None and a.kind == 'built':
      try: job = json.load(open(a.job, encoding='utf-8'))
      except Exception as e: errs.append(f'job file unreadable: {e}')
      if job is not None and not isinstance(job, dict): errs.append('job file is not a JSON object'); job = None
  a.kind = a.kind or 'built'
  KIND_MIME = {'pdf': {'application/pdf'}, 'upload': {'application/epub+zip', 'application/pdf', ALLOWED_MIME['.docx']}, 'built': {'application/epub+zip'}}
  if f0.get('mime') and f0['mime'] not in KIND_MIME[a.kind]: errs.append(f"--kind {a.kind} cannot send {f0['mime']}")
  if a.kind in ('upload', 'pdf') and f0.get('sha256'):
    if a.job: errs.append(f'--kind {a.kind} takes no --job')
    why = courier_built(f0['path'])
    if why: errs.append('this file was built by the courier (' + '; '.join(why) + '): use --kind built with its job')
    c = db(); up = c.execute('SELECT sha256 FROM uploads WHERE path=? AND sha256=?', (os.path.realpath(f0['path']), f0['sha256'])).fetchone()
    known = [r[0] for r in c.execute('SELECT sha256 FROM uploads WHERE path=?', (os.path.realpath(f0['path']),))]; c.close()
    if not up: errs.append('no intake record for these bytes: run intake when the file arrives' + (' (bytes changed since intake)' if known else ''))
    if a.original_sha256 and a.original_sha256 != f0['sha256']: errs.append('upload bytes changed since arrival: send the original file, unmodified')
  if a.kind == 'built':
    if not job: errs.append('built book: --job <out>.job.json is required')
    elif f0.get('sha256'):
      if os.path.realpath(a.job) != os.path.realpath(f0['path'] + '.job.json'): errs.append('job file is not this book\'s sidecar (<book>.job.json)')
      mpath = f0['path'] + '.manifest.json'
      errs += C.check_binding(f0['path'], job, mpath)
      try: manifest = json.load(open(mpath, encoding='utf-8'))
      except Exception: manifest = None
      if f0.get('mime') == 'application/epub+zip':
        m = C.epub_meta(f0['path'])
        for k, jk in (('title', 'title'), ('creator', 'author'), ('source', 'source_url')):
          if m[k] != job.get(jk): errs.append(f'metadata mismatch: dc:{k} {m[k]!r} != job {job.get(jk)!r}')
        if job.get('lang') and C.lang_base(m['language']) != C.lang_base(job['lang']): errs.append(f"metadata mismatch: dc:language {m['language']!r}")
        if f"urn:kindle-courier:job:{job.get('job_id')}" not in m['identifiers']: errs.append('job id marker missing (stale content)')
        if C.content_digest(f0['path']) != job.get('content_digest'): errs.append('content digest mismatch')
      if job.get('pdf_class') and job['pdf_class'] != 'prose' and not job.get('force_reflow'):
        errs.append('layout-heavy PDF was reflowed: send the original PDF instead')
      if isinstance(manifest, dict) and not C.validate_manifest(manifest):
        rv = manifest.get('review') or {}
        if manifest.get('status') != 'complete' and not rv.get('acknowledged'):
          errs.append(f"book is {manifest.get('status')}: failures={manifest.get('failures')} omissions={manifest.get('omissions')} "
                      f"review={manifest.get('review_reasons')} (tell the owner; promote --evidence only after they accept)")
  # size limits per route and destination
  sizes = [r.get('size', 0) for r in files]; total = sum(sizes); enc = sum(encoded_size(s) for s in sizes)
  route = ROUTES.get(a.route, 'invalid')
  if route == 'invalid': errs.append(f'unknown route {a.route}')
  elif a.route == 'custom':
    if not a.route_limit_bytes: errs.append('custom route needs --route-limit-bytes (a documented limit)')
    elif total > a.route_limit_bytes: errs.append(f'{total} bytes exceeds the custom route limit {a.route_limit_bytes}')
  elif route is None:
    if not a.confirm_unknown_limit: errs.append(f'{a.route}: attachment limit is unknown; confirm explicitly (--confirm-unknown-limit) or use a route with a documented limit')
    else: warns.append(f'{a.route}: limit unknown, sending on explicit confirmation')
  else:
    measured = enc if route['measure'] == 'encoded' else total
    if measured > route['limit']: errs.append(f'{a.route}: {measured} bytes ({route["measure"]}) exceeds {route["limit"]}')
  dl = DESTS.get(dkind)
  if dl:
    if len(files) > dl['max_attachments']: errs.append(f'{dkind}: {len(files)} attachments exceed {dl["max_attachments"]}')
    if total > dl['total']: errs.append(f'{dkind}: {total} bytes exceed {dl["total"]}')
  else: warns.append('destination limits unknown (not a Send-to-Kindle address)')
  job = job if isinstance(job, dict) else None
  src = (job or {}).get('source_id') or ('upload:' + (files[0].get('sha256') or '') if files else '')
  digest = (job or {}).get('content_digest') or C.key_of(*[r.get('sha256') for r in files])
  fmt = '+'.join(sorted({os.path.splitext(r['path'])[1].lstrip('.').lower() for r in files}))
  options = (job or {}).get('options') or {}
  key = C.key_of(src, digest, dests, fmt, options)
  c = db(); prev = row(c, key); c.close()
  if prev:
    st = prev['status']
    if st == 'reserved' and prev['lease_until'] < time.time(): st = 'unknown (stale reservation)'
    if st == 'sent' and not a.resend_approved: errs.append(f"already sent (message {prev['message_id']}); duplicate blocked")
    elif st.startswith('unknown') or st == 'reserved': errs.append(f'previous attempt is {st}: reconcile before any retry (no blind resend)')
  rep = {'ok': not errs, 'errors': errs, 'warnings': warns, 'key': key, 'source_id': src, 'content_digest': digest,
         'destinations': dests, 'dest_kind': dkind, 'route': a.route, 'format': fmt, 'files': files, 'total_bytes': total,
         'encoded_bytes': enc, 'title': (job or {}).get('title'), 'omissions': (manifest or {}).get('omissions', []),
         'status': {'built': bool(job) or a.kind != 'built', 'validated': not errs, 'email_sent': False, 'device_confirmed': False}}
  return not errs, rep

def reserve(a):
  ok, rep = evaluate(a)
  if not ok: return False, rep
  c = db(); now = time.time()
  try:
    c.execute('BEGIN IMMEDIATE')
    prev = row(c, rep['key'])
    if prev and not (prev['status'] == 'failed' or (prev['status'] == 'sent' and a.resend_approved)):
      c.execute('ROLLBACK'); rep['ok'] = False; rep['errors'].append(f"lost the reservation race: key is {prev['status']}"); return False, rep
    hist = json.loads(prev['history']) if prev else []
    hist.append({'t': now, 'event': 'reserved'})
    c.execute('INSERT OR REPLACE INTO deliveries(key,source_id,content_digest,destinations,format,options,files,title,status,attempts,reserved_at,'
              'lease_until,updated_at,message_id,attachment_verified,device_confirmed,evidence,history) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
              (rep['key'], rep['source_id'], rep['content_digest'], json.dumps(rep['destinations']), rep['format'], json.dumps({}),
               json.dumps(rep['files']), rep['title'], 'reserved', (prev['attempts'] if prev else 0) + 1, now, now + LEASE_S, now,
               None, None, 0, None, json.dumps(hist)))
    c.execute('COMMIT')
  finally: c.close()
  rep['reserved'] = True; return True, rep

def transition(key, allowed, why, **kw):
  """State change as ONE conditional UPDATE inside BEGIN IMMEDIATE: applies only if the row is still in an allowed state
  ('reserved+stale' = reserved with an expired lease). rowcount 0 means another process got there first: refused."""
  c = db(); now = time.time()
  try:
    c.execute('BEGIN IMMEDIATE')
    conds = [f"status='{s}'" for s in allowed if s != 'reserved+stale']
    if 'reserved+stale' in allowed: conds.append("(status='reserved' AND lease_until < ?)")
    r = row(c, key)
    if not r: c.execute('ROLLBACK'); raise SystemExit(f'no ledger entry {key}')
    hist = json.loads(r['history'] or '[]'); hist.append(dict({'t': now, 'from': r['status']}, **kw))
    sets = dict(kw, history=json.dumps(hist), updated_at=now)
    params = list(sets.values()) + [key] + ([now] if 'reserved+stale' in allowed else [])
    cur = c.execute('UPDATE deliveries SET ' + ','.join(f'{k}=?' for k in sets) + ' WHERE key=? AND (' + ' OR '.join(conds) + ')', params)
    if cur.rowcount != 1: c.execute('ROLLBACK'); raise SystemExit(f"refused: {why}; entry is now {r['status']} (another process changed it first)")
    c.execute('COMMIT'); return row(c, key)
  finally: c.close()

def record(key, status, message_id=None, reason=None, verified=None):
  if status == 'sent' and not message_id: raise SystemExit('sent needs --message-id')
  if status == 'failed' and not reason: raise SystemExit('failed needs --reason (only when the message definitely did not go out)')
  r = transition(key, ('reserved',), f'cannot record {status} unless the entry is reserved (use reconcile)',
                 status=status, message_id=message_id, evidence=reason, **({'attachment_verified': verified} if verified else {}))
  out = os.path.join(BASE, 'outbox', key + '.b64')
  if os.path.exists(out): os.remove(out)
  return r

def verify_sent(key, size, mime, sha=None):
  c = db(); r = row(c, key); c.close()
  if not r or r['status'] != 'sent': raise SystemExit('verify-sent needs a sent entry')
  f = json.loads(r['files'])[0]
  res = {'size_match': int(size) == f['size'], 'mime_match': mime == f['mime'],
         'sha256_match': (sha == f['sha256']) if sha else None}
  res['verified'] = res['size_match'] and res['mime_match'] and res['sha256_match'] is not False
  res['note'] = 'sha256 verified' if sha else 'sha256 not verified (no downloaded copy); size and MIME only'
  if res['verified']: transition(key, ('sent',), 'verify-sent', attachment_verified=json.dumps(res))
  else: transition(key, ('sent',), 'verify-sent', status='unknown', attachment_verified=json.dumps(res),
                   evidence='sent attachment does not match the reserved file; reconcile with the owner')
  return res

def reconcile(key, status, evidence, message_id=None):
  """Resolve unknown/stale entries only with structured Sent-folder evidence validated against the reservation."""
  try: ev = json.loads(evidence) if isinstance(evidence, str) else evidence
  except Exception: raise SystemExit('reconcile --evidence must be JSON from a Sent-folder lookup (free text is refused)')
  c = db(); r = row(c, key); c.close()
  if not r: raise SystemExit(f'no ledger entry {key}')
  f = json.loads(r['files'])[0]; dests = sorted(json.loads(r['destinations']))
  need = {'source': str, 'searched_after': (int, float), 'found': bool, 'recipients': list}
  for k, t in need.items():
    if not isinstance(ev, dict) or not isinstance(ev.get(k), t): raise SystemExit(f'evidence needs {k} ({t})')
  if ev['source'] != 'sent-folder': raise SystemExit('evidence source must be sent-folder')
  if ev['searched_after'] > r['reserved_at']: raise SystemExit('the Sent search must cover the time since the reservation (searched_after <= reserved_at)')
  if sorted(x.lower() for x in ev['recipients']) != dests: raise SystemExit(f'evidence recipients {ev["recipients"]} do not match the reservation {dests}')
  if status == 'sent':
    att = ev.get('attachment') or {}
    if not ev['found'] or not ev.get('message_id'): raise SystemExit('sent needs found=true and the message_id')
    if att.get('size') != f['size'] or ('sha256' in att and att['sha256'] != f['sha256']):
      raise SystemExit('the found message attachment does not match the reserved file')
    message_id = ev['message_id']
  elif ev['found']: raise SystemExit('evidence says a message was found: reconcile as sent, not failed')
  return transition(key, ('unknown', 'reserved+stale'), 'only unknown or stale reservations can be reconciled',
                    status=status, message_id=message_id, evidence='reconciled: ' + json.dumps(ev, sort_keys=True))

def deliver(a, adapter):
  """Reserve -> re-hash -> adapter.send -> verify -> record. Used with mocked transports in tests; real sends follow the
  same steps by hand. adapter.send(files, to, subject, body) returns {'message_id', 'attachments': [{'size','mime','sha256'}]};
  it raises TransportRejected when the message definitely did not leave; anything else means 'unknown'.
  'sent' is recorded only when the sent attachment matches the reserved bytes; a mismatch or a file that changed during
  the send is recorded 'unknown' (it may have gone out with other bytes) and needs reconciliation."""
  ok, rep = reserve(a)
  if not ok: return rep
  f = rep['files'][0]
  if C.sha256_file(f['path']) != f['sha256']:
    record(rep['key'], 'failed', reason='file changed after reservation; not sent'); rep.update(ok=False, result='failed'); return rep
  try:
    res = adapter.send(rep['files'], rep['destinations'], rep['title'] or os.path.basename(f['path']), 'Attached.')
  except TransportRejected as e:
    record(rep['key'], 'failed', reason=str(e)); rep.update(ok=False, result='failed'); return rep
  except BaseException as e:
    record(rep['key'], 'unknown', reason=f'{type(e).__name__}: {e}'); rep.update(ok=False, result='unknown'); return rep
  att = (res.get('attachments') or [{}])[0]
  v = {'size_match': att.get('size') == f['size'], 'mime_match': att.get('mime') == f['mime'],
       'sha256_match': att.get('sha256') == f['sha256'], 'file_unchanged': C.sha256_file(f['path']) == f['sha256']}
  v['verified'] = all(v.values()); rep['verify'] = v
  if not v['verified']:
    record(rep['key'], 'unknown', message_id=res.get('message_id'), reason='sent attachment does not match the reserved file: ' + json.dumps(v))
    rep.update(ok=False, result='unknown'); return rep
  record(rep['key'], 'sent', message_id=res['message_id'], verified=json.dumps(v))
  rep['status']['email_sent'] = True; rep['result'] = 'sent'; rep['message_id'] = res['message_id']; return rep

class TransportRejected(Exception): pass

def repair_epub(src, dst):
  """Owner-requested repair into a NEW file: prefixes NCX/nav ids that start with a digit. The input is never changed."""
  if os.path.abspath(src) == os.path.abspath(dst) or os.path.exists(dst): raise SystemExit('repair must write a new, non-existing file')
  before = C.sha256_file(src)
  with zipfile.ZipFile(src) as zi, zipfile.ZipFile(dst + '.tmp', 'w') as zo:
    zo.writestr(zipfile.ZipInfo('mimetype'), zi.read('mimetype'), compress_type=zipfile.ZIP_STORED)
    for it in zi.infolist():
      if it.filename == 'mimetype': continue
      b = zi.read(it.filename)
      if it.filename.endswith(('.ncx', '.xhtml', '.opf')):
        ids = set(re.findall(rb'\bid="(\d[^"]*)"', b))
        for i in ids: b = re.sub(rb'(\bid=")' + re.escape(i) + rb'"', rb'\1np_' + i + b'"', b).replace(b'#' + i + b'"', b'#np_' + i + b'"')
      zo.writestr(it, b, compress_type=zipfile.ZIP_DEFLATED)
  os.replace(dst + '.tmp', dst)
  assert C.sha256_file(src) == before
  with tempfile.TemporaryDirectory() as td: cnt, _ = C.run_epubcheck(dst, os.path.join(td, 'e.json'))
  return {'input': src, 'input_sha256_unchanged': True, 'output': dst, 'output_sha256': C.sha256_file(dst), 'epubcheck': cnt}

def promote(path, evidence):
  if not path.endswith('.needs-review.epub'): raise SystemExit('promote takes a .needs-review.epub file')
  if not evidence: raise SystemExit('promote needs --evidence (what the owner reviewed and accepted)')
  mf, jf = path + '.manifest.json', path + '.job.json'
  m = json.load(open(mf, encoding='utf-8')); j = json.load(open(jf, encoding='utf-8'))
  sha = C.sha256_file(path)
  errs = C.check_binding(path, j, mf)
  if errs: raise SystemExit('manifest/job do not describe this file; rebuild: ' + '; '.join(errs))
  final = path[:-len('.needs-review.epub')] + '.epub'
  if os.path.exists(final): raise SystemExit(f'{final} exists; refusing to overwrite')
  m['review'] = {'acknowledged': True, 'evidence': evidence, 't': time.time(), 'accepted_failures': m.get('failures'),
                 'accepted_omissions': m.get('omissions'), 'accepted_review_reasons': m.get('review_reasons')}
  m['epub'] = final; j['epub'] = final
  C.write_json(final + '.manifest.json', m); j['manifest_sha256'] = C.sha256_file(final + '.manifest.json')
  os.replace(path, final); C.write_json(final + '.job.json', j)
  for f in (mf, jf): os.remove(f)
  return {'promoted': final, 'epub_sha256': sha, 'review': m['review']}

def parser():
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  sp = ap.add_subparsers(dest='cmd', required=True)
  for name in ('check', 'reserve'):
    p = sp.add_parser(name)
    p.add_argument('--file', action='append', default=[]); p.add_argument('--to', action='append', default=[])
    p.add_argument('--route', required=True); p.add_argument('--job'); p.add_argument('--kind', choices=['built', 'upload', 'pdf'], help='optional assertion; the gate derives the kind itself')
    p.add_argument('--original-sha256')
    p.add_argument('--route-limit-bytes', type=int)
    p.add_argument('--confirm-unknown-limit', action='store_true'); p.add_argument('--resend-approved', action='store_true')
  p = sp.add_parser('record'); p.add_argument('--key', required=True); p.add_argument('--status', choices=['sent', 'unknown', 'failed'], required=True)
  p.add_argument('--message-id'); p.add_argument('--reason')
  p = sp.add_parser('verify-sent'); p.add_argument('--key', required=True); p.add_argument('--size', type=int, required=True)
  p.add_argument('--mime', required=True); p.add_argument('--sha256')
  p = sp.add_parser('reconcile'); p.add_argument('--key', required=True); p.add_argument('--status', choices=['sent', 'failed'], required=True)
  p.add_argument('--evidence', required=True, help='JSON (see reconcile above)'); p.add_argument('--message-id')
  p = sp.add_parser('mark-device-confirmed'); p.add_argument('--key', required=True); p.add_argument('--evidence', required=True)
  p = sp.add_parser('encode'); p.add_argument('--key', required=True)
  p = sp.add_parser('repair-epub'); p.add_argument('--in', dest='src', required=True); p.add_argument('--out', required=True)
  p = sp.add_parser('list'); p.add_argument('--key')
  p = sp.add_parser('init')
  p = sp.add_parser('intake'); p.add_argument('--file', required=True)
  p = sp.add_parser('promote'); p.add_argument('--file', required=True); p.add_argument('--evidence', required=True)
  return ap

def main(argv=None):
  try: return _main(argv)
  except (Blocked, sqlite3.DatabaseError) as e:
    print(json.dumps({'ok': False, 'errors': [f'{type(e).__name__}: {e}'], 'blocked': True}), file=sys.stdout); return 5

def init():
  if os.path.exists(LEDGER): raise SystemExit(f'ledger already exists: {LEDGER}')
  c = db(create=True); c.execute('PRAGMA integrity_check'); c.close(); return {'ledger': LEDGER, 'created': True}

def _main(argv=None):
  a = parser().parse_args(argv)
  if a.cmd == 'init': print(json.dumps(init())); return 0
  if a.cmd in ('check', 'reserve'):
    ok, rep = (evaluate if a.cmd == 'check' else reserve)(a)
    print(json.dumps(rep, ensure_ascii=False, indent=1)); return 0 if ok else 5
  if a.cmd == 'record': r = record(a.key, a.status, a.message_id, a.reason)
  elif a.cmd == 'verify-sent':
    r = verify_sent(a.key, a.size, a.mime, a.sha256); print(json.dumps(r, indent=1)); return 0 if r['verified'] else 5
  elif a.cmd == 'reconcile': r = reconcile(a.key, a.status, a.evidence, a.message_id)
  elif a.cmd == 'mark-device-confirmed':
    r = transition(a.key, ('sent',), 'only a sent delivery can be device-confirmed', device_confirmed=1, evidence='device confirmed by owner: ' + a.evidence)
  elif a.cmd == 'encode':
    c = db(); r0 = row(c, a.key); c.close()
    if not r0 or r0['status'] != 'reserved': raise SystemExit('encode only a reserved delivery')
    f = json.loads(r0['files'])[0]
    if C.sha256_file(f['path']) != f['sha256']: raise SystemExit('file changed since reservation')
    os.makedirs(os.path.join(BASE, 'outbox'), mode=0o700, exist_ok=True)
    out = os.path.join(BASE, 'outbox', a.key + '.b64')
    with open(f['path'], 'rb') as fi, open(out + '.tmp', 'wb') as fo: fo.write(base64.b64encode(fi.read()))
    os.replace(out + '.tmp', out); print(json.dumps({'b64': out, 'bytes': f['size'], 'sha256': f['sha256'], 'mime': f['mime']})); return 0
  elif a.cmd == 'intake': print(json.dumps(intake(a.file), indent=1)); return 0
  elif a.cmd == 'promote': print(json.dumps(promote(a.file, a.evidence), ensure_ascii=False, indent=1)); return 0
  elif a.cmd == 'repair-epub': print(json.dumps(repair_epub(a.src, a.out), indent=1)); return 0
  elif a.cmd == 'list':
    c = db(); rows = [row(c, a.key)] if a.key else [row(c, k) for (k,) in c.execute('SELECT key FROM deliveries ORDER BY updated_at')]; c.close()
    print(json.dumps(rows, ensure_ascii=False, indent=1)); return 0
  print(json.dumps({k: r[k] for k in ('key', 'status', 'message_id', 'device_confirmed', 'attachment_verified')}, indent=1)); return 0

if __name__ == '__main__':
  sys.exit(main())

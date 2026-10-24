#!/usr/bin/env python3
"""verify_lock.py LOCK [LOCK...]: exit 0 only if this interpreter is the supported platform (CPython 3.13, Linux
x86_64; the wheel hashes in the locks are for it) and every 'name==version' in the locks is installed at exactly that
version (importlib.metadata). Prints one line per mismatch. --platform-only checks just the platform."""
import platform, re, sys
from importlib import metadata
SUPPORTED = ((3, 13), 'Linux', 'x86_64')
def platform_ok():
  got = (sys.version_info[:2], platform.system(), platform.machine())
  if sys.implementation.name != 'cpython' or got != SUPPORTED:
    print(f'unsupported platform {sys.implementation.name} {got}: the locks are for CPython 3.13 on Linux x86_64 '
          '(regenerate requirements*.lock with pip download on this platform)'); return False
  return True
def main(argv):
  if not platform_ok(): return 2
  bad = 0
  for lock in [a for a in argv if not a.startswith('--')]:
    for name, ver in re.findall(r'^([A-Za-z0-9_.\-]+)==([^\s\\;]+)', open(lock).read(), re.M):
      try: have = metadata.version(name)
      except metadata.PackageNotFoundError: have = None
      if have != ver: print(f'{name}: locked {ver}, installed {have}'); bad += 1
  return 1 if bad else 0
if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))

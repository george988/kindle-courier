# Changelog

Notable changes to Kindle Courier are recorded here. Dates use YYYY-MM-DD.

## 2.0.0 - 2026-10-24

Published to the [public Grok Bot template](https://x.ai/bot/LXZMn9iFYykfjhOdwffV6) using reviewed source commit [`72af6bb9584bec6348ec08863442699fb1c39f80`](https://github.com/george988/kindle-courier/commit/72af6bb9584bec6348ec08863442699fb1c39f80).

### Public listing

- Name the public listing **Kindle Courier 2.0.0** while retaining the existing template URL.
- Clarify that video URLs are inputs, web and video content is converted to EPUB, and uploaded PDF, EPUB, and DOCX files are forwarded unchanged by default.
- Keep release dates and detailed history in this changelog; omit manually maintained dates from the public description.
- This presentation update leaves the four reviewed skill bodies, pinned source commit, and runtime behavior unchanged.

Public description:

> Send a public article, X post or thread, or video URL—or upload a PDF, EPUB or DOCX file. Kindle Courier turns web and video content into EPUBs, forwards uploaded files unchanged, and emails them to your Kindle address.
> Created by George Hong (@DomainMaster).

### Upgrade considerations

- Require CPython 3.13 on Linux x86_64 for the locked runtime.
- Require an owner-approved recipient allowlist and initialized delivery ledger. Missing or invalid state blocks sending.
- Limit each send to one file. Uncertain delivery outcomes require reconciliation before retrying.
- Treat tools and skills as a coordinated release. A full rollback must restore the matching prior skills as well as the prior tools; the tool rollback helper alone does not restore skills.

### Added

- Typed JSON build jobs, content-completeness manifests, metadata checks, and held-for-review outputs for incomplete or uncertain books.
- A pre-send gate with recipient, attachment, content-identity, and route-size checks.
- A SQLite delivery ledger with atomic reservations, duplicate blocking, conditional status transitions, and structured reconciliation evidence.
- Intake tracking for uploaded EPUB, PDF, and DOCX files, preserving their original bytes. EPUB repair requires an explicit request.
- Separate built, validated, email-sent, and device-confirmed states.
- Immutable tool release directories, checksum verification, atomic activation, baseline capture, and rollback helpers.
- A compact four-skill public template with a commit-pinned installer that verifies all 24 downloaded files before use.
- A public GitHub source repository for traceable changes.

### Fixed

- Source and cache collisions involving matching titles, Chinese titles, generic video hosts, URL paths, and query strings.
- Stale article reuse after changes to fetched content or local assets.
- Platform detection based on misleading URL substrings.
- Caption-language selection and Chinese-text adequacy checks.
- WebVTT parsing and overlap deduplication, preserving legitimate repeated speech and ignoring cue identifiers and non-caption blocks.
- Missing-content detection for dropped text, images, and embedded material; affected books are held for review.
- Local-image handling, metadata escaping, duplicate title headings, and rejection of valid small books by an arbitrary minimum file size.
- Delivery-gate bypasses involving forged or mismatched sidecars, incorrect file-kind assertions, and changed attachments.
- Concurrent ledger transitions and unsafe retries after ambiguous send outcomes.
- First-run setup ordering, exact dependency checks, and agreement between embedded skill tools and distributed tool files.

### Changed

- Use build identities derived from source, input content, options, tools, and environment.
- Publish generated output in book → manifest → job order, removing the old job record first, to support detection of interrupted builds.
- Validate fetched destinations across redirects and restrict local asset paths.
- Pin Pandoc 3.5 and EPUBCheck 5.1.0 by hash and install Python dependencies from hash-locked requirements.
- Keep PDF uploads unchanged by default; make prose reflow an explicit option.
- Label OCR and transcription limitations and distinguish email submission from confirmed Kindle arrival.

### Verification

- Release suite: 35/35 passing with real EPUBCheck 5.1.0, independently rerun by Dr Eggbot.
- Codex targeted checks: 23/23 passing with real Pandoc, files, and SQLite. These local checks used an EPUBCheck stub to isolate application logic; real-validator evidence came from the remote runs.
- Fresh-install, installer-tamper, idempotency, concurrency, activation, and rollback checks completed during release review.
- A non-sending smoke test passed on the deployed 2.0.0 tools.
- Anonymous source download matched all 24 pinned files.
- The compact template passed 13 independent review checks. The four actual staged skill bodies matched their reviewed hashes before publication.
- Corrected template draft 7 was published after review caught an omitted, unregistered installer skill in the preceding draft.

### Known limitations

- Public sources must be accessible; paywalled, private, login-only, and interaction-dependent pages are unsupported.
- OCR and speech recognition may be inaccurate, and video books do not reproduce full video visuals.
- New installations depend on GitHub and dependency-source availability. System packages and the Playwright browser download are not fully pinned.
- Grok Bot inbox attachment limits are undocumented; that route requires owner confirmation.
- No real email or Kindle-arrival test was performed for this release.
- The public source repository does not yet include the release test suite or automated CI.

### Release provenance

The reviewed RC1 tool bytes were activated and published as 2.0.0 without modification. Consequently, `tools/VERSION` still reads `2.0.0-rc1 CANDIDATE`.

The tool checksum-manifest SHA-256 is:

```text
50536751e621c149e3caf8ff9ed0d578aed177816d93920de92c51cbb9585807
```

The x.ai template's four compact skills and the repository's three canonical skills are different distribution forms of the reviewed workflow. GitHub changes require an explicit template update and publication before they reach the public template.

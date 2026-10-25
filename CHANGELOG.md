# Changelog

Notable changes to Kindle Courier are recorded here. Dates use YYYY-MM-DD.

## 2.0.1 — publication pending

### Fixed
- Preserve readable original diagrams and captions without adding supplementary OCR by default. The bot performs visual checks and binds them to the embedded image hashes; missing, corrupt or unreadable content still holds.
- Honor job-file OCR settings, retain body-image resolution within the pixel cap, and reject uniform blank images.
- Recover public media through Grok Bot's supported normal network path while retaining destination checks and source inventories.
- Require source and Sent-history checks before resending rebuilt content, since rebuilding changes the content digest. Explicit owner holds remain in force.

### Release packaging
- Add all four compact public skill bodies, the listing and a hash receipt under `templates/public`.
- Pin the installer to runtime source `f1baf0f3cd149ce5cb20da61ebe1442254ee1fc5`; all 24 anonymous source downloads match their hashes.
- Align public workflow metadata and the immutable release directory with 2.0.1, removing stale candidate/private labels. Shared CLI/API compatibility remains 2.0.0; exact runtime hashes identify the release.
- Runtime builder code is byte-identical to the verified private OCR policy patch. Private validation passed 15 regressions and 28 independent cases; two complete real articles passed EPUBCheck 5.1.0 with no fatal errors, errors or warnings.
- Live delivery passed with a new diagram-rich article: 20/20 sections, 8/8 original diagrams, no supplementary OCR, no owner approval prompt, real EPUBCheck zero errors/warnings, and one verified Sent attachment matching the book. Device arrival is pending owner confirmation.
- Independent public-installer review passed fresh/repeat installation and two tamper-refusal cases. Same-URL template publication verification is pending; the public template remains 2.0.0 until complete.

## Private validation history — OCR policy and proxy-compatible image recovery

### OCR policy correction (2026-10-25; private deployment)
- Preserve original diagrams and source captions by default without adding supplementary OCR. Require the bot to inspect embedded images for readability; record its attestation in the job and bound manifest rather than asking the owner about optional OCR.
- Keep missing/corrupt/unreadable images, omitted content, explicit transcription requests and all existing delivery checks blocking. Historical sends and explicit owner holds are unchanged.
- Bind image review to exact embedded-image SHA256 values, record native/embedded sizes, reject uniform blank images and retain body-image resolution up to 40 million pixels.
- Fix job-file `ocr` settings being masked by the command-line parser's default; reject invalid job OCR values.
- Track this private runtime as `2.0.0-ocrpolicy1`; API version stays 2.0.0 and job identity includes exact tool hashes. Public x.ai template remains at the published source until separately updated.
- Added 15 regression tests using real Pandoc and a mocked EPUBCheck; all passed locally and remotely. Independent review passed 28 adversarial cases. Two real article rebuilds retained all sections/images without supplementary OCR and passed EPUBCheck 5.1.0 with zero fatal errors, errors or warnings.
- Verified private live installation and exact saved skill bodies; fresh/repeat installs passed and tampered input was refused. Moved four stale transferred skill copies intact to backup and confirmed a fresh catalog load no longer lists them. No emails were sent, and existing delivery history, owner holds and book files were preserved.
- Visual readability still requires actual bot inspection. Rebuilt content has a new digest, so source/history checks remain necessary before any resend. Historical video-skill metadata remains a cleanup item for the next public release.

### Changed
- Recover public images through the platform's supported normal-network downloader/browser, then validate and embed local assets using the existing builder.
- Record source URL, local filename, byte count, dimensions, hash and source placement. Reconcile source inventory, parsed HTML, manifest and EPUB instead of counting lines or assuming remote images were embedded.
- Attempt supported recovery before asking the owner to accept missing images; retain genuine video/OCR and unavailable-content holds.
- The original media-recovery change kept runtime bytes unchanged; the subsequent private OCR policy patch below changes only the article builder and variant label. Network and delivery tools remain unchanged. Private setup bodies and hashes are tracked under `templates/private`; public template unchanged.

### Superseded experiment
- Removed the alternate-DNS code and its tests after the new account's review identified that direct address resolution could bypass its network proxy. Earlier image-recovery tests verified output but did not establish acceptable routing. Do not install the `2.0.0-mediafix` experiment from earlier commits.
- Verified on a fresh Grok Bot account: fresh and repeat installation succeeded, tampered input was refused, all four saved skill body hashes matched, and the original network refusals remained active. A chart downloaded through the normal proxy was embedded successfully; EPUBCheck returned zero errors or warnings. Independent inspection confirmed EPUB/sidecar hashes, image references and decoded pixels; the genuine OCR hold remained.

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

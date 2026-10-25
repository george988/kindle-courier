# Kindle Courier 2.0.1 review closure

At review closure, publication was paused by the existing template association. Subsequently, 2.0.1 was published under the current account at a new URL; see the [publication record](publication-2.0.1.md). The blocker below is retained as historical context.

## Findings and fixes

| Finding | Resolution | Verification status |
| --- | --- | --- |
| Active video workflow named the old RC1 checksum | Active/public video body identifies 2.0.1 and the current runtime manifest. Historical snapshots are explicitly marked as such. | Exact public body hash checked; Courier's active-workflow scan found no old RC1 checksum or candidate labels. |
| Transferred skill copies exposed old OCR instructions | Copies were moved intact outside active workflow directories. | Independent fresh catalog load and disk check passed. |
| Page-level fallback intake was underspecified | Explicit supported page-then-media fallback, retaining the direct refusal and network guards. | Fresh non-sending article test complete: 15 sections, 13 images, no OCR; exported provenance and 15 fetch-attempt records independently checked. |
| Missing page provenance and fetch logs | Retain raw capture, reconstructed input, source-provenance hashes and sanitized per-attempt fetch records. | Exported file hashes, final EPUB/sidecar bindings and all 13 embedded-image hashes independently checked. |
| Visual review referred to a temporary inspection book | Archive the inspected EPUB/member hashes, then finalize against the actual final EPUB, manifest, job and media members. | Exported file hashes, final EPUB/sidecar bindings and all 13 embedded-image hashes independently checked. |
| Canonical and compact onboarding differed | Onboarding bodies now match, documenting both public-installer and canonical embedded-tool setup. | Canonical/compact body comparison and all four live saved-skill body hashes passed. |
| README and changelog mixed current and historical identity | Current candidate, actual public version, private history and publication status are explicit. | Independent reviewer signed off on the final source/bundle pins. |
| Release suffix restriction was undocumented | README documents `X.Y.Z` or `X.Y.Z-suffix`, with one suffix. | Present in reviewed candidate source. |
| Legacy positive test image was uniform | Replace only the positive fixture with non-uniform content; preserve the blank-image rejection case. | Targeted positive and blank-rejection cases pass in the repaired maintained copy; archived original restored to its recorded hash. |
| Evidence requirements could be mistaken for runtime enforcement | README explicitly distinguishes workflow receipts from the existing enforced image/delivery gates. | Documentation-only commit `e7a57ba`; independent reviewer closed this finding. |
| Builder removed the temporary inspection EPUB | Preserve a hash-verified, byte-identical copy outside builder-managed output before rebuilding; verify it still exists afterwards. | Targeted two-pass check passed; archived original survived cleanup. Both EPUBs and all receipt/file/image hashes independently verified locally. |
| Main branch lacked the reviewed fixes | The reviewed source, workflows and closure record are included in [PR #1](https://github.com/george988/kindle-courier/pull/1). | Merge status is recorded on the PR; exact bundle/source pins remain immutable. |

## Verified source identities

- Public bundle: `3475735e33af610b1fbf0e8de5b1f775d70d80a0`.
- Installer source pin: `37c3a740fc585b9baa2a9dd23e3ad213c0a10006`.
- Runtime manifest SHA-256: `df03e6204a62aed3f455e73db9c023ac7ab8ebbd076ee5fd1bd1c793b9a569cf`.
- Runtime tools are unchanged from the already tested and installed 2.0.1 build; shared CLI/API compatibility remains 2.0.0.
- All 24 installer files were independently downloaded and verified. All four body hashes, shared canonical/compact sections and installer shell syntax passed local checks.

## External blocker and limits

`CreateBotShareJson` returns `Grok Bot template not found`. It uses an internal bot/template association and accepts no explicit template ID or URL. The error does not prove ownership loss. Restoring that association or using the original publishing bot/account is required before staging the existing public URL. No replacement template had been created at the time of this review. A new template was subsequently published as recorded above.

Actual image readability still requires visual inspection; hashes and EPUBCheck alone cannot detect every placeholder or assess meaning. The builder enforces exact-image attestation through its bound manifest. Page provenance and final visual-review receipts are workflow requirements, not new runtime gate checks.

The earlier live test was emailed once with all 20 sections and 8 diagrams, no supplementary OCR and clean EPUBCheck results. Device arrival remains unconfirmed. Review-closure tests do not send mail, release owner holds or alter delivery history.

## Historical archive status

The original 2.0.0 private archive has five pre-existing missing generated build artifacts; it is not a complete reinstall source. Its test file was restored to its recorded manifest hash, and the repaired maintained test copy lives outside the archive. No replacement historical artifacts were invented. The current pinned 2.0.1 installation verifies independently.

## Final evidence verification — 2026-10-25

The private evidence archive is `kc-2.0.1-final-evidence.zip`, 41,166,426 bytes, SHA-256 `375da6528c3e973930cbc38fbb20cf4b397b1bb3099a683fe1085c18e8652ffd`. Independent local verification passed all 395 checksum entries and 394 original-path mappings, plus:

- Four saved skill bodies equal the pinned public bundle byte for byte.
- Source capture and reconstructed article hashes match provenance; 15 fetch-attempt records bind the saved bytes.
- Full article: 15/15 sections and 13/13 images, OCR off.
- Targeted preservation check: retained inspection SHA `1935d73d2b50a76ccb2882b6171888d4ce5992ef583720cf286ea422a865c470`; final EPUB SHA `9ac7f0c356b06d97e691dbc29faefe8f9bc1e73e3092043344392a141d7d032c`. Both exist, and all 13 image hashes agree with both EPUBs, manifest, job attestation and visual-review evidence.
- Real EPUBCheck: zero fatal errors, errors and warnings.
- Final pinned installer: exit 0; before/after runtime, recipient and delivery-history snapshots byte-identical.
- Repaired positive fixture passes; unchanged blank-image rejection passes.

The full intake run used the preceding `908793f4` workflow; its missing original inspection EPUB is accurately recorded. The final `3475735e` preservation check reused those inputs without fetching again and retained both inspection and final EPUBs. No historical evidence was backfilled or relabelled. No emails were sent in this closure pass.

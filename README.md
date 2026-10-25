# Kindle Courier

Turn public articles, X posts and threads, and video URLs into checked EPUBs, or forward your own EPUB, PDF, and DOCX files to your Kindle.

**Current public release: 2.0.0 — October 24, 2026**

Created by [George Hong (@DomainMaster)](https://x.com/DomainMaster).

[Use the Grok Bot template](https://x.ai/bot/LXZMn9iFYykfjhOdwffV6) · [Release history](CHANGELOG.md)

## Get started

1. Open the public template in Grok Bot and create your own bot from it.
2. Give it your Send-to-Kindle email address. For multiple devices, provide their names and choose a default.
3. Connect your sending account. Gmail is the integration included in the template; the workflow also describes using a Grok Bot inbox if available.
4. Add the sending address to Amazon's Approved Personal Document E-mail List.
5. Choose whether the bot may send directly or must show each email for approval.
6. Let the bot finish installation and recipient setup, then send a public link or upload a supported document.

The bot records the addresses you approve and checks them before every send. The template includes no personal addresses, private memory, or scheduled routines.

Example requests:

- “Turn this public article into an EPUB and send it to my Kindle: <URL>”
- “Make a Chinese transcript EPUB from this video: <URL>”
- “Send this uploaded PDF as is.”

## Supported content

| Input | Behavior |
| --- | --- |
| Public web articles | Build an EPUB with metadata and a content-completeness manifest. |
| Public X posts, threads, and Articles | Build from accessible content; disclose missing material and hold incomplete results for review. |
| Public video links | Build from available captions or speech transcription; report the method and limitations. |
| Uploaded EPUB | Preserve the original bytes; repair only when explicitly requested. |
| Uploaded PDF | Forward as is by default; prose reflow is optional. |
| Uploaded DOCX | Forward the original document. |

Paywalled, private, login-only, and interaction-dependent pages are outside the supported workflow. Video books do not reproduce the full visual content of a video. OCR and speech transcription can contain errors.

## What 2.0.0 checks

- **Book validity and completeness:** generated EPUBs pass EPUBCheck and metadata checks. Missing sections or images, OCR output, and other review conditions hold the book for owner review.
- **Source and cache identity:** cache keys incorporate source identity, content, options, and tool information to reduce collisions and stale reuse.
- **Recipient and attachment checks:** a pre-send gate checks the approved recipient, file type, size, and recorded content identity. Each send contains one file.
- **Duplicate and uncertain sends:** a SQLite ledger reserves deliveries atomically. An uncertain send is held for reconciliation rather than retried automatically.
- **Delivery reporting:** “built,” “validated,” “email sent,” and “device confirmed” are separate states. Only the owner can confirm arrival on the Kindle.
- **Untrusted content:** instructions found inside articles, documents, or transcripts are treated as source content.

These checks do not guarantee source accuracy, successful extraction from every public site, or delivery by Amazon.

## Installation and runtime

Use the public template for normal setup. Its four skills cover installation, onboarding, EPUB processing, and video processing.

The installer downloads **24 files** from a fixed GitHub commit: 20 tool files, their checksum manifest, and three canonical skill files. It verifies every SHA-256 hash before using the downloaded files.

The supported runtime is **CPython 3.13 on Linux x86_64**. Setup requires network access to GitHub and dependency sources, plus permission to install the required runtime components. Pandoc 3.5 and EPUBCheck 5.1.0 are hash-pinned; Python packages use hash-locked requirements. System packages and the Playwright browser download are not fully pinned.

The default bot workspace is `/workspace/kindle`; `KINDLE_BASE` can select a different base. This release is not a supported native macOS or Windows installation.

## Repository layout

| Path | Purpose |
| --- | --- |
| [tools/](tools/) | Builders, delivery gate, dependency locks, installation, activation, and rollback helpers. |
| [SHA256SUMS](SHA256SUMS) | Checksums for the 20 distributed tool files. |
| [skills/kindle-courier-getting-started/](skills/kindle-courier-getting-started/) | Canonical onboarding instructions. |
| [skills/kindle-epub-build/](skills/kindle-epub-build/) | Canonical document workflow and embedded release tools. |
| [skills/kindle-video-build/](skills/kindle-video-build/) | Canonical video workflow and embedded video tool. |
| [CHANGELOG.md](CHANGELOG.md) | User-facing release history. |

The public template uses four compact skills. This repository contains the three larger canonical skills they install from; the compact installer is distributed in the x.ai template.

## Release identity and verification

The published 2.0.0 template installs source commit [`72af6bb9584bec6348ec08863442699fb1c39f80`](https://github.com/george988/kindle-courier/commit/72af6bb9584bec6348ec08863442699fb1c39f80).

The preserved [tools/VERSION](tools/VERSION) file reads `2.0.0-rc1 CANDIDATE`. Those exact reviewed bytes were subsequently activated and published as 2.0.0; the label was retained to preserve their hashes.

Release verification included 35 passing release tests with real EPUBCheck, an independent rerun, fresh installation and tamper checks, and a non-sending deployment smoke test. All four staged template skill bodies were checked against the reviewed hashes before publication. No real email send or device-arrival test was performed. These are recorded release checks; the public repository does not yet contain the test suite or automated CI.

## Maintaining the public template

GitHub is the source history; x.ai publication is a separate step.

1. Make and review changes, and add an entry to `CHANGELOG.md`.
2. Run the relevant build, delivery-gate, installation, and regression checks in an isolated workspace.
3. Commit the reviewed release source and update the template installer's commit and file-hash pins.
4. In Grok Bot, use **Share → Update template**. Register any new skill on the bot before staging: the template tool can omit unregistered skills.
5. Review the staged version, including all four skill bodies, then **Publish** and verify the public page.

A GitHub documentation edit alone does not update the published template. The 2.0.0 template remains pinned to its reviewed source commit.

## Image recovery workflow (unreleased)

In Grok Bot, public hostnames may resolve to a synthetic network-proxy address that the strict tool downloader refuses. The revised private workflow uses the platform's supported normal-network download path, validates and inventories the returned images, then supplies local assets to the existing builder. All original runtime tools and their checksum manifest remain unchanged. Missing media and other completeness warnings remain review conditions.

The four reviewed private setup bodies and their hashes are in [templates/private](templates/private). Its installer pins the original audited runtime commit `72af6bb9584bec6348ec08863442699fb1c39f80`; only the EPUB workflow differs from the public template. Public publication is separate. The earlier alternate-DNS experiment is superseded and must not be installed.

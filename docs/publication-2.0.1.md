# Kindle Courier 2.0.1 publication — 2026-10-25

## Public identity

- Current template: [Kindle Courier 2.0.1](https://x.ai/bot/XQWWJOzqzWz3ksBfQ8lz0).
- Template ID: `XQWWJOzqzWz3ksBfQ8lz0`.
- Publishing bot: **Kindle Courier 2.0.1 Publisher**, under the current George Hong account. Keep this bot and account association for future updates.
- Superseded release: [Kindle Courier 2.0.0](https://x.ai/bot/LXZMn9iFYykfjhOdwffV6). Its transferred publishing association returned “Grok Bot template not found.” No claim of ownership loss is made; old-link recovery is optional.
- GitHub remains the source history. Existing users need an explicit upgrade; publishing a new template does not update their copied bots.

## Configuration and publication verification

Dr Eggbot independently reviewed the exact staging arguments. The four inline skill bodies match reviewed bundle `3475735e33af610b1fbf0e8de5b1f775d70d80a0` byte for byte. The profile is the approved Kindle Courier description, Gmail is the only integration, memory and routines are empty, and `kindle-courier-getting-started` is selected for onboarding. No recipient addresses, ledger, private evidence archive or publisher coordination instructions are included.

Staging-arguments SHA-256: `9dec98ca3b4db947953ca29a1dc8c3ffe4f3896922a107722248ac7cfb0cefb7`.

The app review showed the correct name, approved description, October 25 update date, Gmail and all four skills. The installer, EPUB workflow and video identity were inspected in the app, including retained inspection-artifact rules and the corrected video runtime checksum. The first revision was published and its actual Copy link was read from the app.

An identical-arguments update on the same publisher successfully staged revision 2 at 09:40 ET. Its profile, Gmail and four-skill context were reviewed and the revision was published. The latest card shows **Published**, and Copy link remains `https://x.ai/bot/XQWWJOzqzWz3ksBfQ8lz0`. The older revision card changes to Unpublished when superseded; it must not be republished as an attempted repair. This verifies the new publishing association supports updates.

Anonymous HTTP retrieval and browser inspection confirmed the public name and complete approved description. The public deep link opens the correct app preview, showing **By George Hong** and **Last updated Oct 25**. No new bot import was completed.

## Immutable release identity

- Runtime/installer source: `37c3a740fc585b9baa2a9dd23e3ad213c0a10006`.
- Runtime SHA256SUMS hash: `df03e6204a62aed3f455e73db9c023ac7ab8ebbd076ee5fd1bd1c793b9a569cf`.
- Release directory and tools version: `2.0.1`; shared CLI/API compatibility: `2.0.0`.
- Exact four skill-body hashes: [receipt.json](../templates/public/receipt.json).
- Runtime, workflow and live-delivery evidence: [review closure](review-closure-2.0.1.md).

## Isolated installer verification

Courier ran the installer extracted from the exact staging arguments in a new empty base on October 25, 09:40:59–09:41:10 ET. It exited 0, verified all 24 pinned downloads, staged and activated 2.0.1, and passed the dependency check. The installed release matched the live release byte for byte. Video dependencies remain on demand; a new video conversion was not part of this test.

The test base contained no recipients, ledger or sent records and requires normal onboarding. The before/after live snapshots were identical: recipient configuration, ledger, releases, activation log and four saved skills were preserved. The installer refreshed pip's download cache and left one source-extraction directory in `/tmp`; it did not install global packages or modify live Kindle state. This test used a machine with system prerequisites already present and is not a bare-machine dependency test.

The downloaded evidence archive is `kindle-freshinstall-evidence-20261025T134002Z.zip`, 38,801 bytes, SHA-256 `bc65541dd53a27458f5853e27a5aac7a09fc7ab7f39d70cdf42e01aa4a63e6ec`. Local independent verification passed all 27 evidence checksum entries, exact comparisons of the four bodies with this repository, equal before/after snapshots, installer exit status, the 24-pin verification log, runtime manifest hash and approved profile. This evidence is retained privately; the public template carries no evidence ZIP.

## Verification limits and presentation

The staging tools do not provide a full server-side export for an independent byte-for-byte read-back. Exact arguments and local body hashes were checked; app context and sampled skill content were inspected. An isolated installer check is distinct from creating and onboarding a new bot through the public template.

The x.ai web page still renders the account byline as **by George**, while the app preview shows **By George Hong**. The complete approved description includes **Created by George Hong (@DomainMaster)** in the served HTML and accessibility text. The web card visually clamps long descriptions, so that attribution can be hidden at the inspected width. These are observed platform presentation limits, not missing saved description text; the approved wording was preserved.

No new emails were sent during publication checks. Device arrival from the earlier authorized live test remains unconfirmed. Existing owner holds must remain in force.

---
name: kindle-courier-getting-started
description: >-
  Kindle Courier only: first conversation with a new owner, or whenever memory is missing the sending account or
  Kindle address.
---
# Kindle Courier: getting started

Open with one line: "send me a public article, X post or thread, PDF, EPUB, DOCX or video link and i'll make a checked Kindle book and email it to your Kindle address." Then ask these one at a time, waiting for each answer. Skip any that memory already answers.

1. **Kindle address.** "what's your Send-to-Kindle email address? (Amazon, Manage Your Content and Devices, then Devices, then your Kindle.)" If they have more than one Kindle, take each one with a device name, then ask which should get books by default (one or all).
2. **Sending account.** Offer both:
   - "your own Gmail": connect the Gmail connector (InstallPlugin, or AuthenticateMcpServer if it's installed) and use the address it's signed in as;
   - "my own Grok Bot email": check ListEmailInboxes first. If there's none, ask what name they'd like before @, check it with CheckEmailInboxAvailability, and claim only the one they pick (a claim is permanent). Its attachment size limit isn't documented, so large books need their OK.
3. **Approved sender.** Tell them to add that sending address to Amazon's Approved Personal Document E-mail List (amazon.com, Manage Your Content and Devices, then Preferences, then Personal Document Settings). Otherwise Amazon silently drops the email.
4. **Standing permission.** "these emails only go to your own Kindle. want me to send them straight away, or show you each one first?" If they chose the Grok Bot email and want direct sends, tell them each email otherwise waits on a card, and turn drafting off only after they say yes.

Tell them what to expect: books that miss something (images, sections, video) are held and you'll ask first; you report when the email was sent, and only they can confirm it arrived on the device.

Save to memory: the Kindle addresses with device names, the default, the sending account, the permission answer, and that the approved-sender reminder was given.

Then set up, in this order (kindle-epub-build section 0):
1. If `${KINDLE_BASE:-/workspace/kindle}/tools/presend_gate.py` is missing, run section 0 part 1 (creates the base, rebuilds and verifies the tools, stages and activates them, installs the runtime). Otherwise run `bash "${KINDLE_BASE:-/workspace/kindle}/tools/ensure_tools.sh"`.
2. Run section 0 part 2 with exactly the addresses the owner gave (KINDLE_ADDRESS, DEVICE_LABEL; one entry per device), read the list back to them, and let it create the ledger. The gate sends only to these addresses; change the list only when the owner asks.
Offer a test: "send me a link and i'll make your first book." Make no routines; this bot works when a link arrives.

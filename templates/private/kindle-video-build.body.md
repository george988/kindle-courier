# Kindle video build (Kindle Courier 2.0.0)

Base dir `${KINDLE_BASE:-/workspace/kindle}` (`$B`). Requires `bash "$B/tools/ensure_tools.sh" --video` first (yt-dlp, faster-whisper and ffmpeg are checked inside the venv).
Release identity: Kindle Courier 2.0.0 (rc1 audited build, tools/VERSION `2.0.0-rc1 CANDIDATE`, SHA256SUMS sha256 50536751e621c149e3caf8ff9ed0d578aed177816d93920de92c51cbb9585807).
Tools: the 20 Kindle Courier 2.0.0 tools come from the verified release installed by kindle-courier-install (hash-pinned to SHA256SUMS); this skill no longer embeds them.

1. Write a JSON job file (never put titles or URLs in a shell command): `url`, optional `title`, `author`, `date`, `lang`, `post_text`, `frames` (0..3), `out`.
2. `python3 "$B/tools/video2epub.py" --job /path/job.json`. It re-executes inside the venv; `--doctor` shows which yt-dlp/whisper it uses.
3. Exit 0 = complete; 3 = too little speech (no book; the JSON shows the counted units: CJK characters count one each, other text counts words, threshold 150 words or up to 300 CJK characters); 2 = refused (bad URL, workdir/output from another source); 4 = epubcheck failed (`.broken`); 5 = held for review (e.g. captions only in another language).
4. Then follow kindle-epub-build steps 3 to 5 (gate, ledger, honest report). Tell the owner the transcript method; speech-to-text can be wrong, and the video's visuals are not included.

Caches are keyed by the video's identity, language, model, captions mode and tool version, and checked before reuse, so different videos never share files even with the same or all-Chinese titles.

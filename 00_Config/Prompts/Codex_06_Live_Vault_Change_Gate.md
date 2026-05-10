# Codex 06 - Live Vault Change Gate

Use this prompt before any task that could write to the live/final `06_Stock` Obsidian vault, including import, report, QA, generated Markdown updates, cleanup, cache removal, file moves, file deletes, renames, or template/document consolidation.

```text
You are working on the 06_Stock automation project.

Goal:
- Decide whether a requested live vault change is safe to execute.
- Treat live vault cleanup as a live vault write.
- Do not modify the live vault unless the required gate has been completed and the user explicitly asks for the actual write.

Important paths:
- GitHub baseline repo:
  C:\Users\KSLV-II\Desktop\Codex\stock
- Live/final Obsidian vault:
  C:\Users\KSLV-II\Desktop\Obsidian\ESJ\06_Stock

Default mode:
- Work in the GitHub baseline repo first.
- Do not open, copy, or modify live vault files unless the task explicitly requires live-vault inspection or write handling.
- Do not run import/report/qa/all unless explicitly requested for this task.
- Do not read or print private broker data, account identifiers, raw files, processed files, SQLite DB files, exports, logs, attachments, journal entries, company notes, trade notes, cashflow notes, or library content.
- Do not write investment thesis, sell criteria, buy/sell recommendations, or investment opinions.
- Exclude files with `Personal` or `personal` in the filename from cleanup, merge, rename, or delete decisions.

Required gate before any actual live vault write:
1. Update the GitHub baseline first.
2. Run the relevant tests.
3. Run the repository quality gate.
4. Run the live vault command in dry-run mode.
5. Review and summarize the expected live-vault changes.
6. Ask for and receive explicit user intent for the actual live write.

Live vault cleanup rules:
- Cleanup is a live vault write and must follow the same gate unless the user explicitly scopes the task to a narrow cleanup action.
- Only delete clear cache/system artifacts when deletion is explicitly requested.
- Clear cache/system artifacts include `.pyc`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.ipynb_checkpoints`, and an empty `__pycache__`.
- If a cache directory contains an unknown non-cache file, do not delete the directory or file. Report filenames only.
- Examples of ambiguous non-cache files include `*.DOCX`, `*.xlsx`, `.tmp.drive*`, and unknown generated-looking filenames.
- Do not open ambiguous files to inspect contents unless the user explicitly asks and the file is outside restricted/private areas.
- Do not delete `.tmp.drivedownload` or `.tmp.driveupload` before user confirmation.
- Do not delete, merge, rename, or consolidate README or template files before user confirmation, even when they look duplicated.

Report format:
- State whether the task remained baseline-only or touched the live vault.
- List files changed in the baseline.
- For live vault cleanup, list only deleted folders/files and preserved ambiguous filenames.
- State whether tests, quality gate, dry-run, expected-change review, and explicit user intent were completed.
- State that no import/report/qa/all was run unless it was actually run.
```

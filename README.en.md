# Codex Cleaner

[简体中文](README.md) | **English**

A local Windows cleanup tool for Codex, with session management, database maintenance, and file cleanup. Use your browser to inspect storage usage, preview contents, and remove unwanted sessions, old logs, caches, and staging leftovers.

The service listens only on `127.0.0.1` and does not upload conversation content. Normal use requires no Node.js, frontend dependencies, or additional database installation.

## Features

- **Storage overview**: Sort by size or last activity, search records, filter by project, and navigate project groups.
- **Session relationships**: Display subagent tasks and safety reviews under their parent sessions when an explicit relationship is available. Attached records are collapsed by default.
- **Content previews**: Click a title to view messages, replies, and related files. Previews support incremental loading, a resizable pane, and clearing the current preview.
- **Bulk cleanup**: Select individual records, all matching records, project groups, or groups of unlinked records.
- **Missing-file cleanup**: Filter for records whose files are all missing and remove the remaining session records through the official CLI.
- **Database maintenance**: Reclaim unused database space and optionally remove runtime logs according to a retention period.
- **File cleanup**: Inspect the data directory, select recommended old logs, caches, and staging leftovers, and manually review generated artifacts and backups.
- **Chinese / English**: The initial language follows your browser preference. Manual choices are remembered.

Opening or refreshing the page always starts in **Sessions**. Selections, filters, and grouping preferences are still saved separately for each module.

## Requirements

- Windows.
- Python 3.10 or newer, with `python` or `py` available on your PATH.
- Existing local Codex session data.
- A compatible Codex CLI for session deletion. The tool attempts to find it automatically.

**No fixed CLI version is required.** The tool checks the official deletion command and automatically verifies its behavior in an isolated temporary data directory: a locked session must be protected, other sessions must remain deletable, and releasing the lock must allow deletion. Verification uses disposable test sessions and never touches your real sessions. Deletion is enabled after verification succeeds; failures appear at the top with a read-only status and reason. Python testing has primarily used Windows with Python 3.13.

## Quick start

Download or clone the project, then double-click `start.cmd`. The tool opens your browser and scans the local Codex data directory.

The launcher first tries `python`, then `py -3`, checking for Python 3.10 or newer. The window stays open after the service exits or startup fails so you can read the output. If it reports that the service is already running, use the original window.

Alternatively, run this from the project directory:

```powershell
python app.py
```

The default address is `http://127.0.0.1:8765`. If that port is unavailable, the tool uses another available port. Check the startup window for the actual address. Keep that window open; closing it stops the service.

### Choose a data directory or port

```powershell
# Use a specific Codex data directory
python app.py --home "D:\CodexData"

# Specify the official CLI executable
python app.py --cli "C:\path\to\codex.exe"

# Choose a port without opening the browser automatically
python app.py --port 8766 --no-browser
```

| Option | Description | Default |
| --- | --- | --- |
| `--home` | Codex data directory | `CODEX_HOME`, or `.codex` under your user directory if unset |
| `--cli` | Codex CLI executable path | `CODEX_CLEANER_CLI`, or automatic discovery if unset |
| `--port` | Preferred local port | `8765` |
| `--no-browser` | Do not open the browser at startup | The browser opens by default |

You can also change the data directory and CLI path in **Settings** at the top right. Saving detects Codex and loads sessions automatically. These settings apply only to the current run and do not modify Codex's own configuration.

## Manage and clean up sessions

### Browse records

After the initial scan completes, search by title, project, path, or session ID, or filter by file status. Enable **Group by project** to navigate projects from the sidebar.

Sessions and their attached records appear in one list:

- Records with a confirmed parent relationship appear beneath that session. They are collapsed by default and can be expanded when needed.
- Selecting a parent session also selects all its linked descendants, even when collapsed.
- **Unlinked records** cannot currently be associated with an existing parent session. **Unlinked does not mean useless or safe to delete automatically.**
- When a child matches a filter, its parent may appear for context. A parent that does not match the filter cannot be selected from that context row and is not included in Select all.

Relationships come from explicit fields in the Codex database and log headers. Sharing a project or having similar timestamps is not treated as proof of a relationship.

### Preview content

Click a title to view its content in the right pane. Drag the pane boundary to resize it, or use **Clear preview** to dismiss the current content.

Previews focus on user messages and identifiable assistant replies; they are not complete conversation exports. Images appear as placeholders. Very large messages, some older records, and replies without a final-response marker may be omitted.

### Delete sessions

1. Select the records to clean up. The table header checkbox selects the current filtered results; a group checkbox selects matching records within that group.
2. Click **Review deletion** and check the sessions, attached records, and estimated space in the plan.
3. Confirm permanent deletion and wait for the results. You do not need to type a confirmation phrase for each record.

**Deletion is irreversible. The tool provides neither a recycle bin nor automatic backups.** Changing filters does not clear previous selections. Check the selection summary and deletion plan before proceeding.

Deletion uses the official CLI. The tool checks session metadata, history indexes, and the original associated files afterward, rather than treating a successful command exit as proof of complete cleanup. Batch deletion runs sequentially. You can stop subsequent deletions, but completed deletions cannot be undone.

Codex can remain open. Current sessions, sessions in use, targets whose status cannot be verified, and records with conflicting file ownership are protected. The tool does not force Codex to close or release its locks.

### Clean up records with missing files

Choose **All files missing**, then use the table or group checkbox to select matching records. A healthy parent is not selected merely because a child's files are missing.

These records may remain after files were deleted manually. Because cleanup removes remaining session records, a successful result may reclaim **0 B**. Unreadable files and nonexistent files are different conditions and are not handled interchangeably.

Codex may compress a `.jsonl` rollout into `.jsonl.zst` while retaining the original database path. Both forms are checked. Compressed logs still contain session data, are counted at their actual compressed size, and are excluded from the all-files-missing filter. The list and deletion plan identify compressed logs; post-deletion verification checks both forms. Compressed logs without session metadata appear in scan diagnostics and are never deleted automatically.

Compressed sessions use paginated database history for previews. Without that history, the preview explains that data remains in the compressed log and should be viewed in Codex. Python 3.14's standard library or the optional `zstandard` module can decode bounded headers. Without a decoder, database-referenced compressed logs are still identified, counted, and verified; orphan ownership is never inferred from filenames.

## Database maintenance

Open **Database maintenance** at the top of the page to inspect database size and internal free space:

| Database | Main contents |
| --- | --- |
| `thread_history_1.sqlite` | Conversation turns, messages, and history indexes |
| `state_5.sqlite` | Session metadata, projects, and related state |
| `logs_2.sqlite` | Codex runtime diagnostic logs |

### Deleting records versus reclaiming space

Session deletion invokes the official command to remove the corresponding records. However, SQLite usually retains freed pages for future writes, so the database file may not shrink immediately.

Database maintenance compacts those pages to reclaim file space. Run it after cleaning up a batch of sessions; there is no need to compact after every deletion.

### Run maintenance

1. Select the databases to compact.
2. By default, all logs are retained and only unused space is reclaimed. To remove logs, choose to retain the most recent 7, 30, or 90 days, or remove all logs older than the plan's cutoff time.
3. Review the maintenance plan and confirm execution.
4. Check each database's result and the actual space reclaimed.

Maintenance preserves existing sessions and history. It does not delete a history record simply because matching session metadata is absent, and it does not delete entire database files.

Compaction requires temporary disk space. The tool reports database contention, insufficient space, or failed checks. Maintenance can be stopped, but committed log deletions are not rolled back. Maintenance, session deletion, and scanning cannot run concurrently.

## FAQ

### How do I clean caches, temporary files, and generated outputs?

Use the **File cleanup** tab. Directory and list placeholders appear immediately. Common cleanup directories are inspected first, and progress and completed directories stream into the page. Files can be previewed during inspection; recommendations and selection become available after all checks finish. The first inspection selects recommended items automatically; **Select recommended** reapplies the suggestions. The default retention is 7 days, with 30 and 90 days also available. Search paths, filter recommendations, and inspect the sizes of all top-level directories. Single files can be previewed directly. For directories containing multiple files, **View files** opens the complete searchable list, paginated at 100 files per page. Names are relative to the current directory. Images have thumbnails and an enlarged view; text files have content previews. **Open folder** is available on the main list, browser header, and selected file, opening the directory or selecting the file in Windows Explorer. Opening, searching, and paging reuse the inspected file inventory instead of rescanning the entire data directory. Single-file metadata appears immediately, while contents load independently in the preview pane. Deletion still revalidates the selection. Text previews read up to 256 KiB. PNG, JPEG, GIF, WebP, BMP, and ICO previews support images up to 16 MiB. HTML and SVG are shown as text. Both the file browser and enlarged image view have an upper-right × close icon and support Esc.

The list groups items by top-level folder by default, with a separate group for files in the root. Group headers show item counts, file counts, and sizes. Multi-item groups can be collapsed; group checkboxes select only matching eligible items and exclude protected ones. Group and table-header checkboxes reflect all currently matching items; unselected protected items produce a partial-selection state. Switch to a flat list if preferred. Grouping and collapsed groups are saved with your selection. Summary statistics appear in a compact status bar. The directory sidebar shows the total size and file count of each top-level directory, with search and navigation that expands the target group. Directories without cleanup items show a retention notice. On mobile, navigation appears above the list.

Recommendations cover old sandbox logs and command runners, selected tool caches, known staging directories, and failed atomic state writes. Current and recent runners, referenced paths, active tasks, links, unreadable items, and recent files are protected. Installed plugins, skills, authentication, rules, memories, and database files are retained.

File cleanup also discovers Windows Store and regular Codex desktop installations. Known browser caches under `LocalCache\Roaming\Codex` (or `%APPDATA%\Codex`) and diagnostic logs under `LocalCache\Local\Codex\Logs` (or `%LOCALAPPDATA%\Codex\Logs`) appear in **Codex desktop caches, logs and runtimes**, with their absolute paths. **Scanned storage usage** includes the entire Codex data directory plus identified desktop caches and logs, rather than the entire application package. Desktop logs are grouped by date and follow the 7/30/90-day retention period. Open files are never forcibly deleted.

Desktop caches include embedded-browser partitions' Service Worker `CacheStorage` and `ScriptCache`, HTTP caches, code caches, and GPU caches. They require manual selection: offline web resources will be removed and may be downloaded again. Open this tool in a separate browser, exit Codex, and inspect again before deleting caches. The running state is checked before and during execution. IndexedDB, Local Storage, Cookies, Service Worker databases, login information, application settings, and session data are excluded from this cache allowlist. Personal Edge browser data is not scanned.

The desktop group also lists known legacy executables, fingerprint directories and `cua_node` environments under `%LOCALAPPDATA%\OpenAI\Codex` and Store packages' `LocalCache\Local\OpenAI\Codex`. Manual selection requires no references in checked processes, PATH, startup registry entries, App Paths, scheduled tasks, services, desktop/Start menu shortcuts, startup scripts or common configuration, plus deployed successors verified against installed package hashes. Retention still applies; old runtimes are never auto-recommended. Installed versions, helpers sharing a referenced legacy executable's directory, incomplete audits, unknown directory contents and unverified replacements are retained. Planning and execution repeat the audit; deletion also checks file identity and refuses occupied files. No launch entries, PATH or processes are changed. Static checks cannot cover every project or dynamically constructed paths in arbitrary custom scripts; the deletion plan notes this limitation.

File cleanup confirmation, progress and results share one dialog. You can stop remaining deletions; reloading reconnects to progress. Browser-cache protection checks desktop application image paths, so running the Codex CLI alone does not block caches. Exit the desktop app before cleaning its active browser caches. If the desktop starts during cleanup, the remaining cache files are skipped as one group per source while unaffected items continue. Results count successful, failed, skipped and unprocessed files separately and group reasons with actual paths.

During cache deletion, desktop process checks run about every 100 milliseconds or after at most 32 cache file attempts, whichever comes first, and immediately when switching cache sources. This avoids enumerating all processes for every small file; file identity and open-handle checks still run individually.

Visualizations, generated images, attachments, plans, and configuration backups require manual selection. Review the deletion plan and confirm permanent deletion. The selection is rechecked before execution; changes, usage, or permission problems prevent deletion. Remaining cleanup can be stopped, but deleted files cannot be recovered. Lock files and category roots remain; only empty selected task or staging directories are removed.

The top navigation has **Sessions / Database maintenance / File cleanup**. Selections are saved per data directory and restored across tab changes and reloads. Session selections are reconciled only after a complete scan.

### Why can the deletion plan show a different size from the list?

A session row includes the file sizes of children known to the official session relationship data. Additional attached relationships recovered from log headers may not belong to the same official deletion scope. Selecting a parent also selects those attached records for the plan, so use the deletion plan as the final scope of the operation.

Session storage figures represent the logical sizes of JSONL files with confirmed ownership. They exclude shared databases, image attachments, and filesystem compression differences. Database maintenance measures database and WAL files separately. Concurrent Codex writes can also affect changes in actual free disk space.

### What are Scan issues?

These are findings such as missing files, read failures, unexpected paths, or uncertain ownership. Click **Scan issues** in the status bar to inspect them. Use **Recheck files** in that window when you need another scan. The issue count is neither a count of files ready for deletion nor an estimate of reclaimable space.

### Why are some records blocked from deletion?

A session may be in use by Codex, CLI deletion capability or session lock verification may have failed, permissions may be insufficient, or file ownership may be uncertain. Check the CLI status at the top, connection details in Settings, the deletion plan, or the execution result for the specific reason. The tool does not bypass these checks to delete files directly.

Session activity updates automatically about every 6 seconds; you do not need to quit Codex entirely. After updating the CLI, use **Recheck files** in **Scan issues**, or save Settings, to verify it again. Closing Codex does not resolve a verification failure.

### Does changing the language change my conversations?

No. Only the interface changes. Session titles, messages, project names, and paths remain in their original language. On first use, a Chinese browser language selects Chinese; other languages select English. A saved manual choice takes precedence.

## Development

The backend uses the Python standard library. The frontend uses vanilla JavaScript, HTML, and CSS.

```text
app.py          Local HTTP service and startup entry point
cleaner/        Session scanning, official CLI cleanup, and database maintenance
web/            Pages, styles, and frontend logic
web/locales/    Chinese and English language resources
tests/          Automated tests and development verification scripts
```

Run the automated tests:

```powershell
python -m unittest discover -s tests -v
```

Browser verification scripts use Playwright. Node.js and Playwright are needed only for development checks. Read each script's service address, mocked endpoints, and environment-variable configuration before running it. The isolated official CLI verification script, `tests/probe_official_delete.py`, creates and deletes temporary test sessions.

When adding interface text, update both `web/locales/zh-CN.json` and `web/locales/en.json`. Do not commit local Codex data, conversation content, or debug screenshots containing private information.

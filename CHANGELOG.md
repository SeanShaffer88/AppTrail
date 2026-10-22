# Changelog

## 0.3.0 — 2026-10-21

- Rename snapshots and add searchable build/commit/test notes without changing evidence hashes.
- Move old snapshots to Trash, restore them, or permanently delete library copies after confirmation.
- Migrate existing v0.2 catalogs in place and preserve annotations on duplicate imports.
- Set a known-good baseline per application folder and compare later builds against it directly.
- Include snapshot names, notes, and baseline markers in exported HTML reports.
- Recover staged deletion operations after an interrupted exit.

## 0.2.0 — 2026-10-21

- Automatically save new desktop captures to a persistent local snapshot history.
- Browse and filter snapshots by application, folder, or date.
- Compare two history rows directly, or choose Before and After separately.
- Import existing JSON snapshots as owned copies, deduplicating identical imports.
- Flag missing library files and reject files modified outside the application.
- Preserve manual JSON export/import and the source CLI.

## 0.1.0 — 2026-10-21

- Capture application folders with SHA-256 hashes, sizes, and timestamps.
- Inspect PE architecture, ordinary/delay DLL imports, and Windows file versions.
- Compare saved snapshots and inspect before/after file evidence.
- Export self-contained HTML reports with capture limitations.
- Provide a native desktop interface, source CLI, and standalone Windows x64 executable.
- Include automated tests and pinned Windows packaging instructions.

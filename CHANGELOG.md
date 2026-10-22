# Changelog

## 0.8.0 — 2026-10-21

- Literal search across both side-by-side saved snapshots, with optional case matching.
- All-match and active-match highlights, match counter with snapshot side/original line number, and wrapped previous/next navigation.
- Ctrl+F focuses search; F3/Shift+F3 and Enter/Shift+Enter navigate. Clear or Escape in the search field clears results.
- Offscreen matches scroll into view; search survives theme, word-highlight, and line-ending toggles. Match limit is explicit.

## 0.7.0 — 2026-10-21

- Word-level highlighting within paired modified lines, including numbers, punctuation, whitespace, and Unicode identifiers.
- Stronger changed-region backgrounds in dark/light themes preserve syntax colors. A toggle switches back to line-only shading.
- Changed line-ending markers are emphasized when visible. Bounded fallback handles very long or repetitive input.

## 0.6.0 — 2026-10-21

- Terminal-inspired dark theme by default, with a persistent dark/light toggle at the top right. Diff and snapshot notes windows update with the app theme.
- Offline Pygments syntax colors in side-by-side source/config diffs, including multiline context and Unicode-aware text ranges. Unknown formats stay plain text.
- Preserved change backgrounds, line numbers, navigation, and line-ending markers. Pygments is pinned and its BSD license bundled in portable releases.

## 0.5.0 — 2026-10-21

- Default side-by-side saved-text diff with original line numbers, aligned spacer rows, red/green highlights, and synchronized vertical scrolling.
- Previous/Next change buttons and Shift+F7/F7 shortcuts, with change position and wraparound navigation.
- Unified view, metadata, and line-ending markers remain available. No snapshot schema change.

## 0.4.0 — 2026-10-21

- Save bounded source/config text with new snapshots and show color-coded unified diffs in file details.
- Display line-ending, encoding, BOM, and missing-final-newline evidence; optionally show line-ending markers.
- Include escaped saved-text diffs in HTML reports, with an explicit report size budget.
- Introduce v2 snapshots with text capture policy and hash-verified payloads; retain v1 reading without inventing missing text.
- Add desktop capture opt-out and CLI --no-text, source/config allowlists, common credential exclusions, and per-file/snapshot budgets.

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

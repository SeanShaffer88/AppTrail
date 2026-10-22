# Changelog

## 0.16.0 — 2026-10-21

- Named project checkpoints with saved exclusion patterns, optional source capture, and local Git commit/branch/author/date/working-tree details.
- One-click comparison of a selected checkpoint against its current project folder, reusing its capture policy and preserving both observations in history.
- Git and exclusion evidence in comparison HTML reports; existing history, notes, Trash, and text diffs remain compatible.

## 0.15.0 — 2026-10-21

- Expand all unchanged / Collapse all unchanged buttons in exported side-by-side reports, with a live section counter.
- Search/navigation reopen hidden matches after collapse, while source text, colors, and exported settings remain intact. Buttons disable when no sections exist.
- CI uploads temporary build artifacts only for manual workflow runs, with one-day retention; release downloads remain available.

## 0.14.0 — 2026-10-21

- Offline search and previous/next match and change controls in exported side-by-side HTML reports, with counts and keyboard shortcuts.
- Literal search preserves syntax/word markup, reveals collapsed matches, supports case matching, and wraps through both snapshots.
- One fixed embedded script is authorized with a CSP hash; captured text stays escaped. Reports remain readable without JavaScript.
- Real Edge browser regression checks cover navigation, Unicode/token-boundary queries, whitespace/marker exclusions, match limits, and offline behavior.

## 0.13.0 — 2026-10-21

- Export the current file’s side-by-side diff to a self-contained HTML report.
- Preserve syntax colors, word-level changes, line numbers, theme, line endings, whitespace filtering, context size, expanded/collapsed sections, and current search highlights.
- Native HTML expandable sections reveal hidden code in both snapshots without scripts or network requests. Escaped captured content and encoding/hash summaries are included.

## 0.12.0 — 2026-10-21

- Remember collapsing unchanged lines, ignoring whitespace-only changes, showing line endings, word-level highlighting, and search case matching for new diff windows and future sessions.
- Restore saved options on first render without overwriting preferences. Both enabled and disabled values persist; strict boolean validation retains safe defaults for malformed settings.
- Updates preserve context size, theme, and unrelated settings. Save failures report a window-only change. Individual expanded sections and search queries remain temporary.

## 0.11.0 — 2026-10-21

- Context lines setting (0–100, default 3) alongside collapsed diff controls. Applies immediately and is remembered for new diff windows and future sessions.
- Preference updates preserve theme and unrelated settings. Invalid or malformed values safely revert to defaults/previous values, and save failures are reported without losing the current view.

## 0.10.0 — 2026-10-21

- Optional collapse of long unchanged sections in side-by-side diffs, keeping three context rows around changes.
- Inline expand buttons reveal a section in both panes; Expand all and Collapse again control the full view. Original line numbers and source evidence are preserved.
- Search reveals hidden matches automatically. Folding works with syntax/word colors, line-ending toggles, and whitespace filtering.

## 0.9.0 — 2026-10-21

- Optional Ignore whitespace-only changes filter in the side-by-side toolbar, off by default.
- Whitespace-normalized alignment suppresses formatting-only highlights/navigation while preserving saved text, original line numbers, and search. Inserted blank lines no longer displace real lines during filtered alignment.
- Status shows ignored rows. Non-whitespace edits and whole-file additions/removals remain changes. Exact unified diffs, reports, evidence, and file counts are retained.

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

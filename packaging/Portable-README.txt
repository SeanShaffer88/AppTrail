AppTrail 0.4.0 — Windows x64 portable edition

Source and updates: https://github.com/SeanShaffer88/AppTrail
AppTrail source is MIT licensed. See licenses/AppTrail-MIT.txt.

Double-click AppTrail.exe. No Python installation, command window, administrator
access, or installer is needed. You can move the EXE to another folder.

1. Choose an application folder and click Capture to history.
2. Capture the folder again after changes. Both captures stay in Snapshot history.
3. Select two history rows (Ctrl-click) and click Compare selected (2).
4. Click Export HTML report to save a readable report.

Text diffs:
- Leave Capture source/config text for diffs enabled for new captures.
- In Comparison, double-click a file or choose View text diff to see saved changes.
- Green lines are added, red lines removed. Show line endings displays CRLF/LF/CR
  and missing-final-newline markers. Encoding/BOM details are shown above the diff.
- Text is limited to 256 KiB and 3,000 lines per eligible file, 8 MiB per snapshot.
  UTF-8 and BOM-marked UTF-16/UTF-32 are supported. Skipped text has a reason.
- Common credential filenames and .git contents are excluded, but other config
  files can contain secrets. Snapshots/reports may contain private code or secrets;
  review before sharing or disable text capture. Source CLI: --no-text.
- Older v1 snapshots remain readable but do not contain reconstructable text.
  Capture two new snapshots for a complete diff. New v2 JSON needs AppTrail 0.4+.

Use Import JSON to bring existing snapshots into history. Imports keep a local
copy and identical imports are deduplicated. Save JSON also creates a history
entry. Use as Before / Use as After lets you choose comparison order manually.
The history library persists across restarts in:
%LOCALAPPDATA%\AppTrail\history
It contains snapshot JSON files and a SQLite catalog. It is separate from the
portable EXE; moving or updating the EXE keeps the same user's history.

Organization and development baselines:
- Double-click a history row or choose Edit name & notes to label a build and
  record commit IDs, test results, or the reason for a capture. Search includes notes.
- Mark a known-good capture as baseline. Select another capture from the same
  folder and choose Compare with baseline. Names and notes appear in HTML reports.
- Move old captures to Trash. Show Trash lets you restore selected captures or
  permanently delete them after confirmation. Original imported files are untouched.
- Metadata edits do not alter evidence hashes. Existing v0.2 catalogs upgrade
  automatically; names and notes live in the catalog, not exported snapshot JSON.

The EXE contains Python and Tcl/Tk and extracts its runtime into a temporary
directory while running. First launch can take a few seconds. The temporary
runtime is normally removed when AppTrail closes. Snapshots and reports stay
where you save them. No network connection is required for AppTrail itself.

This release was tested on the build computer's Windows x64 installation.
It has not been certified on all Windows versions. It is not an ARM64-native
or 32-bit build. This build is unsigned.

Capture is sequential, not an atomic backup. Close the target application when
practical. Files that cannot be read reliably are flagged. Reparse points are
skipped. Renames appear as removal and addition. Static imports do not prove
which DLLs loaded or caused a failure. Reports contain local paths and metadata;
review before sharing. Only bounded eligible text contents are saved; this is
not a complete backup or restore tool.

Runtime notices are in licenses/Python-and-bundled-components.txt and are also
embedded in the EXE. Keep the notices with copies you redistribute.
SHA256SUMS.txt records the checksum of the executable.

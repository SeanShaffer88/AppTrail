AppTrail 0.1 — Windows x64 portable edition

Source and updates: https://github.com/SeanShaffer88/AppTrail
AppTrail source is MIT licensed. See licenses/AppTrail-MIT.txt.

Double-click AppTrail.exe. No Python installation, command window, administrator
access, or installer is needed. You can move the EXE to another folder.

1. Choose an application folder and save a baseline snapshot outside that folder.
2. Capture the folder again after changes; use a different snapshot filename.
3. Choose the Before and After snapshots and click Compare snapshots.
4. Click Export HTML report to save a readable report.

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
review before sharing. File contents are not backed up.

Runtime notices are in licenses/Python-and-bundled-components.txt and are also
embedded in the EXE. Keep the notices with copies you redistribute.
SHA256SUMS.txt records the checksum of the executable.

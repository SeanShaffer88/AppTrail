# AppTrail

**See what changed in a Windows application folder.** Capture a working baseline, compare it after an update, and export a readable report with the evidence.

[Download for Windows x64](https://github.com/SeanShaffer88/AppTrail/releases/latest) · [Report a bug](https://github.com/SeanShaffer88/AppTrail/issues) · [MIT license](LICENSE)

## Download and run

1. Open the [latest release](https://github.com/SeanShaffer88/AppTrail/releases/latest).
2. Download **AppTrail-0.1-Windows-x64.zip**, extract it, and double-click **AppTrail.exe**. A direct EXE download is also available.
3. No Python installation, command window, administrator access, or account is required. Keep the license notices with copies you redistribute.

The current executable is an unsigned Windows x64 build, tested on Windows 11 x64. Other Windows versions and native ARM64 execution have not been validated. The bundled runtime extracts into the temporary directory at launch and normally cleans up on exit.

## Capture, compare, report

1. Choose an application folder and save a baseline snapshot **outside that folder**.
2. After making changes, capture the folder again using a different snapshot filename.
3. Select the **Before** and **After** snapshots and click **Compare snapshots**.
4. Double-click a file to inspect its evidence, or click **Export HTML report** to save a standalone report.

You can compare the same application in different folder locations or on different computers. File matching uses case-insensitive relative paths, following normal Windows conventions. AppTrail runs locally; it has no telemetry or cloud upload feature.

Try the included [before](examples/before.json) and [after](examples/after.json) example snapshots, or download the [example HTML report](examples/AppTrail-example-report.html). Example root paths are illustrative.

## What it captures

| Evidence | Details |
| --- | --- |
| File identity | Relative path, size, last-write time, and streaming SHA-256 hash |
| PE binary metadata | Machine architecture, imported DLL names, and delay-imported DLL names |
| Windows file version | Fixed file-version resource when present |
| Capture issues | Read errors, skipped reparse points, malformed metadata, and detected changes during capture |

Comparison results distinguish **Added**, **Removed**, **Modified** (different content hash), **Metadata** (same hash, changed metadata), **Unchanged**, and **Unknown** (unreliable content comparison).

HTML reports include before/after hashes, metadata, capture warnings, and UTC timestamps. They use no external assets or scripts and can be printed to PDF from a browser.

## Run from source

Requires **Python 3.11 or later with Tkinter**. There are no third-party runtime packages. The packaged GUI release uses Python 3.15.

```powershell
git clone https://github.com/SeanShaffer88/AppTrail.git
cd AppTrail
python -m apptrail
```

On Windows you can also double-click `Launch-AppTrail.pyw`, if `.pyw` files are associated with Python, or use `Launch-AppTrail.cmd`.

### Command line

The CLI is provided by the source distribution; the packaged EXE opens the desktop interface.

```powershell
python -m apptrail snapshot "C:\Path\To\Application" -o "C:\Snapshots\before.json"
python -m apptrail snapshot "C:\Path\To\Application" -o "C:\Snapshots\after.json"
python -m apptrail compare "C:\Snapshots\before.json" "C:\Snapshots\after.json" -o "C:\Snapshots\report.html"
```

Snapshot exit codes: `0` = captured without issues; `2` = saved with capture issues; `1` = failed. Compare returns `0` on successful report export, including when differences exist. Always read capture warnings.

## Development and Windows builds

Run the test suite from the repository root:

```powershell
python -m unittest discover -s tests -v
```

To build the standalone EXE, use 64-bit Python 3.15 on Windows:

```powershell
python -m venv work\build-env
work\build-env\Scripts\python.exe -m pip install -r packaging\requirements-build.txt
work\build-env\Scripts\python.exe packaging\build_windows.py --work-dir work\package --output-dir dist\AppTrail-Windows-x64
```

The build produces a windowed single-file EXE, runtime license notices, version metadata, a SHA-256 checksum, and a portable ZIP beside the output directory. The original Python distribution's `LICENSE.txt` is required. Build tooling is not needed to run the packaged application. The [Windows CI workflow](.github/workflows/windows.yml) tests Python 3.11 and 3.15 and builds a downloadable artifact on Python 3.15.

## Limitations

- This is a diagnostic snapshot tool, not a backup or restore tool. It does not save file contents.
- Capture is sequential, not atomic. Close the target application where practical. AppTrail detects size, last-write time, or file identity changes during capture but cannot detect every concurrent modification. Traversal may miss newly created or deleted files.
- Symlinks, junctions, and other reparse points are skipped. This is not a security boundary against a hostile process changing paths during a scan. Empty directories, permissions, alternate data streams, and external dependencies are not captured.
- Added/Removed means present only in one capture; access failures can produce apparent removals. Renames appear as removal and addition.
- Static imports do not establish runtime load paths or missing dependencies. Architecture is the PE machine field, not a compatibility verdict; managed AnyCPU behavior is not inferred.
- The bounded PE reader supports common PE32/PE32+ metadata and reports malformed or unsupported metadata rather than attempting recovery. Signature verification, import symbol resolution, registry capture, and runtime tracing are not included.

Snapshots and reports contain local paths and binary metadata. Review them before sharing. Keep snapshots outside the application folder and use different filenames to preserve history.

## Contributing

Bug reports and focused improvements are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). Include reproduction steps and capture warnings; remove private paths or data from anything you attach.

AppTrail source is licensed under [MIT](LICENSE). Bundled Python and Tcl/Tk retain their own licenses; runtime notices are included in the portable release and embedded in the EXE.

## Technical references

AppTrail uses Python's standard library: Tkinter, hashlib, JSON, mmap, and ctypes. PE structures follow [Microsoft's PE specification](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format). Packaging uses [PyInstaller](https://pyinstaller.org/en/stable/usage.html).

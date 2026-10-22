# Contributing to AppTrail

Open an issue to describe a bug or discuss a larger change. Focused pull requests are welcome.

## Local development

Use Python 3.11 or later with Tkinter. Install the pinned Pygments runtime dependency before running from source.

```powershell
python -m pip install -r requirements.txt
python -m apptrail
python -m unittest discover -s tests -v
```

For Windows packaging, follow the pinned build instructions in the README. Keep generated binaries, snapshots of real applications, virtual environments, and build files out of commits.

## Reporting a bug

Include your Windows version, AppTrail version, reproduction steps, expected behavior, and the actual result. Capture warnings are particularly helpful. Use small synthetic fixtures where possible. Snapshots and reports can reveal private paths and metadata; sanitize attachments before posting them publicly.

## Pull requests

Explain the problem and resulting behavior. Add tests for substantive scanner, parser, or comparison changes. Run the test suite and describe any manual desktop checks. Keep runtime dependencies minimal and preserve the distinction between observed differences and a proven failure cause.

Contributions are provided under the repository's MIT license.

## Exported report browser tests

With Node.js 20+, Microsoft Edge, and Playwright 1.62.1 available, generate the synthetic fixtures and run `node tests/report_browser.cjs work/browser-report.html`. Generate fixtures first with `python tests/make_browser_fixture.py work/browser-report.html`. Set `APPTRAIL_PLAYWRIGHT` to an absolute Playwright module path if it is not installed on the normal Node module path. CI installs the pinned test-only package into work/browser-tools and uses the runner’s existing Edge browser. This adds no application runtime dependency. The checks verify the actual embedded CSP-authorized script, including offline behavior and the script-disabled fallback.

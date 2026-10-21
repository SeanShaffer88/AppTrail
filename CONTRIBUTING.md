# Contributing to AppTrail

Open an issue to describe a bug or discuss a larger change. Focused pull requests are welcome.

## Local development

Use Python 3.11 or later with Tkinter. No pip runtime dependencies are required.

```powershell
python -m apptrail
python -m unittest discover -s tests -v
```

For Windows packaging, follow the pinned build instructions in the README. Keep generated binaries, snapshots of real applications, virtual environments, and build files out of commits.

## Reporting a bug

Include your Windows version, AppTrail version, reproduction steps, expected behavior, and the actual result. Capture warnings are particularly helpful. Use small synthetic fixtures where possible. Snapshots and reports can reveal private paths and metadata; sanitize attachments before posting them publicly.

## Pull requests

Explain the problem and resulting behavior. Add tests for substantive scanner, parser, or comparison changes. Run the test suite and describe any manual desktop checks. Keep runtime dependencies minimal and preserve the distinction between observed differences and a proven failure cause.

Contributions are provided under the repository's MIT license.

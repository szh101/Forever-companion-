# Checks, builds and publication

The source repository is [szh101/Forever-companion-](https://github.com/szh101/Forever-companion-).
It contains a desktop companion and an addon, with no cloud deployment target.
Use `origin` for that repository and `main` for the integration branch. Fetch
before development, preserve other contributors' changes and work on task branches.
Do not force-push or change repository visibility as part of a routine release.

## Source checks

Install [uv](https://docs.astral.sh/uv/) and run from the repository root:

```sh
uv run --locked --group dev python scripts/check.py
```

This runs deterministic Python and Lua contract tests. Keep platform-specific
skips visible in the results. Tests use synthetic data and do not establish real
game compatibility, capture behavior or live model access.

On macOS, also compile the native ScreenCaptureKit component:

```sh
uv run --locked python scripts/build_native.py
```

`.ai-pipeline.json` preserves both checks for a macOS runner. Its `/private/tmp`
cache is a build-tool cache, not a source or user-data path. The external
`ai-pipeline` runner is optional infrastructure and is not distributed in this
repository; contributors can run the commands above directly. Do not copy its
macOS cache path into Windows commands.

For Windows background testing, use an isolated checkout with project
dependencies installed and run:

```powershell
.venv\Scripts\pythonw.exe scripts\windows_quiet.py --report .runtime\windows-quiet.json
```

Read the completed JSON report. Starting the process is not evidence of a pass.
See [background checks](windows-test-handoff.md) for the no-interference boundary.

## Review and integration

Record the exact source revision and results for a pull request or release.
Review the tracked files and commit identity for private data before pushing.
Never commit credentials, screenshots, transcripts, game snapshots, virtual
environments, test receipts or build products. Use a GitHub noreply email for
public commits and keep local receipts under ignored `.runtime` or `dist` paths.

Shared Python/UI changes need checks on both supported platforms before normal
main integration and release. Windows-only results cannot substitute for macOS
checks, including the native build. If a platform is unavailable, publish the
review branch with that limitation stated and leave its integration check pending.
The independent public source snapshot retains the verification limits documented
in [verification.md](verification.md); it is not a new claim of platform acceptance.

Confirm the remote revision and source tree after publishing. Keep source upload,
binary packaging, live testing and installation as separate reported outcomes.

## Application packages

Build from a fixed Git commit rather than an uncommitted working tree:

```powershell
# Windows x64, with the build dependencies and native toolchain installed
.venv\Scripts\python.exe -X utf8 scripts\build_windows.py --commit FULL_COMMIT_SHA
```

```sh
# macOS, with the native toolchain installed
uv run --locked --group dev --group bundle python scripts/build_macos.py --commit FULL_COMMIT_SHA
```

Build outputs stay in `dist`. Windows packaging includes the native capture
component and runs the packaged application's hidden self-test. macOS packaging
uses a temporary signature and strict signature verification; that is not Apple
notarization. Neither build automatically publishes a release or installs itself
on another computer. Report available signed/notarized packages honestly.

Visible UI, real game capture, addon behavior and model requests require separate
testing. Never infer those results from a build or hidden check. Release download
instructions must match assets that have actually been uploaded.

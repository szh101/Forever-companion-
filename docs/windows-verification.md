# Windows verification scope

The 0.4.3 release passed **161 checks: 160 passed,
1 skipped**, with no failures or errors. The full hidden GUI check also passed.
The skipped case is the generic symlink test; Windows-specific junction and
hard-link rejection tests ran and passed, including files addressed through Windows
8.3 short path aliases.

The released installer is [v0.4.3-windows.2](https://github.com/szh101/Forever-companion-/releases/tag/v0.4.3-windows.2),
built from `c6ada6424c2f73cbca1adb9503f4dbfabaec8fa1`. Both jobs in
[the release workflow](https://github.com/szh101/Forever-companion-/actions/runs/38534145251)
completed successfully.

[Source checks](https://github.com/szh101/Forever-companion-/actions/runs/38533867098)
also passed on Windows and macOS, including English control labels, narrow-window
wrapping, hidden UI behavior and the Windows application entry point. macOS
passed 155 of 161 contracts with six Windows-specific skips, native compilation
and clipboard-image checks on a private synthetic pasteboard.

## Covered by offline checks

- Python request and response contracts, bounded snapshot import, image parsing,
  provider isolation and Lua addon behavior with synthetic APIs/data.
- Windows path validation, CLI discovery and process options using test doubles,
  and temporary attachment cleanup on success, failure and timeout.
- One-shot screenshot attachment and clipboard-image encoding using mocked
  capture and clipboard services; stale completion and clipboard failure cases.
- Compact UI state, snapshot import feedback, preserved drafts, synthetic chat
  and images, settings, collapse/expand and chat-scroll routing in hidden Tk.
- Passive overlay routing, signed wheel deltas, drag state, input activation and
  first-click focus handoff through mocked native events and window identities.

The tests do not install native hooks, operate the game, read or replace the
real clipboard, display a visible assistant or send real provider requests.
The automated tests exercise behavior contracts; they do not reproduce every
Windows input mode or game presentation mode.

## Installer and download checks

The packaged application passed its hidden self-test, and the bundled capture
helper passed a synthetic bitmap test without starting a capture session. Nine
installer checks passed on an isolated Windows runner: invalid client rejection,
missing game executable rejection, Interface-file rejection, fresh installation,
exact bundle bytes, update backup, AddOn opt-out, junction rejection, and uninstall
preservation of the AddOn and its backup. The fixture used a synthetic client with
spaces and Chinese characters in its path; no game executable was run.

The privacy scanner decoded the application archives and inspected 1,413 items
and 11,980 code objects with no findings. Its installer scan is raw-file-only;
the installation check separately verified that installed application files
matched the deeply scanned bundle byte for byte.

All four public release assets were downloaded without authentication. Their
sizes and SHA256 digests matched GitHub metadata; the three payload files also
matched SHA256SUMS.txt. Both ZIPs passed integrity checks, and the portable
application's source record matched the release commit. This download check did
not execute the installer locally.

## Still requires separate validation

- Visible window layout and behavior at supported display scales.
- Physical scrolling, dragging, background click-through and first-click keyboard
  handoff while the game is running, including any fullscreen limitations.
- Actual Windows Graphics Capture frames, occluded/minimized windows and HDR.
- Actual client addon loading, `/fai` export and native Ctrl+C copying.
- Live Codex/API connectivity and supported models on the user's account.
- macOS visible UI and real capture. The macOS Python/Lua contracts and native
  compilation passed on the release runner.

Installation and build instructions are in [Windows usage](windows.md).
Run the background checks as described in [Windows test handoff](windows-test-handoff.md)
and read the final report. `realCaptureTested:false` and `liveApiTested:false`
must remain false when only offline checks ran. Source checks, packaged self-tests,
visible testing and installation are distinct results.

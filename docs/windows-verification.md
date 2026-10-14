# Windows verification scope

The companion implementation in this snapshot passed **155 checks: 154 passed,
1 skipped**, with no failures or errors. The full hidden GUI check also passed.
The skipped case is the generic symlink test; Windows-specific junction and
hard-link rejection tests ran and passed.

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

## Still requires separate validation

- Visible window layout and behavior at supported display scales.
- Physical scrolling, dragging, background click-through and first-click keyboard
  handoff while the game is running, including any fullscreen limitations.
- Actual Windows Graphics Capture frames, occluded/minimized windows and HDR.
- Actual client addon loading, `/fai` export and native Ctrl+C copying.
- Live Codex/API connectivity and supported models on the user's account.
- macOS regression tests and native build for the recent shared UI changes.

Installation and build instructions are in [Windows usage](windows.md).
Run the background checks as described in [Windows test handoff](windows-test-handoff.md)
and read the final report. `realCaptureTested:false` and `liveApiTested:false`
must remain false when only offline checks ran. Source checks, packaged self-tests,
visible testing and installation are distinct results.

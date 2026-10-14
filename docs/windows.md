# Forever AI for Windows

Forever AI 0.4.3 for Windows x64 shares its application logic with the macOS
version. The application interface is English. The main chat window is
320 × 380 logical pixels and follows Windows display scaling; at 200% scaling,
its client area is 640 × 760 pixels. Settings open separately. Shift+Enter sends
a message, Enter inserts a line, and the window can stay on top or collapse.
Screenshot capture is off by default.

This guide is included in the Windows package as `Windows-guide.md`.

## Install and start

Download [ForeverAI-Setup-x64.exe](https://github.com/szh101/Forever-companion-/releases/latest/download/ForeverAI-Setup-x64.exe).
The English or Simplified Chinese setup wizard installs the Companion and can
also install the AddOn into your selected Forever client. Python and the capture
helper are included. For a first AddOn installation, fully restart the game when
convenient so that it loads the new AddOn. Setup does not restart the game.

During AddOn updates, setup keeps the previous AddOn folder in the client's
`Interface/ForeverAI-backups` directory. Uninstalling the Companion preserves the
game AddOn and those backups.

For the portable ZIP, keep the entire `Forever AI` folder and open `Forever AI.exe`.
Python is included. The `_internal` directory is part of the application; copying
only the executable will not work. Public Windows installers are unsigned, so
Windows may display an unknown-publisher or reputation notice. See the
[README](https://github.com/szh101/Forever-companion-/blob/main/README.md) for the
download choices and first-use steps.

## Window controls

Hover over an icon to see its name. The gear opens **Settings**, the pin controls
**Keep on top**, the arrow switches between **Collapse** and **Expand**, the
clipboard pastes an AddOn snapshot, the paper plane sends a message, and the cross
closes Forever AI. Drag the handle at the upper left to move the window, or the
diagonal handle at the lower right to resize it.

Chat and input use 10-point text. The dark background, warm gold accents and
highlighted input border are shared with Settings. Settings use a fixed heading
and scrollable cards, with descriptions that wrap to the available width. The
default Settings size is 420 × 620 logical pixels. Under **Appearance**, set
**Opacity** from 45% to 100%; the default is 92%. This setting affects the chat
window and is kept only for the current run.

On Windows, clicks on the main window's background and ordinary chat text pass
through to the window underneath. The input box, buttons, scrollbar, images and
links retain their own mouse areas. Hovering over chat text or its scrollbar lets
the mouse wheel scroll history without taking keyboard focus. Wheel handling
also supports mouse tools whose events carry Windows' injected-event flag, while
preserving the controls' own scrolling and ordinary-window behavior.

Click the input box to type. Moving the pointer outside does not end typing.
Clicking the previously focused game window ends input and returns control on
that first click, while keeping the unsent draft. Sending a message or pressing
Esc in the input box also attempts to return focus to the previous window if it
is still visible and its window and process IDs match.

Focus returns only after checking the actual click target and the saved window
and process IDs. Hovering does not change focus. The application does not swallow
or replay game clicks, and does not pull focus back to the game after you have
switched to another application. Focus changes run on the Companion's UI thread.
Settings and image previews behave as ordinary windows. If the overlay cannot
initialize, the app restores an ordinary window and explains the failure in its
status area.

The overlay uses a main window that passes mouse hit tests through and small,
non-activating windows for its controls, forwarding their events to Tk. A mouse
hook handles chat scrolling, control dragging and clicks back to the previous
window during input. Dragging also uses control movement events and bounded
mouse-position/button-state sampling after a press. The drag handle also works
in ordinary-window mode. There is no keyboard hook, game input synthesis or game
content access. Hook callbacks queue bounded events and do not call Tk. Hidden
tests do not start native overlay windows or hooks.

The implementation follows Microsoft's
[layered-window hit-test rules](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features#layered-windows)
and [non-activating mouse behavior](https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-mouseactivate).
Click targets are checked with
[WindowFromPoint](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-windowfrompoint),
and focus returns through
[SetForegroundWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow).
Actual game focus, click-through, dragging and scrolling need separate user
validation. Exclusive fullscreen, raw input and operating-system restrictions
can affect their behavior.

## Connect AI

When the official Codex CLI is detected, **Codex (signed in)** is selected by
default. The official CLI manages authentication. Windows first checks the CLI
on PATH, then `%USERPROFILE%\AppData\Local\OpenAI\Codex\bin\*\codex.exe`.
This supports Microsoft Store installations that have a CLI binary but do not
expose it through the desktop launch environment's PATH.

Discovery does not hard-code a version directory or change PATH. It does not
require another installation or sign-in just because the CLI was found outside
PATH. The selected CLI must still pass the isolation and ChatGPT sign-in checks.
If only the desktop app is installed and no CLI binary exists, the Companion
reports that the CLI was not found.

OpenAI, Gemini and Claude use API keys, which stay only in the current process's
memory. Do not provide login tokens to third-party applications. **Offline demo**
uses fictional quests and a programmatically drawn image; it makes no model
request.

**Check Codex sign-in** distinguishes launch failures, timeouts, missing isolation
options and sign-in check failures, and shows the CLI path used. It recommends
updating only when the help command exits successfully but required options are
missing. It never removes isolation options and retries.

The most recent failed check writes a diagnostic to
`%USERPROFILE%\AppData\Local\ForeverAI\Diagnostics\codex-probe.json`. It contains
only the time, CLI path, failure stage, exit code, missing options and output byte
counts. It excludes raw output, sign-in details, keys, prompts, snapshots and
conversations. If the directory cannot be written, the original error still
appears in the app.

## Import a game snapshot

In game, `/fai` prepares the snapshot in a selected copy field. Press Ctrl+C,
then click **Paste AddOn snapshot** in the Companion. Wait for **Import
successful** and the quest count, then ask your question. Export and paste again
when quests change.

A newly installed AddOn loads on a full game launch. An update to an already
loaded AddOn can usually be loaded with `/reload` when convenient. Copying files
and passing mock tests do not establish that the real client's export behavior
has been verified. Use your own game installation directory.

Companion 0.4.3 uses AddOn 0.3.0. When updating the AddOn manually, copy all three
files: `ForeverAI.toc`, `ForeverAI.lua` and `Snapshot.lua`. Open the relevant bank,
profession or other game window before exporting when you need that information.
See the [snapshot guide](https://github.com/szh101/Forever-companion-/blob/main/docs/snapshot.md)
for fields and availability limits.

## Attach screenshots

The **Capture & paste · next message** icon beside **Paste AddOn snapshot** first
captures the WoW window, then copies the image to the Windows clipboard and
attaches it to the next message. It works independently of automatic capture and
turns automatic capture off after a successful screenshot. It does not open a
preview or capture the desktop.

An existing window selection is kept. If no window is selected, the button finds
and selects the first detected WoW window. If none is found, nothing is captured.
When running multiple clients, select the intended window under **Game
screenshots** in Settings. Attachments expire after two minutes and must be
captured again.

If the clipboard is busy, the captured image can still be sent with the next
message. Copied screenshots remain on the system clipboard. Windows clipboard
history and synchronization follow your system settings; the Companion does not
read or change those settings.

Window capture uses Windows Graphics Capture, directly bound to the selected
game window, replacing the earlier GDI capture method. Each request takes one
frame and ends. A system capture border may briefly appear. The Companion does
not activate, move or restore the game window. Minimized, closed or resized
windows and capture timeouts produce errors; capture never falls back to the
desktop. Overlays drawn by the game itself remain part of its picture. HDR and
exclusive fullscreen behavior need separate testing.

The Companion does not automatically capture the desktop, control your
character, read game memory, execute model output or send replies into game
chat. It does not save API keys or conversations. Codex CLI temporary input
images and its generated artifacts follow the data-handling limits in the
[README](https://github.com/szh101/Forever-companion-/blob/main/README.md).

## Development and packaging

Use Windows x64 Python 3.11 with Tcl/Tk. In an isolated project directory, run:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-windows-build.txt
.venv\Scripts\python.exe scripts\build_windows_capture.py
.venv\Scripts\pythonw.exe scripts\windows_quiet.py --report .runtime\windows-quiet.json
.venv\Scripts\python.exe -X utf8 scripts\build_windows.py --commit FULL_COMMIT_SHA
```

Read the completed JSON report; a started process is not a passing result.
Windows checks cover directory junctions, hard links, CLI console suppression,
npm shims, temporary attachment cleanup and DPI handling. Keep the macOS checks
and shared publication configuration.

Some execution sandboxes restrict Windows final-file-path APIs or junction
creation. Record that limitation and run the same offline checks in a normal
Windows process; do not weaken path validation. The generic symbolic-link test
may still be skipped depending on the platform.

The packager exports a fixed Git commit, runs contract and hidden GUI checks,
builds an executable without a console window, then runs that executable's
`--self-test-report` check. Outputs and the build manifest are stored in
`dist/windows-<commit>/`. It compiles `native/WindowsCapture.cs` from the same
source revision and bundles the capture helper with the app.

Compilation uses the local .NET Framework compiler, Framework reference
assemblies and Windows WinMetadata. Missing reference assemblies stop the build;
the build does not install a toolchain automatically. No C++ compiler is needed.
For source runs, the capture helper is
`.runtime/native/forever-capture-windows.exe`.

The hidden self-test uses fictional snapshots and mock clipboard functions. It
does not read or change the system clipboard, access a game or use the network.
Build logs stay in ignored `.runtime` paths. Record visible UI, live model and
actual game capture results separately.

To investigate a user's CLI connection, the packaged app also supports a
windowless check:

```powershell
& '.\Forever AI.exe' --check-codex-report '.\codex-check.json'
```

This runs `codex exec --help` and `codex login status` through the packaged bridge
without opening a chat window, sending a model request or reading authentication
files. It is a local connection check, separate from the offline package
self-test, and does not establish live model access. Read `passed` and `phase`
in the report. Failure records exclude raw CLI stdout/stderr.

Follow the [checks and publication workflow](https://github.com/szh101/Forever-companion-/blob/main/docs/pipeline.md)
when submitting a review branch. Shared UI changes require macOS regression and
native compilation checks. A Windows build does not verify macOS; keep those
checks in place.

## Verification scope

The 0.4.3 source at
[`c6ada6424c2f`](https://github.com/szh101/Forever-companion-/commit/c6ada6424c2f73cbca1adb9503f4dbfabaec8fa1)
passed 160 of 161 offline Windows checks; one generic symbolic-link test was
skipped for the platform. On macOS, 155 of 161 checks passed and six
Windows-specific checks were skipped. Hidden GUI checks passed on both platforms.
The Windows entry-point self-test, macOS native helper build and macOS
private-pasteboard checks also passed. These results are recorded in the
[source check run](https://github.com/szh101/Forever-companion-/actions/runs/38533867098).

Package and installer checks are separate from source checks. Their results are
recorded in the
[verification notes](https://github.com/szh101/Forever-companion-/blob/main/docs/verification.md).
Installation and update checks use a synthetic game directory.

Real game capture, scrolling, dragging, click-through, focus transfer and client
AddOn export require separate validation. The visible macOS interface and real
capture also need separate acceptance testing. See the
[Windows verification notes](https://github.com/szh101/Forever-companion-/blob/main/docs/windows-verification.md)
for detailed evidence and the
[README](https://github.com/szh101/Forever-companion-/blob/main/README.md) for
installation steps. These results do not mean that the application has been
installed or tested on a downloader's computer.

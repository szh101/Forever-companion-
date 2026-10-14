# Windows background checks

Use this procedure when testing must not interrupt a running game. It grants no
permission to operate a user's desktop, game, clipboard or model account.
See the [development guide](windows-development-handoff.md) for platform ownership.

1. Use a separate checkout or extracted source directory. Do not write into the
   game, Battle.net, WTF, Interface or Screenshots directories.
2. Do not open visible windows, move focus, send input, run `/reload`, or close
   and restart applications. Do not enumerate or capture game windows.
3. Use an existing Python installation with Tk and isolated project dependencies.
   Do not trigger a system installation, administrator prompt or security-setting
   change as part of a background check. Report missing prerequisites.
4. Install the locked project dependencies with `uv sync --locked --group dev`,
   or use the project's prepared virtual environment.
5. Run the hidden check and then read its completed report:

   ```powershell
   .venv\Scripts\pythonw.exe scripts\windows_quiet.py --report .runtime\windows-quiet.json
   ```

6. Report the test counts, `passed`, `hiddenGuiTested`, skipped cases and any
   failures. Do not include API keys, screenshots, private file paths or real
   player information in shared reports.

These checks use synthetic data and mocked external services. They require no
real model key, do not test a live model, and do not load the addon in a client.
`realCaptureTested:false` and `liveApiTested:false` are expected; do not change
them to true without the corresponding test actually running.

Arrange real capture, visible UI and game-client testing separately with the
current user's permission. Keep machine-specific logs in ignored local files.
Follow [publication checks](pipeline.md) for source upload; background testing
alone does not satisfy the macOS validation requirement for shared changes.

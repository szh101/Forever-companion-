"""Native AppKit integration on a private pasteboard; no user's clipboard/UI."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    if sys.platform != "darwin":
        raise SystemExit("Run this native check on macOS")
    root = Path(__file__).resolve().parents[1]
    runtime = root / ".runtime"
    runtime.mkdir(exist_ok=True)
    cache = runtime / "native" / "swift-cache"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clipboard-native-", dir=runtime) as work:
        binary = Path(work) / "clipboard-check"
        subprocess.run(["xcrun", "swiftc", "-parse-as-library", "-D", "FOREVER_CLIPBOARD_TEST",
                        "-module-cache-path", str(cache),
                        "-target", os.uname().machine + "-apple-macos14.0",
                        str(root / "native" / "MacCapture.swift"),
                        str(root / "tests" / "native" / "MacClipboardTests.swift"),
                        "-o", str(binary)], check=True, timeout=120)
        subprocess.run([str(binary)], check=True, timeout=20)


if __name__ == "__main__":
    main()

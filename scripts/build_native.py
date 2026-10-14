"""Build the local macOS helper; does not execute capture or request permissions."""
import os
from pathlib import Path
import subprocess
import sys


def build(root: Path, output: Path, *, cache: Path | None = None):
    if sys.platform != "darwin":
        raise SystemExit("The native helper must be built on macOS")
    output.parent.mkdir(parents=True, exist_ok=True)
    cache = cache or output.parent / "swift-cache"
    cache.mkdir(parents=True, exist_ok=True)
    subprocess.run(["xcrun", "swiftc", "-parse-as-library", "-O", "-module-cache-path", str(cache),
                    "-target", os.uname().machine + "-apple-macos14.0",
                    str(root / "native" / "MacCapture.swift"), "-o", str(output)], check=True)
    return output


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(build(root, root / ".runtime" / "native" / "forever-capture"))

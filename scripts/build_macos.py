"""Build a self-contained, ad-hoc signed Mac app from an exact Git commit."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import subprocess
import sys
import tarfile
import tempfile

from build_native import build


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    if sys.platform != "darwin" or not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise SystemExit("Build on macOS and pass a full frozen Git commit SHA")
    root = Path(__file__).resolve().parents[1]
    actual = subprocess.check_output(["git", "rev-parse", args.commit + "^{commit}"], cwd=root, text=True).strip()
    if actual != args.commit:
        raise SystemExit("Commit mismatch")
    output = root / "dist" / ("macos-" + actual[:12])
    if output.exists():
        raise SystemExit("Output already exists; preserve it and use a fresh commit")
    runtime = root / ".runtime"
    runtime.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="mac-build-", dir=runtime))
    source = work / "source"
    source.mkdir()
    archive = subprocess.check_output(["git", "archive", "--format=tar", actual], cwd=root)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(source, filter="data")
    native = build(source, work / "native" / "forever-capture", cache=runtime / "native" / "swift-cache")
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(work / "pyinstaller-cache"))
    subprocess.run([sys.executable, "-m", "PyInstaller", "--onedir", "--windowed", "--name", "Forever AI",
                    "--osx-bundle-identifier", "com.foreverai.companion", "--codesign-identity", "-",
                    "--distpath", str(output), "--workpath", str(work / "build"), "--specpath", str(work),
                    "--paths", str(source), "--add-binary", str(native) + ":native",
                    "--exclude-module", "lupa", "--exclude-module", "unittest",
                    str(source / "scripts" / "macos_entry.py")], cwd=source, env=env, check=True)
    app = output / "Forever AI.app"
    plist_path = app / "Contents" / "Info.plist"
    with plist_path.open("rb") as f:
        info = plistlib.load(f)
    info.update(CFBundleShortVersionString="0.4.2", CFBundleVersion="6", LSMinimumSystemVersion="14.0",
                NSHighResolutionCapable=True, NSHumanReadableCopyright="Forever AI local prototype",
                ForeverAISourceCommit=actual)
    with plist_path.open("wb") as f:
        plistlib.dump(info, f)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    bundle_zip = output / ("ForeverAI-macOS-" + platform.machine() + "-" + actual[:12] + ".zip")
    subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(bundle_zip)], check=True)
    manifest = {"sourceCommit": actual, "platform": "macOS", "architecture": platform.machine(),
                "minimumMacOS": "14.0", "app": str(app), "archive": bundle_zip.name,
                "sha256": hashlib.sha256(bundle_zip.read_bytes()).hexdigest(),
                "signature": "ad-hoc local; not Apple notarized", "gameClientTested": False,
                "liveApiTested": False}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

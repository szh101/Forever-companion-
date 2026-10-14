"""Package an explicit, committed source tree; never include local runtime data."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tomllib
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise SystemExit("Pass the exact full committed SHA")
    actual = subprocess.check_output(["git", "rev-parse", args.commit + "^{commit}"], cwd=root, text=True).strip()
    if actual != args.commit:
        raise SystemExit("Commit mismatch")
    output = root / "dist"
    output.mkdir(exist_ok=True)
    version = tomllib.loads(subprocess.check_output(
        ["git", "show", actual + ":pyproject.toml"], cwd=root).decode("utf-8"))["project"]["version"]
    archive = output / ("ForeverAI-" + version + "-" + actual[:12] + ".zip")
    subprocess.run(["git", "archive", "--format=zip", "--prefix=ForeverAI/", "--output=" + str(archive), actual], cwd=root, check=True)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            components = Path(name).parts
            if any(x in components for x in (".git", ".venv", ".runtime", "dist", "__pycache__")) or Path(name).name.startswith(".env"):
                raise SystemExit("Unexpected private content in archive")
        if z.testzip() is not None:
            raise SystemExit("Archive CRC verification failed")
        count = len(z.namelist())
    manifest = {"version": version, "sourceCommit": actual, "archive": archive.name,
                "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "entries": count,
                "status": "source archive only; publication is recorded separately by the shared pipeline; game-client verification pending"}
    archive.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

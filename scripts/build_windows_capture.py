"""Compile the one-shot WGC bridge using installed Windows/.NET reference files.

Compilation does not query, enumerate, or capture any window. No SDK download or
package restore is performed. The companion starts the result with no console.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


def build(root: Path, output: Path) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("Build the Windows capture helper on Windows x64")
    root, output = Path(root).resolve(), Path(output).resolve()
    windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    framework = windows / "Microsoft.NET/Framework64/v4.0.30319"
    reference_base = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Reference Assemblies/Microsoft/Framework/.NETFramework"
    facade_candidates = [reference_base / version / "Facades/System.Runtime.dll" for version in ("v4.8", "v4.7.2", "v4.6.1", "v4.6")]
    runtime = next((path for path in facade_candidates if path.is_file()), None)
    if runtime is None:
        raise RuntimeError("A .NET Framework reference assembly with System.Runtime.dll is required")
    references = [runtime, framework / "System.Runtime.WindowsRuntime.dll"]
    references += [windows / "System32/WinMetadata" / (name + ".winmd")
                   for name in ("Windows.Foundation", "Windows.Graphics", "Windows.Storage")]
    compiler, source = framework / "csc.exe", root / "native/WindowsCapture.cs"
    for path in [compiler, source, *references]:
        if not path.is_file():
            raise RuntimeError("Windows capture build dependency is missing: " + str(path))
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [str(compiler), "/nologo", "/target:exe", "/platform:x64", "/optimize+",
               "/out:" + str(output), *["/reference:" + str(path) for path in references], str(source)]
    result = subprocess.run(command, cwd=root, capture_output=True, timeout=60,
                            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    if result.returncode:
        raise RuntimeError("Windows capture helper compilation failed:\n" +
                           (result.stdout + result.stderr).decode("utf-8", "replace"))
    if not output.is_file():
        raise RuntimeError("Compiler did not create the Windows capture helper")
    return output


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=root / ".runtime/native/forever-capture-windows.exe")
    args = parser.parse_args()
    print(build(root, args.output))


if __name__ == "__main__":
    main()

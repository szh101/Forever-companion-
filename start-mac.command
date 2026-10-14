#!/bin/zsh
# Developer source launch. Users can double-click the standalone .app instead.
set -eu
cd -- "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print '请先使用 uv sync --locked，或打开已经打包的 Forever AI.app。'
  exit 1
fi
if [[ ! -x .runtime/native/forever-capture ]]; then
  .venv/bin/python scripts/build_native.py
fi
exec .venv/bin/python -m companion.app

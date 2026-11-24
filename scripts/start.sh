#!/bin/sh
# Start IELTS Study on Linux or macOS. The browser opens by itself; press Ctrl+C to quit.
# (On a Mac you can also build a desktop app: zsh assets/build_app.sh)
cd "$(dirname "$0")/.." || exit 1
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. Install it first: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
exec uv run ielts-study "$@"

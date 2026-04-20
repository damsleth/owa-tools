#!/bin/bash
# Install cal-cli as an editable pipx package so the `cal-cli` console
# script lands on PATH. Replaces the old shell-script symlink approach.
set -e
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v pipx >/dev/null 2>&1; then
  echo "pipx not found. Install it first: brew install pipx" >&2
  exit 1
fi

pipx install --force -e "$REPO_DIR"
echo
echo "cal-cli installed via pipx. Run: cal-cli --help"

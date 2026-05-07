#!/bin/bash
# Install owa-mail as an editable pipx package so the `owa-mail` console
# script lands on PATH. Replaces the old shell-script symlink approach.
set -e
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v pipx >/dev/null 2>&1; then
  echo "pipx not found. Install it first: brew install pipx" >&2
  exit 1
fi

pipx install --force -e "$REPO_DIR"
echo
echo "owa-mail installed via pipx. Run: owa-mail --help"

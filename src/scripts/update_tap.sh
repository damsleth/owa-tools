#!/usr/bin/env bash
#
# Update the Homebrew tap formula for a published owa-tools release.
#
# Replaces step 10 of AGENTS.md -> "Cutting a release", which was: curl the
# tarball, run shasum by hand, edit two fields in the formula, commit. That is
# pure transport with a correctness trap -- a mistyped sha256 produces a
# formula that fails only when someone installs it.
#
# Deliberately surgical: it rewrites ONLY `url` and `sha256`. The rest of the
# formula (the sixteen-binary test block, virtualenv_install_with_resources,
# the owa-piggy recommendation) stays owned by whoever maintains the formula,
# not by this script. teaminal's equivalent regenerates the whole file from a
# heredoc; that works there because the formula is a thin prebuilt-archive
# wrapper. This one has real content worth not clobbering.
#
# Run AFTER the tag is pushed -- the checksum is taken over the tarball
# GitHub generates for the tag.
#
# Usage:
#   src/scripts/update_tap.sh [vX.Y.Z] [/path/to/homebrew-tap]
#
#   Version defaults to `version` in pyproject.toml.
#   Tap path defaults to ../homebrew-tap, then ~/code/homebrew-tap.
#
# Options (via env):
#   NO_COMMIT=1   write the formula but skip the commit (review with git diff)
#   TARBALL=path  use a local tarball instead of downloading (for testing)

set -euo pipefail

cd "$(dirname "$0")/../.."
repo_root="$(pwd)"

# --- resolve version -------------------------------------------------------
version_arg="${1:-}"
if [[ -n "$version_arg" ]]; then
  version="${version_arg#v}"
else
  version="$(sed -n 's/^version *= *"\([^"]*\)".*/\1/p' pyproject.toml | head -1)"
  if [[ -z "$version" ]]; then
    echo "error: could not read version from pyproject.toml; pass it: $0 v1.5.0" >&2
    exit 1
  fi
fi
tag="v${version}"

# --- resolve tap -----------------------------------------------------------
tap_dir="${2:-}"
if [[ -z "$tap_dir" ]]; then
  for candidate in "../homebrew-tap" "${HOME}/code/homebrew-tap"; do
    if [[ -f "${candidate}/Formula/owa-tools.rb" ]]; then tap_dir="$candidate"; break; fi
  done
fi
formula="${tap_dir%/}/Formula/owa-tools.rb"
if [[ ! -f "$formula" ]]; then
  echo "error: tap formula not found at ${formula:-<unset>}" >&2
  echo "       pass the tap path: $0 ${tag} /path/to/homebrew-tap" >&2
  exit 1
fi

url="https://github.com/damsleth/owa-tools/archive/refs/tags/${tag}.tar.gz"

# --- obtain the checksum ---------------------------------------------------
tmp_tar=""
cleanup() { [[ -n "$tmp_tar" && -f "$tmp_tar" ]] && rm -f "$tmp_tar"; }
trap cleanup EXIT

if [[ -n "${TARBALL:-}" ]]; then
  [[ -f "$TARBALL" ]] || { echo "error: TARBALL not found: $TARBALL" >&2; exit 1; }
  tar_file="$TARBALL"
  echo "==> using local tarball ${tar_file}"
else
  tmp_tar="$(mktemp -t owa-tools-tap)"
  tar_file="$tmp_tar"
  echo "==> fetching ${url}"
  # -f so a 404 (tag not pushed yet) fails loudly instead of hashing an
  # HTML error page into the formula.
  if ! curl -sSLf "$url" -o "$tar_file"; then
    echo "error: could not fetch the tag tarball. Is ${tag} pushed to GitHub?" >&2
    exit 1
  fi
fi

sha="$(shasum -a 256 "$tar_file" | awk '{print $1}')"
if [[ ! "$sha" =~ ^[0-9a-f]{64}$ ]]; then
  echo "error: shasum produced something that is not a sha256: ${sha}" >&2
  exit 1
fi
echo "==> sha256 ${sha}"

# --- rewrite url + sha256 --------------------------------------------------
before_url="$(sed -n 's/^ *url "\(.*\)".*/\1/p' "$formula" | head -1)"
before_sha="$(sed -n 's/^ *sha256 "\(.*\)".*/\1/p' "$formula" | head -1)"

python3 - "$formula" "$url" "$sha" <<'PY'
import re, sys
path, url, sha = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(path, encoding='utf-8').read()

# Only the top-level url/sha256 pair (the first of each) is the release
# pointer. Anchoring on the line start avoids touching anything nested.
src, n_url = re.subn(r'(?m)^(\s*url\s+")[^"]*(")', lambda m: m.group(1) + url + m.group(2), src, count=1)
src, n_sha = re.subn(r'(?m)^(\s*sha256\s+")[^"]*(")', lambda m: m.group(1) + sha + m.group(2), src, count=1)
if n_url != 1 or n_sha != 1:
    sys.exit(f'error: expected one url and one sha256 line, replaced {n_url} and {n_sha}')
open(path, 'w', encoding='utf-8').write(src)
PY

echo "==> ${formula}"
echo "    url    ${before_url}"
echo "        -> ${url}"
echo "    sha256 ${before_sha}"
echo "        -> ${sha}"

# Mirror the tap formula into the repo's draft so the two cannot drift. The
# TAP is authoritative for content; the in-repo copy is a reference. (They had
# already drifted badly before this script existed: the draft still described
# nine binaries and a PyPI sdist URL.)
draft="${repo_root}/src/packaging/homebrew/owa-tools.rb"
if [[ -f "$draft" ]]; then
  {
    echo "# Mirror of the authoritative formula in damsleth/homebrew-tap."
    echo "# Written by src/scripts/update_tap.sh -- do not hand-edit; edit the tap."
    cat "$formula"
  } > "$draft"
  echo "==> mirrored into src/packaging/homebrew/owa-tools.rb"
fi

# --- commit ----------------------------------------------------------------
if [[ "${NO_COMMIT:-}" == "1" ]]; then
  echo "==> NO_COMMIT=1 set; formula written, skipping commit"
  echo "    review: git -C ${tap_dir} diff"
  exit 0
fi

if git -C "$tap_dir" diff --quiet -- Formula/owa-tools.rb; then
  echo "==> formula already at ${tag}; nothing to commit"
  exit 0
fi

git -C "$tap_dir" add Formula/owa-tools.rb
git -C "$tap_dir" commit -q -m "owa-tools ${version}"
echo "==> committed in ${tap_dir}: owa-tools ${version}"
echo "    push it:  git -C ${tap_dir} push"
echo "    then:     brew upgrade owa-tools"

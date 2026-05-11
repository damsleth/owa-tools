# Legacy per-tool Homebrew aliases

For one release cycle after the first `owa-tools` release, the old
per-tool formulas in the tap stay alive as deprecated aliases that
depend on `owa-tools`. After that cycle they are removed.

Each old formula gets the snippet below. `owa-cal` shown as the example;
repeat with the binary name swapped for the other six tools (`owa-mail`,
`owa-graph`, `owa-doctor`, `owa-people`, `owa-sched`, `owa-drive`).

```ruby
class OwaCal < Formula
  desc "Deprecated. Installs owa-tools, which provides owa-cal."
  homepage "https://github.com/damsleth/owa-tools"
  url "https://files.pythonhosted.org/packages/source/o/owa-tools/owa-tools-X.Y.Z.tar.gz"
  sha256 "<sha256 of the owa-tools sdist>"
  license "MIT"
  version "X.Y.Z"

  # Remove this formula one release cycle after the first owa-tools
  # release (e.g., when bumping to vX.(Y+1).0 or vX.Y.(Z+1) depending on
  # how the cycle is sliced).
  deprecate! date: "YYYY-MM-DD", because: "owa-cal is now part of the owa-tools suite. Run `brew install owa-tools` instead."

  depends_on "owa-tools"

  def install
    # No-op. The owa-tools formula installs the binary.
  end

  test do
    assert_match version.to_s, shell_output("#{HOMEBREW_PREFIX}/bin/owa-cal --version")
  end
end
```

Notes:

- Keep the same version on the alias as on `owa-tools` so users can pin
  consistently.
- Do not ship per-tool wheels. The alias is purely a redirect.
- The eventual removal PR should update the tap's README to point users
  at `owa-tools` directly.

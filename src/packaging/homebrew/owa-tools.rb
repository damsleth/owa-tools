#  Draft Homebrew formula for the `owa-tools` suite.
#
#  This file is not used by Homebrew when it lives in this repository. Copy
#  it into the tap repo (`HomebrewFormula/owa-tools.rb` or
#  `Formula/owa-tools.rb`, depending on tap layout) at release time and
#  update `url`, `sha256`, and `version` to point at the published sdist on
#  PyPI.
#
#  Pinned things to remember when copying:
#  - The nine console scripts (`owa`, `owa-cal`, `owa-mail`, `owa-graph`,
#    `owa-doctor`, `owa-people`, `owa-sched`, `owa-drive`, `owa-todo`) all
#    come from this one bottle.
#  - `owa-piggy` keeps its own formula in the same tap. This formula does
#    not depend on it at install time. `owa doctor --no-tokens` deliberately
#    exits 2 when `owa-piggy` is not installed (the broker is required for
#    any real check); the `test do` block matches that contract by reading
#    the JSON payload's `owa_piggy.installed` field rather than asserting
#    exit 0.
#  - Runtime is stdlib-only. The only Homebrew dependency is a supported
#    Python.

class OwaTools < Formula
  include Language::Python::Virtualenv

  desc "Outlook / Microsoft 365 CLI suite (cal, mail, graph, doctor, people, sched, drive)"
  homepage "https://github.com/damsleth/owa-tools"
  # Replace at release time with the sdist URL and sha256 from PyPI:
  #   https://pypi.org/project/owa-tools/X.Y.Z/#files
  url "https://files.pythonhosted.org/packages/source/o/owa-tools/owa-tools-0.0.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "MIT"
  version "0.0.0"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    # All nine binaries land on PATH and report the same suite version.
    %w[owa owa-cal owa-mail owa-graph owa-doctor owa-people owa-sched owa-drive
       owa-todo].each do |bin_name|
      assert_match version.to_s, shell_output("#{bin}/#{bin_name} --version")
    end

    # `owa list` does not need credentials and must succeed.
    system "#{bin}/owa", "list"

    # `owa doctor --no-tokens` exits 2 when `owa-piggy` is not installed
    # (the broker is required for any real check). Assert on the JSON
    # payload instead of the exit code so the formula test stays green
    # without owa-piggy on PATH.
    doctor_json = shell_output("#{bin}/owa doctor --no-tokens", 2)
    assert_match "\"installed\": false", doctor_json
  end
end

# Mirror of the authoritative formula in damsleth/homebrew-tap.
# Written by src/scripts/update_tap.sh -- do not hand-edit; edit the tap.
class OwaTools < Formula
  include Language::Python::Virtualenv

  desc "Outlook/Microsoft 365 CLI suite (mail, calendar, graph, drive, todo, video)"
  homepage "https://github.com/damsleth/owa-tools"
  url "https://github.com/damsleth/owa-tools/archive/refs/tags/v1.5.1.tar.gz"
  sha256 "96bf852994f4602eda341c2c988d00f4974af25f8fe66e0a1a8e93284647bcde"
  license "MIT"
  head "https://github.com/damsleth/owa-tools.git", branch: "main"

  depends_on "python@3.12"
  depends_on "damsleth/tap/owa-piggy" => :recommended

  def install
    virtualenv_install_with_resources
  end

  test do
    # All sixteen binaries land on PATH and report the same suite version.
    %w[owa owa-cal owa-mail owa-graph owa-doctor owa-people owa-sched owa-places
       owa-drive owa-todo owa-planner owa-sites owa-teams owa-vids owa-ado
       owa-swodp].each do |bin_name|
      assert_match version.to_s, shell_output("#{bin}/#{bin_name} --version")
    end
    system "#{bin}/owa", "list"
  end
end

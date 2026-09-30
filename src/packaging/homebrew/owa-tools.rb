# Mirror of the authoritative formula in damsleth/homebrew-tap.
# Written by src/scripts/update_tap.sh -- do not hand-edit; edit the tap.
class OwaTools < Formula
  include Language::Python::Virtualenv

  desc "Outlook/Microsoft 365 CLI suite (mail, calendar, graph, drive, todo, video)"
  homepage "https://github.com/damsleth/owa-tools"
  url "https://github.com/damsleth/owa-tools/archive/refs/tags/v1.9.0.tar.gz"
  sha256 "3a8a0f2b6a160cc4ad5f37cca1e0aae20ab9301a386aaa6edef37d9693f6df44"
  license "MIT"
  head "https://github.com/damsleth/owa-tools.git", branch: "main"

  depends_on "python@3.12"
  depends_on "damsleth/tap/owa-piggy"

  def install
    virtualenv_install_with_resources
  end

  test do
    # All twenty binaries land on PATH and report the same suite version.
    %w[owa owa-cal owa-mail owa-graph owa-doctor owa-people owa-sched owa-places
       owa-drive owa-todo owa-planner owa-sites owa-teams owa-vids owa-ado
       owa-swodp owa-halo owa-kova owa-gmail owa-gdrive].each do |bin_name|
      assert_match version.to_s, shell_output("#{bin}/#{bin_name} --version")
    end
    system "#{bin}/owa", "list"
  end
end

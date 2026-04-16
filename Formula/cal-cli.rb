class CalCli < Formula
  desc "Calendar CLI for Outlook / Microsoft 365"
  homepage "https://github.com/damsleth/cal-cli"
  head "https://github.com/damsleth/cal-cli.git", branch: "main"
  license "WTFPL"

  depends_on "jq"
  depends_on "python@3.12"
  depends_on "damsleth/tap/owa-piggy" => :recommended

  def install
    bin.install "cal-cli.zsh" => "cal-cli"
  end

  test do
    assert_match "Usage: cal-cli", shell_output("#{bin}/cal-cli help 2>&1")
  end
end

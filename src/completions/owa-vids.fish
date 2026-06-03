# fish completion for owa-vids.
#
# Install: drop into ~/.config/fish/completions/owa-vids.fish, or
# (with Homebrew) /opt/homebrew/share/fish/vendor_completions.d/.
#
# fish 3.x.

set -l owa_vids_commands info show get download check probe config schema help

# --- first positional: commands + aliases -----------------------------------

complete -c owa-vids -n "__fish_is_first_token" -a "info" -d "Probe a recording (alias: show)" -f
complete -c owa-vids -n "__fish_is_first_token" -a "show" -d "Alias for info" -f
complete -c owa-vids -n "__fish_is_first_token" -a "get" -d "Download and mux to MP4 (alias: download)" -f
complete -c owa-vids -n "__fish_is_first_token" -a "download" -d "Alias for get" -f
complete -c owa-vids -n "__fish_is_first_token" -a "check" -d "Validate auth + manifest + first segments (alias: probe)" -f
complete -c owa-vids -n "__fish_is_first_token" -a "probe" -d "Alias for check" -f
complete -c owa-vids -n "__fish_is_first_token" -a "config" -d "View or set cached region and default profile" -f
complete -c owa-vids -n "__fish_is_first_token" -a "schema" -d "Print the JSON command schema" -f
complete -c owa-vids -n "__fish_is_first_token" -a "help" -d "Show help" -f

# --- global flags ------------------------------------------------------------

complete -c owa-vids -l profile -d "owa-piggy profile alias" -x
complete -c owa-vids -l debug -d "Verbose HTTP / ffmpeg / auth detail" -f
complete -c owa-vids -l verbose -d "Alias for --debug" -f
complete -c owa-vids -l version -d "Print the suite version" -f
complete -c owa-vids -l help -d "Show help" -f

# --- source flags (info / get / check) ----------------------------------------

complete -c owa-vids -n "__fish_seen_subcommand_from info show get download check probe" -l manifest-url -d "videomanifest URL from DevTools" -x
complete -c owa-vids -n "__fish_seen_subcommand_from info show get download check probe" -l embed-url -d "Teams/Stream player page URL" -x
complete -c owa-vids -n "__fish_seen_subcommand_from info show get download check probe config" -l region -d "Media region host (*-mediap.svc.ms)" -x

# --- per-command flags ---------------------------------------------------------

complete -c owa-vids -n "__fish_seen_subcommand_from info show get download" -l pretty -d "Human-readable output" -f
complete -c owa-vids -n "__fish_seen_subcommand_from get download" -l out -s o -d "Output MP4 path" -r
complete -c owa-vids -n "__fish_seen_subcommand_from get download check probe" -l workdir -d "Segment scratch dir" -r -a "(__fish_complete_directories)"
complete -c owa-vids -n "__fish_seen_subcommand_from get download" -l video-only -d "Download only the video track" -f
complete -c owa-vids -n "__fish_seen_subcommand_from get download" -l audio-only -d "Download only the audio track" -f
complete -c owa-vids -n "__fish_seen_subcommand_from config" -l set-profile -d "Alias for --profile" -x

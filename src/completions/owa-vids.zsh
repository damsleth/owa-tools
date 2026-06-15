#compdef owa-vids
#
# zsh completion for owa-vids.
#
# Install: place anywhere on $fpath named exactly `_owa-vids`. With
# Homebrew + zsh-completions, putting it in
# `/opt/homebrew/share/zsh/site-functions/_owa-vids` is the conventional
# spot. Then run `compinit` (or restart zsh).

_owa_vids() {
    local -a commands global_flags source_flags get_flags config_flags
    commands=(
        'info:Probe a recording (title, duration, tracks; alias: show)'
        'get:Download all tracks and mux to MP4 (alias: download)'
        'check:Validate auth, manifest, and first segments (alias: probe)'
        'config:View or set cached region and default profile'
        'schema:Print the JSON command schema'
        'help:Show help'
    )
    global_flags=(--profile --all-profiles -A --debug --verbose --version --help)
    source_flags=(--manifest-url --embed-url --region)
    get_flags=(--out -o --workdir --video-only --audio-only --pretty)
    config_flags=(--region --set-profile --profile)

    # Value-completing flags.
    case "${words[CURRENT-1]}" in
        --out|-o)
            _files
            return
            ;;
        --workdir)
            _directories
            return
            ;;
        --profile|--set-profile|--manifest-url|--embed-url|--region)
            return
            ;;
    esac

    # Find the subcommand.
    local i cmd=""
    for (( i=2; i<=CURRENT-1; i++ )); do
        case "${words[i]}" in
            -*) continue ;;
            info|show|get|download|check|probe|config|schema|help)
                cmd="${words[i]}"
                break
                ;;
        esac
    done

    if [[ -z "$cmd" ]]; then
        if [[ "${words[CURRENT]}" == -* ]]; then
            _values 'flag' "${global_flags[@]}"
        else
            _describe 'command' commands
        fi
        return
    fi

    case "$cmd" in
        info|show)
            _values 'flag' "${source_flags[@]}" --pretty "${global_flags[@]}"
            ;;
        get|download)
            _values 'flag' "${source_flags[@]}" "${get_flags[@]}" "${global_flags[@]}"
            ;;
        check|probe)
            _values 'flag' "${source_flags[@]}" --workdir "${global_flags[@]}"
            ;;
        config)
            _values 'flag' "${config_flags[@]}" --debug --help
            ;;
    esac
}

_owa_vids "$@"

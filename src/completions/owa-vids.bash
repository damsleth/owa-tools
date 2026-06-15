# bash completion for owa-vids
#
# Install: source this file from your bashrc, or symlink into
# /usr/local/etc/bash_completion.d/ (Homebrew) or
# /etc/bash_completion.d/ (system).
#
# Sticks to bash 3 syntax for default-macOS compatibility.

_owa_vids() {
    local cur prev
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    local commands="info get check config schema help"
    local aliases="show download probe"
    local global_flags="--profile --all-profiles -A --debug --verbose --version --help"
    local source_flags="--manifest-url --embed-url --region"
    local get_flags="--out -o --workdir --video-only --audio-only --pretty"
    local config_flags="--region --set-profile --profile"

    # Value-completing flags: file/dir completion where it makes sense,
    # otherwise leave to the user.
    case "$prev" in
        --out|-o)
            COMPREPLY=( $(compgen -f -- "$cur") )
            return 0
            ;;
        --workdir)
            COMPREPLY=( $(compgen -d -- "$cur") )
            return 0
            ;;
        --profile|--set-profile|--manifest-url|--embed-url|--region)
            COMPREPLY=()
            return 0
            ;;
    esac

    # Find the subcommand, skipping flags and their values.
    local i cmd=""
    for (( i=1; i<COMP_CWORD; i++ )); do
        local w="${COMP_WORDS[i]}"
        case "$w" in
            -*) continue ;;
            info|show|get|download|check|probe|config|schema|help)
                cmd="$w"
                break
                ;;
        esac
    done

    if [[ -z "$cmd" ]]; then
        if [[ "$cur" == -* ]]; then
            COMPREPLY=( $(compgen -W "$global_flags" -- "$cur") )
        else
            COMPREPLY=( $(compgen -W "$commands $aliases" -- "$cur") )
        fi
        return 0
    fi

    case "$cmd" in
        info|show)
            COMPREPLY=( $(compgen -W "$source_flags --pretty $global_flags" -- "$cur") )
            ;;
        get|download)
            COMPREPLY=( $(compgen -W "$source_flags $get_flags $global_flags" -- "$cur") )
            ;;
        check|probe)
            COMPREPLY=( $(compgen -W "$source_flags --workdir $global_flags" -- "$cur") )
            ;;
        config)
            COMPREPLY=( $(compgen -W "$config_flags --debug --help" -- "$cur") )
            ;;
        *)
            COMPREPLY=()
            ;;
    esac
}

complete -F _owa_vids owa-vids

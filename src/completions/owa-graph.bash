# bash completion for owa-graph
#
# Install: source this file from your bashrc, or symlink into
# /usr/local/etc/bash_completion.d/ (Homebrew) or
# /etc/bash_completion.d/ (system).
#
# Sticks to bash 3 syntax for default-macOS compatibility - no
# associative arrays, no compopt dependency on bash-completion v2.

_owa_graph() {
    local cur prev words cword
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    local verbs="GET POST PATCH PUT DELETE"
    local reserved="refresh config batch help"
    local groups="me mail calendar files users teams chats presence contacts groups planner todo sites directory"
    local audiences="graph outlook outlook365 teams ic3 csa presence uis azure keyvault storage sql substrate manage powerbi flow devops"
    local flags="--pretty --ndjson --retry --all --raw --curl --az --beta --debug --verbose --version --help --profile --all-profiles -A --body --header --query --select --top --filter --count --search --audience"

    # Value-completing flags (next arg is a value, not another flag).
    case "$prev" in
        --audience)
            COMPREPLY=( $(compgen -W "$audiences" -- "$cur") )
            return 0
            ;;
        --profile|--body|--header|--query|--select|--top|--filter|--search)
            # No useful static completion - leave to the user / their shell.
            COMPREPLY=()
            return 0
            ;;
    esac

    # Walk back through COMP_WORDS to classify the head: was it a
    # resource group, an HTTP verb, or a reserved subcommand? Sets
    # `head_kind` and (for groups) `group`.
    local i head_kind="" group=""
    for (( i=1; i<COMP_CWORD; i++ )); do
        local w="${COMP_WORDS[i]}"
        case "$w" in
            -*) continue ;;
        esac
        case "$w" in
            me|mail|calendar|files|users|teams|chats|presence|contacts|groups|planner|todo|sites|directory)
                head_kind="group"
                group="$w"
                break
                ;;
            GET|POST|PATCH|PUT|DELETE|get|post|patch|put|delete)
                head_kind="verb"
                break
                ;;
            refresh|config|batch|help)
                head_kind="reserved"
                break
                ;;
        esac
    done

    # Path completion: right after an HTTP verb, or when the verb is omitted
    # and the first arg is a /path (`owa-graph /me` == `owa-graph GET /me`).
    # We complete one tier per tab (segment-wise) from the vendored manifest
    # rather than dumping the whole tree. --beta switches the source endpoint.
    if [[ ( "$head_kind" == "verb" && ${COMP_CWORD} -eq $((i+1)) ) || \
          ( ${COMP_CWORD} -eq 1 && "$cur" == /* ) ]] && [[ "$cur" != -* ]]; then
        local endpoint="v1.0"
        local w
        for w in "${COMP_WORDS[@]}"; do
            [[ "$w" == "--beta" ]] && endpoint="beta"
        done
        local cands
        cands="$(owa-graph __complete next "$endpoint" "$cur" 2>/dev/null)"
        COMPREPLY=( $(compgen -W "$cands" -- "$cur") )
        # Parents come back with a trailing slash; suppress the space so the
        # next tab descends (no-op on bash 3.2, which lacks compopt).
        compopt -o nospace 2>/dev/null
        return 0
    fi

    if [[ -n "$group" && "$cur" != -* ]]; then
        # Only complete shortcut name in the slot immediately after the
        # group token. Beyond that, fall through to flag completion.
        if [[ ${COMP_CWORD} -eq $((i+1)) ]]; then
            local shortcuts=""
            case "$group" in
                me)        shortcuts="whoami photo manager directreports help" ;;
                mail)      shortcuts="list read send reply replyall forward move flag delete help" ;;
                calendar)  shortcuts="events create update delete findtimes accept decline help" ;;
                files)     shortcuts="list download upload share delete search help" ;;
                users)     shortcuts="list find get manager directreports help" ;;
                teams)     shortcuts="joined channels messages send members help" ;;
                chats)     shortcuts="list messages send help" ;;
                presence)  shortcuts="me set get help" ;;
                contacts)  shortcuts="list find create delete help" ;;
                groups)    shortcuts="list members add remove help" ;;
                planner)   shortcuts="tasks complete plans buckets help" ;;
                todo)      shortcuts="lists tasks add complete help" ;;
                sites)     shortcuts="find lists items help" ;;
                directory) shortcuts="roles auditlogs help" ;;
            esac
            COMPREPLY=( $(compgen -W "$shortcuts" -- "$cur") )
            return 0
        fi
    fi

    # First positional: verbs + groups + reserved.
    if [[ ${COMP_CWORD} -eq 1 && "$cur" != -* ]]; then
        COMPREPLY=( $(compgen -W "$verbs $reserved $groups" -- "$cur") )
        return 0
    fi

    # Default: flag completion.
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "$flags" -- "$cur") )
        return 0
    fi

    COMPREPLY=()
}

complete -F _owa_graph owa-graph

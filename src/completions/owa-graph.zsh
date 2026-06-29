#compdef owa-graph
#
# zsh completion for owa-graph.
#
# Install: place anywhere on $fpath named exactly `_owa-graph`. With
# Homebrew + zsh-completions, putting it in
# `/opt/homebrew/share/zsh/site-functions/_owa-graph` is the conventional
# spot. Then run `compinit` (or restart zsh).

_owa_graph() {
    local -a verbs reserved groups audiences flags
    verbs=(GET POST PATCH PUT DELETE)
    reserved=(refresh config batch help)
    groups=(me mail calendar files users teams chats presence contacts groups planner todo sites directory)
    audiences=(graph outlook outlook365 teams ic3 csa presence uis azure keyvault storage sql substrate manage powerbi flow devops)
    flags=(
        --pretty --ndjson --retry --all --raw --curl --az --beta
        --debug --verbose --version --help --profile --all-profiles -A --body --header
        --query --select --top --filter --count --search --audience
    )

    # Classify the head and remember which slot it sat in.
    local i head_kind="" group=""
    for (( i=2; i<=CURRENT-1; i++ )); do
        local w="${words[i]}"
        case "$w" in
            -*) continue ;;
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

    # Value-completing flags.
    if [[ "${words[CURRENT-1]}" == "--audience" ]]; then
        _values 'audience' "${audiences[@]}"
        return
    fi

    # Path completion. Either right after an explicit HTTP verb, or the verb
    # was omitted and the user is typing a /path as the first arg
    # (`owa-graph /me` == `owa-graph GET /me`). --beta anywhere switches to the
    # beta manifest. We complete one tier per tab (segment-wise) so a tab never
    # dumps the whole ~3.5k-path tree.
    local cur="${words[CURRENT]}"
    if [[ ( "$head_kind" == "verb" && $CURRENT -eq $((i+1)) ) || \
          ( $CURRENT -eq 2 && "$cur" == /* ) ]]; then
        local endpoint="v1.0" x
        for x in "${words[@]}"; do
            [[ "$x" == "--beta" ]] && endpoint="beta"
        done
        local -a cands parents leaves
        cands=("${(@f)$(owa-graph __complete next $endpoint "$cur" 2>/dev/null)}")
        local c
        for c in "${cands[@]}"; do
            [[ -z "$c" ]] && continue
            if [[ "$c" == */ ]]; then parents+=("${c%/}"); else leaves+=("$c"); fi
        done
        # Parents keep a trailing slash and no space, so the next tab descends;
        # leaves complete normally. Both groups are filtered by what's typed.
        (( ${#parents} )) && compadd -S / -- "${parents[@]}"
        (( ${#leaves} )) && compadd -- "${leaves[@]}"
        return
    fi

    # Shortcut for the slot right after a group token.
    if [[ -n "$group" && $CURRENT -eq $((i+1)) ]]; then
        local -a shortcuts
        case "$group" in
            me)        shortcuts=(whoami photo manager directreports help) ;;
            mail)      shortcuts=(list read send reply replyall forward move flag delete help) ;;
            calendar)  shortcuts=(events create update delete findtimes accept decline help) ;;
            files)     shortcuts=(list download upload share delete search help) ;;
            users)     shortcuts=(list find get manager directreports help) ;;
            teams)     shortcuts=(joined channels messages send members help) ;;
            chats)     shortcuts=(list messages send help) ;;
            presence)  shortcuts=(me set get help) ;;
            contacts)  shortcuts=(list find create delete help) ;;
            groups)    shortcuts=(list members add remove help) ;;
            planner)   shortcuts=(tasks complete plans buckets help) ;;
            todo)      shortcuts=(lists tasks add complete help) ;;
            sites)     shortcuts=(find lists items help) ;;
            directory) shortcuts=(roles auditlogs help) ;;
        esac
        _values 'shortcut' "${shortcuts[@]}"
        return
    fi

    # First positional.
    if [[ $CURRENT -eq 2 ]]; then
        _values 'command' "${verbs[@]}" "${reserved[@]}" "${groups[@]}"
        return
    fi

    # Default: flags.
    _values 'flag' "${flags[@]}"
}

_owa_graph "$@"

# fish completion for owa-graph.
#
# Install: drop into ~/.config/fish/completions/owa-graph.fish, or
# (with Homebrew) /opt/homebrew/share/fish/vendor_completions.d/.
#
# fish 3.x. Uses __fish_seen_subcommand_from for both first-position
# routing and group/shortcut detection - cleaner than the bash/zsh
# manual-walk pattern.

# --- helpers ---------------------------------------------------------------

set -l owa_graph_verbs GET POST PATCH PUT DELETE
set -l owa_graph_reserved refresh config batch help
set -l owa_graph_groups me mail calendar files users teams chats presence contacts groups planner todo sites directory
set -l owa_graph_audiences graph outlook outlook365 teams ic3 csa presence uis azure keyvault storage sql substrate manage powerbi flow devops

# --- first positional: verbs + groups + reserved ---------------------------

complete -c owa-graph -n "__fish_is_first_token" -a "$owa_graph_verbs $owa_graph_reserved $owa_graph_groups" -f

# --- path completion (segment-wise) ----------------------------------------
#
# Shells out to `owa-graph __complete next` once per tab-press, passing the
# token being completed so we only return the next tier (e.g. /me -> /me/*)
# instead of the whole ~3.5k-path tree. Fires after an explicit verb, or when
# the verb is omitted and the token is a /path (`owa-graph /me`).

function __owa_graph_paths
    set -l endpoint v1.0
    if contains -- --beta (commandline -opc)
        set endpoint beta
    end
    owa-graph __complete next $endpoint (commandline -ct) 2>/dev/null
end

complete -c owa-graph \
    -n "__fish_seen_subcommand_from GET POST PATCH PUT DELETE; or string match -q -- '/*' (commandline -ct)" \
    -a "(__owa_graph_paths)" -f

# --- per-group shortcuts ---------------------------------------------------

complete -c owa-graph -n "__fish_seen_subcommand_from me; and not __fish_seen_subcommand_from whoami photo manager directreports help" -a "whoami photo manager directreports help" -f
complete -c owa-graph -n "__fish_seen_subcommand_from mail; and not __fish_seen_subcommand_from list read send reply replyall forward move flag delete help" -a "list read send reply replyall forward move flag delete help" -f
complete -c owa-graph -n "__fish_seen_subcommand_from calendar; and not __fish_seen_subcommand_from events create update delete findtimes accept decline help" -a "events create update delete findtimes accept decline help" -f
complete -c owa-graph -n "__fish_seen_subcommand_from files; and not __fish_seen_subcommand_from list download upload share delete search help" -a "list download upload share delete search help" -f
complete -c owa-graph -n "__fish_seen_subcommand_from users; and not __fish_seen_subcommand_from list find get manager directreports help" -a "list find get manager directreports help" -f
complete -c owa-graph -n "__fish_seen_subcommand_from teams; and not __fish_seen_subcommand_from joined channels messages send members help" -a "joined channels messages send members help" -f
complete -c owa-graph -n "__fish_seen_subcommand_from chats; and not __fish_seen_subcommand_from list messages send help" -a "list messages send help" -f
complete -c owa-graph -n "__fish_seen_subcommand_from presence; and not __fish_seen_subcommand_from me set get help" -a "me set get help" -f
complete -c owa-graph -n "__fish_seen_subcommand_from contacts; and not __fish_seen_subcommand_from list find create delete help" -a "list find create delete help" -f
complete -c owa-graph -n "__fish_seen_subcommand_from groups; and not __fish_seen_subcommand_from list members add remove help" -a "list members add remove help" -f
complete -c owa-graph -n "__fish_seen_subcommand_from planner; and not __fish_seen_subcommand_from tasks complete plans buckets help" -a "tasks complete plans buckets help" -f
complete -c owa-graph -n "__fish_seen_subcommand_from todo; and not __fish_seen_subcommand_from lists tasks add complete help" -a "lists tasks add complete help" -f
complete -c owa-graph -n "__fish_seen_subcommand_from sites; and not __fish_seen_subcommand_from find lists items help" -a "find lists items help" -f
complete -c owa-graph -n "__fish_seen_subcommand_from directory; and not __fish_seen_subcommand_from roles auditlogs help" -a "roles auditlogs help" -f

# --- flags -----------------------------------------------------------------

complete -c owa-graph -l pretty   -d "Human-readable output (table when shape is known)"
complete -c owa-graph -l ndjson   -d "Stream collection items one JSON per line"
complete -c owa-graph -l retry    -d "Honor Retry-After once on 429/503"
complete -c owa-graph -l all      -d "Follow @odata.nextLink until exhausted"
complete -c owa-graph -l raw      -d "Print raw response bytes (no JSON parsing)"
complete -c owa-graph -l curl     -d "Print equivalent curl command and exit"
complete -c owa-graph -l az       -d "Print equivalent az rest command and exit"
complete -c owa-graph -l beta     -d "Use https://graph.microsoft.com/beta"
complete -c owa-graph -l debug    -d "Print HTTP requests and response bodies on errors"
complete -c owa-graph -l verbose  -d "Alias for --debug"
complete -c owa-graph -l version  -d "Print version and exit"
complete -c owa-graph -l help     -d "Show help and exit"
complete -c owa-graph -l profile  -d "owa-piggy profile alias (or 'all' to fan out)" -r
complete -c owa-graph -l all-profiles -d "Fan out across every active profile"
complete -c owa-graph -o A         -d "Fan out across every active profile"
complete -c owa-graph -l body     -d "Request body (JSON, @file, or -)" -r
complete -c owa-graph -l header   -d "Extra header K=V" -r
complete -c owa-graph -l query    -d "OData query parameter K=V" -r
complete -c owa-graph -l select   -d "Shortcut for --query \$select=…" -r
complete -c owa-graph -l top      -d "Shortcut for --query \$top=N" -r
complete -c owa-graph -l filter   -d "Shortcut for --query \$filter=…" -r
complete -c owa-graph -l count    -d "Shortcut for \$count=true (sets ConsistencyLevel)"
complete -c owa-graph -l search   -d "Shortcut for \$search='…' (sets ConsistencyLevel)" -r

complete -c owa-graph -l audience -d "FOCI audience" -x -a "$owa_graph_audiences"

#!/bin/zsh

# cal-cli - Calendar CLI for Outlook / Microsoft 365
# Uses Outlook REST API (cookie auth) or Microsoft Graph (OAuth)
# POSIX-style util: pipe-friendly, JSON by default, --pretty for humans

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

# --- .env loading ---
if [ ! -f .env ]; then
  if [ -f .env.sample ]; then
    if cp .env.sample .env 2>/dev/null; then
      print -P "%F{yellow}Created .env from .env.sample. Configure auth then re-run.%f" >&2
      exit 2
    fi
  fi
  print -P "%F{red}ERROR: .env not found. Copy .env.sample to .env and configure it.%f" >&2
  exit 1
fi
source .env

# --- Defaults ---
: ${debug:=0}
: ${default_timezone:="W. Europe Standard Time"}

# --- Logging (all to stderr, stdout is data only) ---
debug_log() { [[ "$debug" -eq 1 ]] && print -P "%F{green}DEBUG: $1%f" >&2 }
error_log() { print -P "%F{red}ERROR: $1%f" >&2 }
info_log()  { print -P "%F{cyan}$1%f" >&2 }

# --- Dependencies ---
check_dep() {
  if ! command -v "$1" &>/dev/null; then
    error_log "Required command '$1' not found."
    exit 1
  fi
}
check_dep curl
check_dep jq

# Locate owa-piggy: PATH first, then sibling repo directory.
_owa_piggy() {
  if command -v owa-piggy &>/dev/null; then
    OWA_REFRESH_TOKEN="$OUTLOOK_REFRESH_TOKEN" \
    OWA_TENANT_ID="$OUTLOOK_TENANT_ID" \
    owa-piggy "$@"
  elif [[ -x "$SCRIPT_DIR/../owa-piggy/owa-piggy" ]]; then
    OWA_REFRESH_TOKEN="$OUTLOOK_REFRESH_TOKEN" \
    OWA_TENANT_ID="$OUTLOOK_TENANT_ID" \
    "$SCRIPT_DIR/../owa-piggy/owa-piggy" "$@"
  else
    error_log "owa-piggy not found. Add it to PATH or place it at ../owa-piggy/owa-piggy"
    return 1
  fi
}

# --- Auth setup ---
AUTH_HEADER=""
API_BASE=""
API_CASE="pascal" # pascal (Outlook) or camel (Graph)

# Exchange OUTLOOK_REFRESH_TOKEN for a new access token.
# Uses OUTLOOK_APP_CLIENT_ID (app registration) if set, otherwise owa-piggy.
# On success: sets OUTLOOK_TOKEN, persists rotated refresh token to .env, returns 0.
# On failure: returns 1.
do_token_refresh() {
  if [[ -z "$OUTLOOK_REFRESH_TOKEN" || -z "$OUTLOOK_TENANT_ID" ]]; then
    return 1
  fi

  local result
  if [[ -n "$OUTLOOK_APP_CLIENT_ID" ]]; then
    debug_log "Auth: using app registration (${OUTLOOK_APP_CLIENT_ID})"
    result=$(curl -s -X POST \
      "https://login.microsoftonline.com/${OUTLOOK_TENANT_ID}/oauth2/v2.0/token" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      --data-urlencode "grant_type=refresh_token" \
      --data-urlencode "client_id=${OUTLOOK_APP_CLIENT_ID}" \
      --data-urlencode "refresh_token=${OUTLOOK_REFRESH_TOKEN}" \
      --data-urlencode "scope=https://outlook.office.com/Calendars.ReadWrite openid profile offline_access" \
      2>/dev/null)
  else
    debug_log "Auth: using owa-piggy"
    result=$(_owa_piggy --json 2>/dev/null)
  fi

  if [[ -z "$result" ]]; then
    return 1
  fi

  local new_access new_refresh
  new_access=$(echo "$result" | jq -r '.access_token // empty')
  new_refresh=$(echo "$result" | jq -r '.refresh_token // empty')

  if [[ -z "$new_access" ]]; then
    debug_log "Auth: exchange failed: $(echo "$result" | jq -r '.error_description // .error // "unknown"' 2>/dev/null)"
    return 1
  fi

  OUTLOOK_TOKEN="$new_access"

  # Persist rotated refresh token (single-use)
  if [[ -n "$new_refresh" ]]; then
    OUTLOOK_REFRESH_TOKEN="$new_refresh"
    local tmpfile
    tmpfile=$(mktemp)
    awk -v val="$new_refresh" '/^OUTLOOK_REFRESH_TOKEN=/{print "OUTLOOK_REFRESH_TOKEN=\"" val "\""; next} {print}' .env > "$tmpfile" && mv "$tmpfile" .env
  fi

  local exp remaining
  exp=$(echo "$new_access" | cut -d'.' -f2 | (cat; echo '==') | base64 -d 2>/dev/null | jq -r '.exp // 0' 2>/dev/null)
  remaining=$(( (exp - $(date +%s)) / 60 ))
  debug_log "Auth: token exchange succeeded (${remaining}min remaining)"
  return 0
}

setup_auth() {
  if [[ -n "$OUTLOOK_REFRESH_TOKEN" && -n "$OUTLOOK_TENANT_ID" ]]; then
    if do_token_refresh; then
      AUTH_HEADER="Authorization: Bearer $OUTLOOK_TOKEN"
      API_BASE="https://outlook.office.com/api/v2.0"
      API_CASE="pascal"
      return
    else
      error_log "Token refresh failed. Check OUTLOOK_REFRESH_TOKEN and OUTLOOK_TENANT_ID in .env"
      exit 1
    fi
  fi

  error_log "No auth configured. Set OUTLOOK_REFRESH_TOKEN + OUTLOOK_TENANT_ID in .env"
  exit 1
}

# --- API helper ---
# All output goes to stdout as JSON. Errors go to stderr.
api_request() {
  local method="${1:-GET}"
  local endpoint="$2"
  local body="$3"
  local url="${API_BASE}/${endpoint}"

  debug_log "$method $url"
  [[ -n "$body" ]] && debug_log "Body: $body"

  local curl_args=(-s -w "\n%{http_code}" -X "$method" -H "$AUTH_HEADER")
  if [[ -n "$body" ]]; then
    curl_args+=(-H "Content-Type: application/json" -d "$body")
  fi

  local response
  response=$(curl "${curl_args[@]}" "$url")

  local http_code
  http_code=$(echo "$response" | tail -1)
  local body_response
  body_response=$(echo "$response" | sed '$d')

  case "$http_code" in
    2*) ;; # success
    401)
      error_log "Auth expired (401). Run: cal-cli refresh"
      exit 1 ;;
    403)
      error_log "Access denied (403). Check permissions."
      exit 1 ;;
    404)
      error_log "Not found (404)."
      return 1 ;;
    429)
      error_log "Rate limited (429). Try again later."
      return 1 ;;
    *)
      error_log "HTTP $http_code"
      debug_log "$body_response"
      return 1 ;;
  esac

  echo "$body_response"
}

# --- Response normalization ---
# Normalize Outlook PascalCase / Graph camelCase to consistent camelCase output
# Converts timestamps to local timezone, respecting the TimeZone field from the API

NORMALIZE_PY='
import json, sys
from datetime import datetime, timezone, timedelta
import time

local_offset = timedelta(seconds=-time.timezone if time.daylight == 0 else -time.altzone)
tz_local = timezone(local_offset)

# Map Windows timezone names to UTC offsets (common European ones + UTC)
TZ_OFFSETS = {
    "UTC": 0,
    "W. Europe Standard Time": 1, "Romance Standard Time": 1,
    "Central European Standard Time": 1, "Central Europe Standard Time": 1,
    "E. Europe Standard Time": 2, "FLE Standard Time": 2,
    "GTB Standard Time": 2, "Eastern Standard Time": -5,
    "Pacific Standard Time": -8, "Mountain Standard Time": -7,
    "Central Standard Time": -6, "GMT Standard Time": 0,
}
# DST: add 1h for European zones between last Sunday of March and last Sunday of October
def is_dst_europe(dt):
    if dt.month < 3 or dt.month > 10: return False
    if dt.month > 3 and dt.month < 10: return True
    # March or October: check last Sunday
    last_sunday = max(d for d in range(25, 32) if datetime(dt.year, dt.month, d).weekday() == 6)
    if dt.month == 3: return dt.day >= last_sunday
    return dt.day < last_sunday

def to_local(dt_str, tz_name=""):
    if not dt_str: return dt_str
    clean = dt_str.split(".")[0].replace("Z", "")
    try:
        dt = datetime.fromisoformat(clean)
    except:
        return dt_str

    # If the datetime already has offset info, use it
    if dt.tzinfo is not None:
        return dt.astimezone(tz_local).strftime("%Y-%m-%dT%H:%M:%S")

    # Check if the API-provided TimeZone tells us the source timezone
    if tz_name in TZ_OFFSETS:
        base_offset = TZ_OFFSETS[tz_name]
        # Only apply DST for non-UTC European zones
        dst_extra = 1 if base_offset != 0 and is_dst_europe(dt) and -1 <= base_offset <= 3 else 0
        source_tz = timezone(timedelta(hours=base_offset + dst_extra))
        dt = dt.replace(tzinfo=source_tz)
        return dt.astimezone(tz_local).strftime("%Y-%m-%dT%H:%M:%S")

    # No timezone info: assume UTC (Outlook REST API default)
    dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz_local).strftime("%Y-%m-%dT%H:%M:%S")

def normalize(e):
    s = e.get("Start") or e.get("start") or {}
    en = e.get("End") or e.get("end") or {}
    loc = e.get("Location") or e.get("location") or {}
    s_tz = s.get("TimeZone") or s.get("timeZone") or ""
    e_tz = en.get("TimeZone") or en.get("timeZone") or ""
    return {
        "id": e.get("Id") or e.get("id"),
        "subject": e.get("Subject") or e.get("subject"),
        "start": to_local(s.get("DateTime") or s.get("dateTime") or "", s_tz),
        "end": to_local(en.get("DateTime") or en.get("dateTime") or "", e_tz),
        "categories": e.get("Categories") or e.get("categories") or [],
        "location": loc.get("DisplayName") or loc.get("displayName") or "",
        "showAs": e.get("ShowAs") or e.get("showAs") or "",
        "isAllDay": e.get("IsAllDay") or e.get("isAllDay") or False,
    }
'

normalize_event() {
  python3 -c "${NORMALIZE_PY}
import codecs
raw = sys.stdin.buffer.read()
text = raw.decode('utf-8', errors='replace')
e = json.loads(text, strict=False)
print(json.dumps(normalize(e)))
"
}

normalize_events() {
  python3 -c "${NORMALIZE_PY}
import codecs
raw = sys.stdin.buffer.read()
text = raw.decode('utf-8', errors='replace')
data = json.loads(text, strict=False)
print(json.dumps([normalize(e) for e in data.get('value', [])]))
"
}

# --- Date helpers ---
today()     { date +%Y-%m-%d }
tomorrow()  { date -v+1d +%Y-%m-%d }
yesterday() { date -v-1d +%Y-%m-%d }

resolve_date() {
  case "$1" in
    today)     today ;;
    tomorrow)  tomorrow ;;
    yesterday) yesterday ;;
    *)         echo "$1" ;;
  esac
}

# Monday and Sunday of an ISO week
week_range() {
  local week="${1:-$(date +%V | sed 's/^0//')}"
  local year="${2:-$(date +%G)}"
  python3 -c "
from datetime import datetime, timedelta
d = datetime.strptime(f'${year}-W${week}-1', '%G-W%V-%u')
print(d.strftime('%Y-%m-%d'))
print((d + timedelta(days=6)).strftime('%Y-%m-%d'))
"
}

# Combine date + time into datetime string
make_datetime() {
  local date_val="$1" time_val="$2"
  if [[ -n "$time_val" ]]; then
    # Handle HH:MM or HH:MM:SS
    if [[ "$time_val" =~ ^[0-9]{1,2}:[0-9]{2}$ ]]; then
      echo "${date_val}T${time_val}:00"
    else
      echo "${date_val}T${time_val}"
    fi
  elif [[ "$date_val" == *T* ]]; then
    echo "$date_val"
  else
    echo "${date_val}T00:00:00"
  fi
}

# --- Pretty output ---
format_events_pretty() {
  jq -r '
    def pad(n): tostring | if length < n then . + (" " * (n - length)) else . end;
    def time_part: split("T")[1] // "" | split(":")[0:2] | join(":");
    def date_part: split("T")[0];

    if length == 0 then "No events found."
    else
      group_by(.start | date_part)
      | sort_by(.[0].start)
      | .[] |
      (.[0].start | date_part) as $date |
      "\($date)",
      (sort_by(.start) | .[] |
        "  \(.start | time_part)-\(.end | time_part)  \(.subject | pad(28))\(if .location != "" then .location + "  " else "" end)\(if (.categories | length) > 0 then "[\(.categories | join(", "))]" else "" end)"
      ),
      ""
    end
  '
}

# --- Build event JSON (handles both API casings) ---
build_event_json() {
  local subject="$1" start_dt="$2" end_dt="$3" tz="$4"
  local category="$5" location="$6" body_text="$7" allday="${8:-false}" showas="$9"

  if [[ "$API_CASE" == "camel" ]]; then
    : ${showas:=busy}
    jq -n \
      --arg s "$subject" --arg sd "$start_dt" --arg ed "$end_dt" --arg tz "$tz" \
      --arg cat "$category" --arg loc "$location" --arg bt "$body_text" \
      --argjson allday "$allday" --arg showas "$showas" \
      '{subject: $s, start: {dateTime: $sd, timeZone: $tz}, end: {dateTime: $ed, timeZone: $tz}, showAs: $showas, isAllDay: $allday, isReminderOn: false}
      + (if $cat != "" then {categories: [$cat]} else {} end)
      + (if $loc != "" then {location: {displayName: $loc}} else {} end)
      + (if $bt  != "" then {body: {contentType: "text", content: $bt}} else {} end)'
  else
    : ${showas:=Busy}
    jq -n \
      --arg s "$subject" --arg sd "$start_dt" --arg ed "$end_dt" --arg tz "$tz" \
      --arg cat "$category" --arg loc "$location" --arg bt "$body_text" \
      --argjson allday "$allday" --arg showas "$showas" \
      '{Subject: $s, Start: {DateTime: $sd, TimeZone: $tz}, End: {DateTime: $ed, TimeZone: $tz}, ShowAs: $showas, IsAllDay: $allday, IsReminderOn: false}
      + (if $cat != "" then {Categories: [$cat]} else {} end)
      + (if $loc != "" then {Location: {DisplayName: $loc}} else {} end)
      + (if $bt  != "" then {Body: {ContentType: "Text", Content: $bt}} else {} end)'
  fi
}

# --- Build PATCH JSON (only provided fields) ---
build_patch_json() {
  local patch='{}'

  while [[ $# -gt 0 ]]; do
    local key="$1" val="$2"
    shift 2

    case "$key" in
      subject)
        if [[ "$API_CASE" == "camel" ]]; then
          patch=$(echo "$patch" | jq --arg v "$val" '. + {subject: $v}')
        else
          patch=$(echo "$patch" | jq --arg v "$val" '. + {Subject: $v}')
        fi ;;
      category)
        if [[ "$API_CASE" == "camel" ]]; then
          patch=$(echo "$patch" | jq --arg v "$val" '. + {categories: [$v]}')
        else
          patch=$(echo "$patch" | jq --arg v "$val" '. + {Categories: [$v]}')
        fi ;;
      location)
        if [[ "$API_CASE" == "camel" ]]; then
          patch=$(echo "$patch" | jq --arg v "$val" '. + {location: {displayName: $v}}')
        else
          patch=$(echo "$patch" | jq --arg v "$val" '. + {Location: {DisplayName: $v}}')
        fi ;;
      showas)
        if [[ "$API_CASE" == "camel" ]]; then
          patch=$(echo "$patch" | jq --arg v "$val" '. + {showAs: $v}')
        else
          patch=$(echo "$patch" | jq --arg v "$val" '. + {ShowAs: $v}')
        fi ;;
      start)
        if [[ "$API_CASE" == "camel" ]]; then
          patch=$(echo "$patch" | jq --arg v "$val" --arg tz "$default_timezone" '. + {start: {dateTime: $v, timeZone: $tz}}')
        else
          patch=$(echo "$patch" | jq --arg v "$val" --arg tz "$default_timezone" '. + {Start: {DateTime: $v, TimeZone: $tz}}')
        fi ;;
      end)
        if [[ "$API_CASE" == "camel" ]]; then
          patch=$(echo "$patch" | jq --arg v "$val" --arg tz "$default_timezone" '. + {end: {dateTime: $v, timeZone: $tz}}')
        else
          patch=$(echo "$patch" | jq --arg v "$val" --arg tz "$default_timezone" '. + {End: {DateTime: $v, TimeZone: $tz}}')
        fi ;;
      body)
        if [[ "$API_CASE" == "camel" ]]; then
          patch=$(echo "$patch" | jq --arg v "$val" '. + {body: {contentType: "text", content: $v}}')
        else
          patch=$(echo "$patch" | jq --arg v "$val" '. + {Body: {ContentType: "Text", Content: $v}}')
        fi ;;
    esac
  done

  echo "$patch"
}

# ============================================================
# Subcommands
# ============================================================

cmd_events() {
  local date="" from="" to="" week="" year="" search="" pretty=0 limit=50

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --date)    date=$(resolve_date "$2"); shift 2 ;;
      --from)    from=$(resolve_date "$2"); shift 2 ;;
      --to)      to=$(resolve_date "$2"); shift 2 ;;
      --week)    week="$2"; shift 2 ;;
      --year)    year="$2"; shift 2 ;;
      --search)  search="$2"; shift 2 ;;
      --pretty)  pretty=1; shift ;;
      --limit)   limit="$2"; shift 2 ;;
      *) error_log "Unknown flag: $1"; exit 1 ;;
    esac
  done

  # Resolve date range
  if [[ -n "$week" ]]; then
    local range
    range=$(week_range "$week" "${year:-$(date +%G)}")
    from=$(echo "$range" | head -1)
    to=$(echo "$range" | tail -1)
  elif [[ -n "$date" ]]; then
    from="$date"
    to="$date"
  elif [[ -z "$from" ]]; then
    # Default: today
    from=$(today)
    to=$(today)
  fi
  [[ -z "$to" ]] && to="$from"

  local start_dt="${from}T00:00:00"
  local end_dt="${to}T23:59:59"

  debug_log "Events: $from to $to"

  # Select only the fields we need (Body contains HTML with control chars that break jq)
  local select_fields
  if [[ "$API_CASE" == "camel" ]]; then
    select_fields="id,subject,start,end,location,categories,showAs,isAllDay,originalStartTimeZone,originalEndTimeZone"
  else
    select_fields="Id,Subject,Start,End,Location,Categories,ShowAs,IsAllDay,OriginalStartTimeZone,OriginalEndTimeZone"
  fi

  # Escape single quotes for OData filter
  local safe_search="${search//\'/\'\'}"

  local data
  if [[ -n "$search" ]]; then
    # URL-encode the OData filter to handle spaces, &, and special chars
    local filter_field="Subject" orderby_field="Start/DateTime"
    [[ "$API_CASE" == "camel" ]] && filter_field="subject" && orderby_field="start/dateTime"
    local filter="contains(${filter_field},'${safe_search}')"
    local encoded_filter
    encoded_filter=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$filter")
    data=$(curl -s -w "\n%{http_code}" -X GET -H "$AUTH_HEADER" \
      "${API_BASE}/me/events?\$filter=${encoded_filter}&\$top=${limit}&\$orderby=${orderby_field}&\$select=${select_fields}")
    local http_code=$(echo "$data" | tail -1)
    data=$(echo "$data" | sed '$d')
    [[ "$http_code" != 2* ]] && { error_log "HTTP $http_code"; return 1; }
  else
    local orderby_field="Start/DateTime"
    [[ "$API_CASE" == "camel" ]] && orderby_field="start/dateTime"
    local endpoint="me/calendarView?startDateTime=${start_dt}&endDateTime=${end_dt}&\$top=${limit}&\$orderby=${orderby_field}&\$select=${select_fields}"
    data=$(api_request GET "$endpoint") || return 1
  fi

  if [[ "$pretty" -eq 1 ]]; then
    echo "$data" | normalize_events | format_events_pretty
  else
    echo "$data" | normalize_events
  fi
}

cmd_create() {
  local subject="" date="" start_time="" end_time="" category="" location="" body_text="" allday=false showas=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --subject)   subject="$2"; shift 2 ;;
      --date)      date=$(resolve_date "$2"); shift 2 ;;
      --start)     start_time="$2"; shift 2 ;;
      --end)       end_time="$2"; shift 2 ;;
      --category)  category="$2"; shift 2 ;;
      --location)  location="$2"; shift 2 ;;
      --body)      body_text="$2"; shift 2 ;;
      --allday)    allday=true; shift ;;
      --showas)    showas="$2"; shift 2 ;;
      *) error_log "Unknown flag: $1"; exit 1 ;;
    esac
  done

  if [[ -z "$subject" ]]; then
    error_log "--subject is required"
    exit 1
  fi

  : ${date:=$(today)}
  : ${start_time:="09:00"}
  : ${end_time:="10:00"}

  local start_dt=$(make_datetime "$date" "$start_time")
  local end_dt=$(make_datetime "$date" "$end_time")

  local event_json
  event_json=$(build_event_json "$subject" "$start_dt" "$end_dt" "$default_timezone" "$category" "$location" "$body_text" "$allday" "$showas")

  debug_log "Creating event: $(echo "$event_json" | jq -c .)"

  local result
  result=$(api_request POST "me/events" "$event_json")
  local created
  created=$(echo "$result" | normalize_event)
  echo "$created"

  # Post-creation duplicate check: query all events on the same day (normalized),
  # then compare against the just-created event to detect duplicates.
  local created_subject created_start created_end created_id
  created_subject=$(echo "$created" | jq -r '.subject')
  created_start=$(echo "$created" | jq -r '.start')
  created_end=$(echo "$created" | jq -r '.end')
  created_id=$(echo "$created" | jq -r '.id')

  local check_date="${date}"
  local select_fields="Id,Subject,Start,End"
  [[ "$API_CASE" == "camel" ]] && select_fields="id,subject,start,end"
  local orderby_field="Start/DateTime"
  [[ "$API_CASE" == "camel" ]] && orderby_field="start/dateTime"

  local check_start="${check_date}T00:00:00"
  local check_end="${check_date}T23:59:59"
  local existing
  existing=$(api_request GET "me/calendarView?startDateTime=${check_start}&endDateTime=${check_end}&\$top=50&\$orderby=${orderby_field}&\$select=${select_fields}" 2>/dev/null) || return 0

  # Normalize the existing events to local time, then compare against created event
  local normalized_existing
  normalized_existing=$(echo "$existing" | normalize_events 2>/dev/null) || return 0

  local dup_count
  dup_count=$(python3 -c "
import json, sys
events = json.loads(sys.argv[1])
target_id = sys.argv[2]
target_subj = sys.argv[3]
target_start = sys.argv[4]
target_end = sys.argv[5]
dupes = [e for e in events
  if e.get('subject') == target_subj
  and e.get('id') != target_id
  and e.get('start') == target_start
  and e.get('end') == target_end]
print(len(dupes))
" "$normalized_existing" "$created_id" "$created_subject" "$created_start" "$created_end" 2>/dev/null)

  if [[ -n "$dup_count" && "$dup_count" -gt 0 ]]; then
    echo -e "\033[33m⚠ Warning: Found $dup_count other event(s) with same subject/time on $check_date. Possible duplicates.\033[0m" >&2
  fi
}

cmd_update() {
  local id="" patch_args=()
  local date="" start_time="" end_time=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --id)        id="$2"; shift 2 ;;
      --subject)   patch_args+=(subject "$2"); shift 2 ;;
      --category)  patch_args+=(category "$2"); shift 2 ;;
      --location)  patch_args+=(location "$2"); shift 2 ;;
      --body)      patch_args+=(body "$2"); shift 2 ;;
      --showas)    patch_args+=(showas "$2"); shift 2 ;;
      --date)      date=$(resolve_date "$2"); shift 2 ;;
      --start)     start_time="$2"; shift 2 ;;
      --end)       end_time="$2"; shift 2 ;;
      *) error_log "Unknown flag: $1"; exit 1 ;;
    esac
  done

  if [[ -z "$id" ]]; then
    error_log "--id is required"
    exit 1
  fi

  # For date/time changes, fetch the existing event to preserve untouched components
  if [[ -n "$start_time" || -n "$end_time" || -n "$date" ]]; then
    local existing
    existing=$(api_request GET "me/events/$id" 2>/dev/null | normalize_event)
    local existing_start existing_end existing_date
    existing_start=$(echo "$existing" | jq -r '.start // empty')
    existing_end=$(echo "$existing" | jq -r '.end // empty')
    # Extract date and time parts from existing event
    local existing_date_part="${existing_start%%T*}"
    local existing_start_time="${existing_start##*T}"
    local existing_end_time="${existing_end##*T}"

    # Merge: use provided values, fall back to existing
    local patch_date="${date:-$existing_date_part}"
    if [[ -n "$start_time" ]]; then
      patch_args+=(start "$(make_datetime "$patch_date" "$start_time")")
    elif [[ -n "$date" ]]; then
      # Date changed but not start time - keep the original time
      patch_args+=(start "$(make_datetime "$patch_date" "$existing_start_time")")
    fi
    if [[ -n "$end_time" ]]; then
      patch_args+=(end "$(make_datetime "$patch_date" "$end_time")")
    elif [[ -n "$date" ]]; then
      # Date changed but not end time - keep the original time
      patch_args+=(end "$(make_datetime "$patch_date" "$existing_end_time")")
    fi
  fi

  local patch
  patch=$(build_patch_json "${patch_args[@]}")

  local result
  result=$(api_request PATCH "me/events/$id" "$patch")
  echo "$result" | normalize_event
}

cmd_delete() {
  local id="" confirm=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --id)      id="$2"; shift 2 ;;
      --confirm) confirm=1; shift ;;
      *) error_log "Unknown flag: $1"; exit 1 ;;
    esac
  done

  if [[ -z "$id" ]]; then
    error_log "--id is required"
    exit 1
  fi

  # Show what we're about to delete
  if [[ "$confirm" -eq 0 ]]; then
    local event
    event=$(api_request GET "me/events/$id" | normalize_event)
    local subj start_time
    subj=$(echo "$event" | jq -r '.subject')
    start_time=$(echo "$event" | jq -r '.start')
    print -P -n "%F{yellow}Delete '$subj' ($start_time)? (y/N): %f" >&2
    read -r answer
    if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
      info_log "Aborted."
      exit 0
    fi
  fi

  api_request DELETE "me/events/$id" >/dev/null
  info_log "Deleted."
}

cmd_categories() {
  local add=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --add) add="$2"; shift 2 ;;
      *) error_log "Unknown flag: $1"; exit 1 ;;
    esac
  done

  if [[ -n "$add" ]]; then
    local body
    if [[ "$API_CASE" == "camel" ]]; then
      body=$(jq -n --arg n "$add" '{displayName: $n, color: "preset0"}')
    else
      body=$(jq -n --arg n "$add" '{DisplayName: $n, Color: "Preset0"}')
    fi
    api_request POST "me/outlook/masterCategories" "$body" | jq .
  else
    local data
    data=$(api_request GET "me/outlook/masterCategories")
    echo "$data" | jq -r '.value[] | "\((.DisplayName // .displayName))\t\((.Color // .color))"' | column -t -s $'\t'
  fi
}

cmd_config() {
  local refresh_token="" tenant_id="" app_client_id=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --refresh-token)  refresh_token="$2"; shift 2 ;;
      --tenant-id)      tenant_id="$2"; shift 2 ;;
      --app-client-id)  app_client_id="$2"; shift 2 ;;
      *) error_log "Unknown flag: $1"; exit 1 ;;
    esac
  done

  if [[ -n "$refresh_token" ]]; then
    local tmpfile=$(mktemp)
    awk -v val="$refresh_token" '/^OUTLOOK_REFRESH_TOKEN=/{print "OUTLOOK_REFRESH_TOKEN=\"" val "\""; next} {print}' .env > "$tmpfile" && mv "$tmpfile" .env
    info_log "Refresh token saved"
  fi

  if [[ -n "$tenant_id" ]]; then
    if grep -q '^OUTLOOK_TENANT_ID=' .env; then
      sed -i '' "s|^OUTLOOK_TENANT_ID=.*|OUTLOOK_TENANT_ID=\"$tenant_id\"|" .env
    else
      echo "OUTLOOK_TENANT_ID=\"$tenant_id\"" >> .env
    fi
    info_log "Tenant ID saved"
  fi

  if [[ -n "$app_client_id" ]]; then
    if grep -q '^OUTLOOK_APP_CLIENT_ID=' .env; then
      sed -i '' "s|^OUTLOOK_APP_CLIENT_ID=.*|OUTLOOK_APP_CLIENT_ID=\"$app_client_id\"|" .env
    else
      echo "OUTLOOK_APP_CLIENT_ID=\"$app_client_id\"" >> .env
    fi
    info_log "App client ID saved"
  fi

  if [[ -z "$refresh_token" && -z "$tenant_id" && -z "$app_client_id" ]]; then
    info_log "Current config:"
    if [[ -n "$OUTLOOK_REFRESH_TOKEN" ]]; then
      info_log "  OUTLOOK_REFRESH_TOKEN=set (tenant: ${OUTLOOK_TENANT_ID:-not set})"
    else
      info_log "  OUTLOOK_REFRESH_TOKEN=(not set)"
    fi
    if [[ -n "$OUTLOOK_APP_CLIENT_ID" ]]; then
      info_log "  OUTLOOK_APP_CLIENT_ID=$OUTLOOK_APP_CLIENT_ID (app registration)"
    else
      info_log "  OUTLOOK_APP_CLIENT_ID=(not set - using owa-piggy)"
    fi
    info_log "  default_timezone=$default_timezone"
    info_log "  API: ${API_BASE:-(auth not yet run)}"
  fi
}

cmd_refresh() {
  if [[ -z "$OUTLOOK_REFRESH_TOKEN" || -z "$OUTLOOK_TENANT_ID" ]]; then
    error_log "OUTLOOK_REFRESH_TOKEN and OUTLOOK_TENANT_ID must be set in .env"
    exit 1
  fi

  info_log "Refreshing token..."

  if do_token_refresh; then
    AUTH_HEADER="Authorization: Bearer $OUTLOOK_TOKEN"
    API_BASE="https://outlook.office.com/api/v2.0"
    API_CASE="pascal"
    local me name
    me=$(api_request GET "me" 2>/dev/null)
    name=$(echo "$me" | jq -r '.DisplayName // .displayName // empty' 2>/dev/null)
    [[ -n "$name" ]] && info_log "Authenticated as $name"
  else
    error_log "Token refresh failed."
    exit 1
  fi
}

cmd_help() {
  cat >&2 <<'HELP'
cal-cli - Calendar CLI for Outlook / Microsoft 365

Usage: cal-cli <command> [options]

Commands:
  refresh             Force a token refresh and verify auth
  events              List calendar events (default: today)
  create              Create a new event
  update              Update an existing event
  delete              Delete an event
  categories          List or add master categories
  config              View or update configuration
  help                Show this help

Events options:
  --date <date>       Specific day (YYYY-MM-DD, today, tomorrow, yesterday)
  --from <date>       Start of range
  --to <date>         End of range
  --week <n>          ISO week number
  --year <n>          Year (default: current)
  --search <term>     Search events by subject
  --pretty            Human-readable table (default: JSON)
  --limit <n>         Max results (default: 50)

Create options:
  --subject <title>   Event title (required)
  --date <date>       Date (default: today)
  --start <HH:MM>     Start time (default: 09:00)
  --end <HH:MM>       End time (default: 10:00)
  --category <name>   Category for DID project mapping
  --location <place>  Location
  --body <text>       Description
  --allday            All-day event
  --showas <status>   busy, free, tentative, oof

Update options:
  --id <event-id>     Event ID (required)
  --subject, --date, --start, --end, --category,
  --location, --body, --showas

Delete options:
  --id <event-id>     Event ID (required)
  --confirm           Skip confirmation prompt

Categories options:
  --add <name>        Add a new master category
  (no flags)          List all categories

Config options:
  --refresh-token <v> Set MSAL refresh token
  --tenant-id <id>    Set Azure AD tenant ID
  --app-client-id <id> Set app registration client ID (optional)

Auth:
  Requires OUTLOOK_REFRESH_TOKEN + OUTLOOK_TENANT_ID in .env.

  If OUTLOOK_APP_CLIENT_ID is set, uses that app registration directly
  (standard OAuth2 refresh_token grant - more durable, recommended for
  registered apps).

  Otherwise falls back to owa-piggy, which piggybacks on OWA's public
  SPA client - no app registration needed, but requires owa-piggy on PATH
  (or at ../owa-piggy/owa-piggy).

  Setup (app registration):
    1. Register an app in Azure AD with Calendars.ReadWrite delegated permission
    2. Run device code or auth code flow to get a refresh token
    3. cal-cli config --refresh-token "1.AQ..." --tenant-id "8f47ad71-..." \
                      --app-client-id "your-client-id"

  Setup (owa-piggy, no app registration):
    1. owa-piggy --save-config  (one-time interactive setup)
    2. cal-cli config --refresh-token "$(owa-piggy --json | jq -r .refresh_token)" \
                      --tenant-id "your-tenant-id"

Examples:
  cal-cli events --pretty
  cal-cli events --week 16 --pretty
  cal-cli events --from 2026-04-14 --to 2026-04-18 --pretty
  cal-cli create --subject "lunsj" --start 11:00 --end 11:30 --category "CC LUNCH"
  cal-cli create --subject "Standup" --date tomorrow --start 09:00 --end 09:30
  cal-cli update --id AAMkAG... --category "ProjectX"
  cal-cli delete --id AAMkAG...
  cal-cli categories
HELP
}

# --- Main ---
# Skip auth for commands that don't need it
case "${1:-help}" in
  refresh|config|help|--help|-h) ;;
  *) setup_auth ;;
esac

case "${1:-help}" in
  refresh)    shift; cmd_refresh "$@" ;;
  events)     shift; cmd_events "$@" ;;
  create)     shift; cmd_create "$@" ;;
  update)     shift; cmd_update "$@" ;;
  delete)     shift; cmd_delete "$@" ;;
  categories) shift; cmd_categories "$@" ;;
  config)     shift; cmd_config "$@" ;;
  help|--help|-h) cmd_help ;;
  *) error_log "Unknown command: $1. Run 'cal-cli help' for usage."; exit 1 ;;
esac

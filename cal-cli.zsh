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
: ${use_oauth:=0}
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

# --- Auth setup ---
AUTH_HEADER=""
API_BASE=""
API_CASE="pascal" # pascal (Outlook) or camel (Graph)

setup_auth() {
  # Priority: 1. JWT token  2. OAuth via get-token  3. Cookie

  # 1. JWT token from Outlook Web (grab from DevTools, ~65 min lifetime)
  if [[ -n "$OUTLOOK_TOKEN" ]]; then
    # Check if token is expired (best-effort, works for standard JWTs)
    local exp
    exp=$(echo "$OUTLOOK_TOKEN" | cut -d'.' -f2 | (cat; echo '==') | base64 -d 2>/dev/null | jq -r '.exp // 0' 2>/dev/null)
    local now=$(date +%s)
    if [[ "$exp" -gt "$now" ]]; then
      AUTH_HEADER="Authorization: Bearer $OUTLOOK_TOKEN"
      API_BASE="https://outlook.office.com/api/v2.0"
      API_CASE="pascal"
      local remaining=$(( (exp - now) / 60 ))
      debug_log "Auth: JWT token (outlook.office.com, ${remaining}min remaining)"
      return
    else
      info_log "JWT token expired. Falling back..." >&2
    fi
  fi

  # 2. OAuth via get-token (if enabled)
  if [[ "$use_oauth" -eq 1 ]]; then
    if command -v get-token &>/dev/null; then
      local token
      token=$(get-token 2>/dev/null)
      if [[ -n "$token" ]]; then
        AUTH_HEADER="Authorization: Bearer $token"
        API_BASE="https://graph.microsoft.com/v1.0"
        API_CASE="camel"
        debug_log "Auth: OAuth token (graph.microsoft.com)"
        return
      fi
    fi
    debug_log "OAuth failed, falling back to cookie"
  fi

  # 3. Cookie auth (full Cookie header from DevTools)
  if [[ -n "$OUTLOOK_COOKIE" ]]; then
    AUTH_HEADER="Cookie: $OUTLOOK_COOKIE"
    API_BASE="https://outlook.office.com/api/v2.0"
    API_CASE="pascal"
    debug_log "Auth: cookie (outlook.office.com)"
  else
    error_log "No auth configured. Set OUTLOOK_TOKEN or OUTLOOK_COOKIE in .env, or enable OAuth with use_oauth=1"
    exit 1
  fi
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
      error_log "Auth expired (401). Refresh your cookie or re-run get-token."
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
e = json.load(sys.stdin)
print(json.dumps(normalize(e)))
"
}

normalize_events() {
  python3 -c "${NORMALIZE_PY}
data = json.load(sys.stdin)
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
  echo "$result" | normalize_event
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
  local token="" cookie="" oauth=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --token)  token="$2"; shift 2 ;;
      --cookie) cookie="$2"; shift 2 ;;
      --oauth)  oauth="$2"; shift 2 ;;
      *) error_log "Unknown flag: $1"; exit 1 ;;
    esac
  done

  if [[ -n "$token" ]]; then
    # Strip "Bearer " prefix if included
    token="${token#Bearer }"
    if grep -q '^OUTLOOK_TOKEN=' .env; then
      # Token is too long for sed, rewrite the line
      local tmpfile=$(mktemp)
      awk -v val="$token" '/^OUTLOOK_TOKEN=/{print "OUTLOOK_TOKEN=\"" val "\""; next} {print}' .env > "$tmpfile" && mv "$tmpfile" .env
    else
      echo "OUTLOOK_TOKEN=\"$token\"" >> .env
    fi
    info_log "JWT token updated"
    # Show expiry
    local exp
    exp=$(echo "$token" | cut -d'.' -f2 | (cat; echo '==') | base64 -d 2>/dev/null | jq -r '.exp // 0' 2>/dev/null)
    if [[ "$exp" -gt 0 ]]; then
      local now=$(date +%s)
      local remaining=$(( (exp - now) / 60 ))
      if [[ $remaining -gt 0 ]]; then
        info_log "Token valid for ${remaining} more minutes"
      else
        info_log "Warning: token is already expired"
      fi
    fi
  fi

  if [[ -n "$cookie" ]]; then
    if grep -q '^OUTLOOK_COOKIE=' .env; then
      local tmpfile=$(mktemp)
      awk -v val="$cookie" '/^OUTLOOK_COOKIE=/{print "OUTLOOK_COOKIE=\"" val "\""; next} {print}' .env > "$tmpfile" && mv "$tmpfile" .env
    else
      echo "OUTLOOK_COOKIE=\"$cookie\"" >> .env
    fi
    info_log "Cookie updated"
  fi

  if [[ -n "$oauth" ]]; then
    if grep -q '^use_oauth=' .env; then
      sed -i '' "s|^use_oauth=.*|use_oauth=$oauth|" .env
    else
      echo "use_oauth=$oauth" >> .env
    fi
    info_log "OAuth set to $oauth"
  fi

  if [[ -z "$token" && -z "$cookie" && -z "$oauth" ]]; then
    info_log "Current config:"
    if [[ -n "$OUTLOOK_TOKEN" ]]; then
      local exp
      exp=$(echo "$OUTLOOK_TOKEN" | cut -d'.' -f2 | (cat; echo '==') | base64 -d 2>/dev/null | jq -r '.exp // 0' 2>/dev/null)
      local now=$(date +%s)
      local remaining=$(( (exp - now) / 60 ))
      if [[ $remaining -gt 0 ]]; then
        info_log "  OUTLOOK_TOKEN=set (${remaining}min remaining)"
      else
        info_log "  OUTLOOK_TOKEN=set (EXPIRED)"
      fi
    else
      info_log "  OUTLOOK_TOKEN=(not set)"
    fi
    if [[ -n "$OUTLOOK_COOKIE" ]]; then
      info_log "  OUTLOOK_COOKIE=$(echo "$OUTLOOK_COOKIE" | cut -c1-40)..."
    else
      info_log "  OUTLOOK_COOKIE=(not set)"
    fi
    info_log "  use_oauth=$use_oauth"
    info_log "  default_timezone=$default_timezone"
    info_log "  API: $API_BASE"
  fi
}

cmd_login() {
  local token=""

  # Check clipboard first (from bookmarklet)
  if command -v pbpaste &>/dev/null; then
    local clip
    clip=$(pbpaste 2>/dev/null)
    if [[ "$clip" == eyJ* ]] || [[ "$clip" == Bearer\ eyJ* ]]; then
      token="${clip#Bearer }"
      info_log "Found JWT in clipboard"
    fi
  fi

  if [[ -z "$token" ]]; then
    info_log "Grab a token from Outlook:"
    info_log ""
    info_log "  Option A: Use the bookmarklet (one click)"
    info_log "    Add this as a bookmark, click it on outlook.cloud.microsoft:"
    info_log "    (see cal-cli help for the bookmarklet URL)"
    info_log ""
    info_log "  Option B: DevTools > Network > any outlook.office.com API request"
    info_log "    Copy the Authorization: Bearer eyJ... header"
    info_log ""
    info_log "Then either:"
    info_log "  - Run cal-cli login again (reads clipboard automatically)"
    info_log "  - Or paste below:"
    info_log ""

    open "https://outlook.cloud.microsoft/calendar" 2>/dev/null

    print -P -n "%F{cyan}Token: %f" >&2
    read -r token

    if [[ -z "$token" ]]; then
      error_log "No token provided."
      exit 1
    fi
  fi

  # Strip "Bearer " prefix
  token="${token#Bearer }"

  if [[ "$token" != eyJ* ]]; then
    error_log "Doesn't look like a JWT (should start with eyJ)."
    exit 1
  fi

  # Save it
  cmd_config --token "$token"

  # Verify
  source .env
  OUTLOOK_TOKEN="$token"
  AUTH_HEADER="Authorization: Bearer $OUTLOOK_TOKEN"
  API_BASE="https://outlook.office.com/api/v2.0"
  API_CASE="pascal"

  local me
  me=$(api_request GET "me" 2>/dev/null)
  local name
  name=$(echo "$me" | jq -r '.DisplayName // .displayName // empty' 2>/dev/null)

  if [[ -n "$name" ]]; then
    info_log "Authenticated as $name"
  else
    error_log "Token saved but verification failed. It may already be expired."
  fi
}

cmd_setup() {
  info_log "Setting up automated token refresh..."
  info_log "This restarts your default browser with remote debugging (port 9222)."
  info_log "Tabs and session are preserved."
  info_log ""
  "$SCRIPT_DIR/scripts/vivaldi-debug.sh"
  info_log ""
  info_log "Open Outlook in the browser, then run: cal-cli refresh"
}

cmd_refresh() {
  info_log "Refreshing token via browser CDP..."

  local token
  token=$(python3 "$SCRIPT_DIR/scripts/refresh-token.py")

  if [[ -n "$token" && "$token" == eyJ* ]]; then
    cmd_config --token "$token"

    # Verify
    source .env
    OUTLOOK_TOKEN="$token"
    AUTH_HEADER="Authorization: Bearer $OUTLOOK_TOKEN"
    API_BASE="https://outlook.office.com/api/v2.0"
    API_CASE="pascal"

    local me
    me=$(api_request GET "me" 2>/dev/null)
    local name
    name=$(echo "$me" | jq -r '.DisplayName // .displayName // empty' 2>/dev/null)
    if [[ -n "$name" ]]; then
      info_log "Authenticated as $name"
    fi
  else
    error_log "Token refresh failed. Use: cal-cli login"
  fi
}

cmd_help() {
  cat >&2 <<'HELP'
cal-cli - Calendar CLI for Outlook / Microsoft 365

Usage: cal-cli <command> [options]

Commands:
  login               Grab a fresh JWT from Outlook (interactive)
  setup               Restart browser with remote debugging (one-time)
  refresh             Headless token refresh via browser CDP (no UI)
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
  --token <jwt>       Set JWT from Outlook Web (primary, ~65min)
  --cookie <value>    Set full cookie header from DevTools
  --oauth <0|1>       Enable/disable OAuth via get-token

Auth (tried in order):
  1. JWT token from Outlook Web (~65 min lifetime, full permissions)
  2. OAuth via get-token (requires Calendars.ReadWrite scope)
  3. Session cookie from outlook.office.com

  Quickest: bookmarklet (copies token to clipboard automatically)
  Add this URL as a bookmark, click it on outlook.cloud.microsoft,
  then click anything in Outlook (switch folder, open email) to
  trigger an API call. The token gets intercepted and copied.

  javascript:void((async()=>{let t=null;const of=window.fetch;window.fetch=function(...a){const[input,opts]=a;let auth=null;if(input instanceof Request)auth=input.headers.get('authorization');else if(opts?.headers instanceof Headers)auth=opts.headers.get('authorization');else if(opts?.headers)auth=opts.headers.Authorization||opts.headers.authorization;if(auth?.startsWith('Bearer ')&&!t){try{const p=JSON.parse(atob(auth.slice(7).split('.')[1]));if(p.aud?.includes('outlook.office.com'))t=auth.slice(7)}catch{}}return of.apply(this,a)};for(let i=0;i<150&&!t;i++)await new Promise(r=>setTimeout(r,100));window.fetch=of;if(t){const p=JSON.parse(atob(t.split('.')[1]));await navigator.clipboard.writeText(t);alert('Token copied! '+Math.round((p.exp-Date.now()/1000)/60)+'min left')}else alert('No token captured. Click something in Outlook, then try again.')})())

  Then: cal-cli login  (reads clipboard automatically on macOS)

  Manual: DevTools (F12) > Network > any outlook.office.com API request
  Copy Authorization header > cal-cli config --token "eyJ..."

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
  login|setup|refresh|config|help|--help|-h) ;;
  *) setup_auth ;;
esac

case "${1:-help}" in
  login)      shift; cmd_login "$@" ;;
  setup)      shift; cmd_setup "$@" ;;
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

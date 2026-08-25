"""SWODP query builders, write validation, and timesheet operations."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date, timedelta

from owa_core.errors import ConflictError, NotFoundError, ScopeInsufficientError, UsageError

from . import api

DAY_FIELDS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DESCRIPTION_FIELD = "comments"
TASK_RE = re.compile(r"^T[0-9A-Z]{5,30}$")
SYS_ID_RE = re.compile(r"^[0-9a-f]{32}$")
CATEGORY_RE = re.compile(r"^[a-z0-9_ -]{2,40}$", re.IGNORECASE)


def parse_iso_date(value, *, name="date"):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise UsageError(f"{name} must be YYYY-MM-DD") from exc


def card_range(week_start, weeks=3):
    start = parse_iso_date(week_start, name="week start")
    if start.weekday() != 0:
        raise UsageError("week start must be a Monday")
    if weeks < 0 or weeks > 52:
        raise UsageError("range weeks must be between 0 and 52")
    return start - timedelta(weeks=weeks), start + timedelta(weeks=weeks)


def week_cards(session, week_start, *, weeks=3, debug=False):
    start, end = card_range(week_start, weeks)
    return api.request(
        session,
        "GET",
        "time_card",
        params={
            "sysparm_display_value": "true",
            "sysparm_fields": (
                "task.number,category,comments,week_starts_on,monday,tuesday,wednesday,"
                "thursday,friday,saturday,sunday,total,state"
            ),
            "sysparm_query": (
                f"user.user_name={session.user}^week_starts_on>={start.isoformat()}"
                f"^week_starts_on<={end.isoformat()}"
            ),
            "sysparm_limit": "500",
        },
        debug=debug,
    )


def probe(session, *, debug=False):
    rows = api.request(
        session,
        "GET",
        "time_card",
        params={
            "sysparm_fields": "sys_id",
            "sysparm_query": f"user.user_name={session.user}",
            "sysparm_limit": "1",
        },
        debug=debug,
    )
    return len(rows) if isinstance(rows, list) else 1


def history(session, *, debug=False):
    return api.request(
        session,
        "GET",
        "time_card",
        params={
            "sysparm_display_value": "true",
            "sysparm_fields": (
                "task.number,task.short_description,task.top_task.short_description,"
                "project_time_category,category,week_starts_on"
            ),
            "sysparm_query": f"user.user_name={session.user}^ORDERBYDESCweek_starts_on",
            "sysparm_limit": "1000",
        },
        debug=debug,
    )


def allocations(session, *, since=None, debug=False):
    since = since or (date.today() - timedelta(days=90)).isoformat()
    parse_iso_date(since, name="since")
    return api.request(
        session,
        "GET",
        "resource_allocation",
        params={
            "sysparm_display_value": "true",
            "sysparm_fields": (
                "resource_plan.task.number,resource_plan.task.short_description,"
                "resource_plan.task.top_task.short_description,start_date,end_date,state"
            ),
            "sysparm_query": f"user.user_name={session.user}^end_date>={since}",
            "sysparm_limit": "1000",
        },
        debug=debug,
    )


def categories(session, *, debug=False):
    rows = api.request(
        session,
        "GET",
        "time_card",
        params={
            "sysparm_display_value": "all",
            "sysparm_fields": "category",
            "sysparm_query": (
                f"user.user_name={session.user}^taskISEMPTY^ORDERBYDESCweek_starts_on"
            ),
            "sysparm_limit": "100",
        },
        debug=debug,
    )
    result = {}
    for row in rows:
        category = row.get("category") or {}
        if not isinstance(category, dict):
            continue
        display, value = category.get("display_value"), category.get("value")
        if display and value and display != "Project/Project Task":
            result[display] = value
    return result


def task_lookup(session, task_number, *, debug=False):
    if not TASK_RE.fullmatch(task_number or ""):
        raise UsageError("task number must match T followed by 5-30 uppercase letters or digits")
    rows = api.request(
        session,
        "GET",
        "task",
        params={"sysparm_query": f"number={task_number}", "sysparm_fields": "sys_id,number"},
        debug=debug,
    )
    return rows[0] if rows else None


def _card_in_state(session, sys_id, required_state, operation, *, debug=False):
    """Fetch one time card and require the state allowed for an operation."""
    if not SYS_ID_RE.fullmatch(sys_id or ""):
        raise UsageError("sys id must be 32 lowercase hex characters")
    record = api.request(
        session,
        "GET",
        "time_card",
        sys_id=sys_id,
        params={"sysparm_fields": "sys_id,state,category,task.number,total,week_starts_on"},
        debug=debug,
    )
    if isinstance(record, list):
        record = record[0] if record else {}
    if not record:
        raise NotFoundError(f"time card not found: {sys_id}")
    if record.get("state") != required_state:
        raise ConflictError(
            f"time card is {record.get('state') or 'in an unknown state'}; "
            f"only {required_state} cards may be {operation}"
        )
    return record


def _pending_card(session, sys_id, *, debug=False):
    """Fetch one time card and refuse to touch it unless it is Pending."""
    return _card_in_state(session, sys_id, "Pending", "changed", debug=debug)


def delete_card(session, sys_id, *, debug=False):
    card = _pending_card(session, sys_id, debug=debug)
    api.request(session, "DELETE", "time_card", sys_id=sys_id, debug=debug)
    return {"action": "deleted", "sys_id": sys_id, "card": card}


def submit_card(session, sys_id, *, debug=False):
    """Move one Pending card to Submitted through the portal processor."""
    card = _pending_card(session, sys_id, debug=debug)
    payload = api.processor(
        session,
        "updateTimeCardState",
        {"timecard_id": sys_id, "new_state": "Submitted"},
        debug=debug,
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    message = data.get("message") or payload.get("message") or ""
    if payload.get("status") != "success":
        raise ConflictError(f"SWODP refused the submit: {message or 'no reason given'}")
    state = api.request(
        session,
        "GET",
        "time_card",
        sys_id=sys_id,
        params={"sysparm_fields": "state"},
        debug=debug,
    )
    if isinstance(state, list):
        state = state[0] if state else {}
    result = {"action": "submitted", "sys_id": sys_id, "state": state.get("state"), "card": card}
    if message:
        result["message"] = message
    if state.get("state") != "Submitted":
        result["detail"] = f"state is {state.get('state') or 'unknown'} after a successful submit"
    return result


def validate_recall_reason(reason):
    if not isinstance(reason, str) or not reason.strip():
        raise UsageError("recall reason must be non-empty")
    return reason.strip()


def recall_card(session, sys_id, reason, *, debug=False):
    """Move one Submitted card to Recalled through the portal processor."""
    reason = validate_recall_reason(reason)
    card = _card_in_state(session, sys_id, "Submitted", "recalled", debug=debug)
    payload = api.processor(
        session,
        "updateTimeCardState",
        {"timecard_id": sys_id, "new_state": "Recalled", "reason": reason},
        debug=debug,
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    message = data.get("message") or payload.get("message") or ""
    if payload.get("status") != "success":
        raise ConflictError(f"SWODP refused the recall: {message or 'no reason given'}")
    state = api.request(
        session,
        "GET",
        "time_card",
        sys_id=sys_id,
        params={"sysparm_fields": "state"},
        debug=debug,
    )
    if isinstance(state, list):
        state = state[0] if state else {}
    result = {"action": "recalled", "sys_id": sys_id, "state": state.get("state"), "card": card}
    if message:
        result["message"] = message
    if state.get("state") != "Recalled":
        result["detail"] = f"state is {state.get('state') or 'unknown'} after a successful recall"
    return result


def sync(session, week_start, *, weeks=3, cards_only=False, debug=False):
    cards = week_cards(session, week_start, weeks=weeks, debug=debug)
    warnings = []
    if len(cards) >= 500:
        warnings.append("week cards reached the 500-row limit and may be truncated")
    if cards_only:
        result = {"weekCards": cards}
        if warnings:
            result["warnings"] = warnings
        return result

    def optional(label, consequence, function):
        try:
            return function()
        except ScopeInsufficientError:
            warnings.append(f"403 on {label}; {consequence}")
            return []

    history_rows = optional(
        "time_card history", "last-used activity dates are unavailable", lambda: history(session, debug=debug)
    )
    allocation_rows = optional(
        "resource_allocation",
        "only projects already present in time-card history are available",
        lambda: allocations(session, debug=debug),
    )
    category_map = optional(
        "time_card category map",
        "Other categories cannot be written until observed in tcp",
        lambda: categories(session, debug=debug),
    )
    if len(history_rows) >= 1000 or len(allocation_rows) >= 1000:
        warnings.append("history or allocations reached the 1000-row limit and may be truncated")
    result = {
        "history": history_rows,
        "allocations": allocation_rows,
        "weekCards": cards,
        "otherCategories": category_map,
    }
    if warnings:
        result["warnings"] = warnings
    return result


def validate_write_rows(rows):
    if not isinstance(rows, list) or not 0 < len(rows) <= 200:
        raise UsageError("write input must contain 1-200 rows")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise UsageError(f"row {index + 1} must be an object")
        task_ok = isinstance(row.get("taskNumber"), str) and bool(
            TASK_RE.fullmatch(row["taskNumber"])
        )
        category_ok = isinstance(row.get("category"), str) and bool(
            CATEGORY_RE.fullmatch(row["category"])
        )
        if task_ok == category_ok or ("taskNumber" in row and not task_ok) or (
            "category" in row and not category_ok
        ):
            raise UsageError(f"row {index + 1} must have exactly one valid taskNumber or category")
        days = row.get("days")
        if not isinstance(days, list) or len(days) != 7:
            raise UsageError(f"row {index + 1} must contain exactly 7 day values")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            or value > 24
            for value in days
        ):
            raise UsageError(f"row {index + 1} day values must be finite numbers from 0 to 24")
        if "description" in row and not isinstance(row["description"], str):
            raise UsageError(f"row {index + 1} description must be a string")
        # SWODP makes Description mandatory on time_card. A blank one creates a card
        # that cannot be submitted, so require it rather than warn after the write.
        if not row.get("remove") and not row.get("description", "").strip():
            raise UsageError(f"row {index + 1} requires a non-empty description")
        if "remove" in row and not isinstance(row["remove"], bool):
            raise UsageError(f"row {index + 1} remove must be boolean")
        if "split" in row and row["split"] is not True:
            raise UsageError(f"row {index + 1} split may only be true")
        if row.get("split") and row.get("remove"):
            raise UsageError(f"row {index + 1} split cannot remove")
    return rows


def _identity(row):
    return row.get("taskNumber") or f"category:{row['category']}"


def _days_body(row):
    body = {field: str(row["days"][index]) for index, field in enumerate(DAY_FIELDS)}
    if row.get("description"):
        body[DESCRIPTION_FIELD] = row["description"][:4000]
    return body


def _verify_description(session, sys_id, sent, *, debug=False):
    record = api.request(
        session,
        "GET",
        "time_card",
        sys_id=sys_id,
        params={"sysparm_fields": f"{DESCRIPTION_FIELD},notes"},
        debug=debug,
    )
    if isinstance(record, list):
        record = record[0] if record else {}
    if str(record.get(DESCRIPTION_FIELD, "")).strip():
        return None
    suffix = " (text landed in notes)" if str(record.get("notes", "")).strip() else ""
    return f"{len(sent)} description characters were sent but comments is empty{suffix}"


def _create_card(session, identity, body, *, debug=False):
    description = body.get(DESCRIPTION_FIELD)
    post_body = {key: value for key, value in body.items() if key != DESCRIPTION_FIELD}
    created = api.request(session, "POST", "time_card", body=post_body, debug=debug)
    sys_id = created.get("sys_id") if isinstance(created, dict) else None
    if not sys_id:
        return {"taskNumber": identity, "action": "failed", "detail": "POST lacked sys_id"}
    if description:
        api.request(
            session,
            "PATCH",
            "time_card",
            sys_id=sys_id,
            body={DESCRIPTION_FIELD: description},
            debug=debug,
        )
    result = {"taskNumber": identity, "action": "created", "sys_id": sys_id}
    detail = _verify_description(session, sys_id, description, debug=debug)
    if detail:
        result["detail"] = detail
    return result


def _project_base(session, week_start, task_number, *, debug=False):
    task = task_lookup(session, task_number, debug=debug)
    if not task:
        return None
    base = {"task": task["sys_id"], "week_starts_on": week_start, "category": "project_work"}
    try:
        rows = api.request(
            session,
            "GET",
            "resource_allocation",
            params={
                "sysparm_fields": "resource_plan",
                "sysparm_query": (
                    f"user.user_name={session.user}^resource_plan.task.number={task_number}"
                    "^ORDERBYDESCend_date"
                ),
                "sysparm_limit": "1",
            },
            debug=debug,
        )
        plan = rows[0].get("resource_plan") if rows else None
        value = plan.get("value") if isinstance(plan, dict) else plan
        if value:
            base["resource_plan"] = value
    except ScopeInsufficientError:
        pass
    return base


def write_week(session, week_start, rows, *, debug=False):
    parse_iso_date(week_start, name="week start")
    validate_write_rows(rows)
    existing = api.request(
        session,
        "GET",
        "time_card",
        params={
            "sysparm_fields": "sys_id,task.number,category,state",
            "sysparm_query": f"user.user_name={session.user}^week_starts_on={week_start}",
            "sysparm_limit": "200",
        },
        debug=debug,
    )
    by_task, by_category = defaultdict(list), defaultdict(list)
    for card in existing:
        key = card.get("task.number")
        (by_task if key else by_category)[key or card.get("category")].append(card)
    results = []

    def cards_for(row):
        return (by_task if row.get("taskNumber") else by_category).get(
            row.get("taskNumber") or row.get("category"), []
        )

    def delete_pending(identity, cards):
        for card in cards:
            if card.get("state") != "Pending":
                results.append(
                    {"taskNumber": identity, "action": "skipped", "detail": f"state={card.get('state')}"}
                )
                continue
            api.request(session, "DELETE", "time_card", sys_id=card["sys_id"], debug=debug)
            results.append({"taskNumber": identity, "action": "deleted"})

    split_groups = defaultdict(list)
    plain_rows = []
    for row in rows:
        (split_groups[_identity(row)] if row.get("split") else plain_rows).append(row)

    for row in plain_rows:
        identity = _identity(row)
        cards = cards_for(row)
        if row.get("remove"):
            if cards:
                delete_pending(identity, cards)
            else:
                results.append({"taskNumber": identity, "action": "skipped", "detail": "card not found"})
            continue
        card = next((item for item in cards if item.get("state") == "Pending"), cards[0] if cards else None)
        body = _days_body(row)
        if card:
            if card.get("state") != "Pending":
                results.append({"taskNumber": identity, "action": "skipped", "detail": f"state={card.get('state')}"})
                continue
            api.request(session, "PATCH", "time_card", sys_id=card["sys_id"], body=body, debug=debug)
            result = {"taskNumber": identity, "action": "updated", "sys_id": card["sys_id"]}
            detail = _verify_description(session, card["sys_id"], body.get(DESCRIPTION_FIELD), debug=debug)
            if detail:
                result["detail"] = detail
            results.append(result)
            continue
        base = (
            _project_base(session, week_start, row["taskNumber"], debug=debug)
            if row.get("taskNumber")
            else {"week_starts_on": week_start, "category": row["category"]}
        )
        if base is None:
            results.append({"taskNumber": identity, "action": "skipped", "detail": "task not found"})
            continue
        results.append(_create_card(session, identity, {**body, **base}, debug=debug))

    for identity, group in split_groups.items():
        sample = group[0]
        delete_pending(identity, cards_for(sample))
        base = (
            _project_base(session, week_start, sample["taskNumber"], debug=debug)
            if sample.get("taskNumber")
            else {"week_starts_on": week_start, "category": sample["category"]}
        )
        if base is None:
            results.extend(
                {"taskNumber": identity, "action": "skipped", "detail": "task not found"}
                for _ in group
            )
            continue
        for row in group:
            results.append(_create_card(session, identity, {**_days_body(row), **base}, debug=debug))
    return results

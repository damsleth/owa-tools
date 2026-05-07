"""Output formatters. JSON, pretty-print tables, CSV, TSV, NDJSON.

Public surface:
    render(value, *, format, columns=None) -> str
    pretty_table(rows, columns) -> str
    to_csv(rows, columns, *, sep=',') -> str
    to_ndjson(rows) -> str

Format options:
    "json"   - default; ensure_ascii=False, indent=None
    "pretty" - aligned text table for humans
    "csv"    - RFC 4180 minimal; UTF-8
    "tsv"    - tab-separated; safe when fields lack tabs
    "ndjson" - one JSON object per line
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Iterable, Sequence

from .errors import UsageError


def _columns_or_keys(rows: Sequence[dict], columns: Iterable[str] | None) -> list[str]:
    if columns is not None:
        return list(columns)
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in row.keys():
            if k not in seen:
                seen.add(k)
                keys.append(k)
    return keys


def _stringify(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float, str)):
        return str(v)
    return json.dumps(v, ensure_ascii=False)


def pretty_table(rows: Sequence[dict], columns: Iterable[str] | None = None) -> str:
    cols = _columns_or_keys(rows, columns)
    if not cols:
        return ""
    widths = {c: len(c) for c in cols}
    str_rows: list[dict[str, str]] = []
    for row in rows:
        sr = {c: _stringify(row.get(c)) for c in cols}
        str_rows.append(sr)
        for c in cols:
            widths[c] = max(widths[c], len(sr[c]))
    line = "  ".join(c.ljust(widths[c]) for c in cols)
    sep = "  ".join("-" * widths[c] for c in cols)
    out = [line, sep]
    for sr in str_rows:
        out.append("  ".join(sr[c].ljust(widths[c]) for c in cols))
    return "\n".join(out)


def to_csv(rows: Sequence[dict], columns: Iterable[str] | None = None, *, sep: str = ",") -> str:
    cols = _columns_or_keys(rows, columns)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=sep, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(cols)
    for row in rows:
        writer.writerow([_stringify(row.get(c)) for c in cols])
    return buf.getvalue()


def to_ndjson(rows: Iterable[Any]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def render(
    value: Any,
    *,
    format: str = "json",
    columns: Iterable[str] | None = None,
) -> str:
    fmt = format.lower()
    if fmt == "json":
        return json.dumps(value, ensure_ascii=False)
    if fmt == "ndjson":
        if not isinstance(value, (list, tuple)):
            raise UsageError("ndjson requires a list of objects")
        return to_ndjson(value)
    if fmt in ("pretty", "csv", "tsv"):
        if not isinstance(value, (list, tuple)) or any(not isinstance(r, dict) for r in value):
            raise UsageError(f"{fmt} requires a list of dict rows")
        if fmt == "pretty":
            return pretty_table(value, columns)
        if fmt == "csv":
            return to_csv(value, columns, sep=",")
        if fmt == "tsv":
            return to_csv(value, columns, sep="\t")
    raise UsageError(f"unknown format: {format}")

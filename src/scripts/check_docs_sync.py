#!/usr/bin/env python3
"""Check docs stay aligned with declared tool command schemas."""
from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from owa import cli as umbrella_cli  # noqa: E402
from owa_cal.cli import COMMAND_SCHEMA as CAL_SCHEMA  # noqa: E402
from owa_doctor.cli import COMMAND_SCHEMA as DOCTOR_SCHEMA  # noqa: E402
from owa_drive.cli import COMMAND_SCHEMA as DRIVE_SCHEMA  # noqa: E402
from owa_graph import resources as graph_resources  # noqa: E402
from owa_graph.cli import COMMAND_SCHEMA as GRAPH_SCHEMA  # noqa: E402
from owa_mail.cli import COMMAND_SCHEMA as MAIL_SCHEMA  # noqa: E402
from owa_people.cli import COMMAND_SCHEMA as PEOPLE_SCHEMA  # noqa: E402
from owa_sched.cli import COMMAND_SCHEMA as SCHED_SCHEMA  # noqa: E402

DOCS = {
    'owa-cal': ('docs/cal.md', CAL_SCHEMA),
    'owa-mail': ('docs/mail.md', MAIL_SCHEMA),
    'owa-graph': ('docs/graph.md', GRAPH_SCHEMA),
    'owa-doctor': ('docs/doctor.md', DOCTOR_SCHEMA),
    'owa-people': ('docs/people.md', PEOPLE_SCHEMA),
    'owa-sched': ('docs/sched.md', SCHED_SCHEMA),
    'owa-drive': ('docs/drive.md', DRIVE_SCHEMA),
}

SHELL_FENCES = {'', 'sh', 'bash', 'shell', 'console'}


def _schema_commands(rows):
    return {row['name'] for row in rows}


def _doc_mentions_command(text, tool, command):
    return re.search(rf'\b{re.escape(tool)}\s+{re.escape(command)}\b', text) is not None


def _shell_lines(text):
    in_fence = False
    shell = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('```'):
            if not in_fence:
                parts = stripped[3:].strip().split(None, 1)
                lang = parts[0].lower() if parts else ''
                shell = lang in SHELL_FENCES
                in_fence = True
            else:
                in_fence = False
                shell = False
            continue
        if in_fence and shell:
            promptless = stripped.removeprefix('$').strip()
            if promptless and not promptless.startswith('#'):
                yield promptless


def _strip_inline_comment(line):
    return re.sub(r'\s+#.*$', '', line).strip()


def _example_commands(line, tool):
    for segment in re.split(r'[|;&]', _strip_inline_comment(line)):
        try:
            parts = shlex.split(segment)
        except ValueError:
            continue
        while parts and re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', parts[0]):
            parts = parts[1:]
        if not parts:
            continue
        if parts[0] == 'uvx' and len(parts) > 1 and parts[1] == tool:
            parts = parts[1:]
        if parts[0] != tool:
            continue
        parts = parts[1:]
        while parts and parts[0].startswith('-'):
            if parts[0] in {'--profile', '--audience'} and len(parts) > 1:
                parts = parts[2:]
            else:
                parts = parts[1:]
        if parts:
            yield parts[0]


def check_command_docs():
    failures = []
    for tool, (doc_path, schema) in DOCS.items():
        path = REPO_ROOT / doc_path
        if not path.is_file():
            failures.append(f'{doc_path}: missing')
            continue
        text = path.read_text(encoding='utf-8')
        commands = _schema_commands(schema)
        allowed_examples = set(commands)
        if tool == 'owa-graph':
            allowed_examples.update(graph_resources.known_groups())
        for command in sorted(commands):
            if not _doc_mentions_command(text, tool, command):
                failures.append(f'{doc_path}: missing documented command `{tool} {command}`')
        for line in _shell_lines(text):
            for command in _example_commands(line, tool):
                if command in allowed_examples:
                    continue
                failures.append(f'{doc_path}: unknown example command `{tool} {command}` in `{line}`')
    return failures


def check_readme_tool_list():
    readme = (REPO_ROOT / 'README.md').read_text(encoding='utf-8')
    failures = []
    for tool in umbrella_cli.CONSUMERS:
        if f'`{tool}`' not in readme:
            failures.append(f'README.md: missing `{tool}` from tool list')
    if '`owa`' not in readme:
        failures.append('README.md: missing `owa` umbrella entry')
    return failures


def check_agents_index():
    root_agents = (REPO_ROOT / 'AGENTS.md').read_text(encoding='utf-8')
    failures = []
    for match in re.finditer(r'`([^`]*AGENTS\.md)`', root_agents):
        rel = match.group(1)
        if not (REPO_ROOT / rel).is_file():
            failures.append(f'AGENTS.md: indexed path does not exist: {rel}')
    return failures


def check_docs_sync():
    failures = []
    failures.extend(check_command_docs())
    failures.extend(check_readme_tool_list())
    failures.extend(check_agents_index())
    return failures


def main() -> int:
    failures = check_docs_sync()
    if not failures:
        print('docs sync check: OK')
        return 0
    print('docs sync check: FAIL', file=sys.stderr)
    for failure in failures:
        print(f'  {failure}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

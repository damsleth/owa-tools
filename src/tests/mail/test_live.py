"""Live mailbox tests.

These are opt-in and hit a real Outlook mailbox through the configured
owa-piggy profile. They cover the non-delete command surface against a
real account, using save-draft where possible to minimise side effects.

Required environment:

- OWA_MAIL_LIVE=1                enable the suite
- OWA_MAIL_LIVE_PROFILE=<alias>  owa-piggy profile alias
- OWA_MAIL_LIVE_TO=<addr>        recipient for real send tests

Optional environment:

- OWA_MAIL_LIVE_PYTHON=python3   interpreter used to run `-m owa_mail`
"""
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

RUN_LIVE = os.environ.get('OWA_MAIL_LIVE') == '1'
LIVE_PROFILE = os.environ.get('OWA_MAIL_LIVE_PROFILE', '')
LIVE_TO = os.environ.get('OWA_MAIL_LIVE_TO', '')
LIVE_PYTHON = (
    os.environ.get('OWA_MAIL_LIVE_PYTHON')
    or shutil.which('python3')
    or sys.executable
)

pytestmark = pytest.mark.skipif(
    not RUN_LIVE or not LIVE_PROFILE or not LIVE_TO,
    reason='set OWA_MAIL_LIVE=1, OWA_MAIL_LIVE_PROFILE, and OWA_MAIL_LIVE_TO to run live mailbox tests',
)


def _run(args, input_text=None, timeout=90):
    cmd = [LIVE_PYTHON, '-m', 'owa_mail', '--profile', LIVE_PROFILE, *args]
    proc = subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    assert proc.returncode == 0, (
        f'command failed: {cmd}\n'
        f'stdout:\n{proc.stdout}\n'
        f'stderr:\n{proc.stderr}'
    )
    return proc


def _json(args, input_text=None, timeout=90):
    proc = _run(args, input_text=input_text, timeout=timeout)
    return json.loads(proc.stdout)


def _subject(tag):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return f'owa-mail live {tag} {stamp} {uuid.uuid4().hex[:8]}'


def _today_utc():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def _send_at(minutes=15):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime(
        '%Y-%m-%dT%H:%M:%SZ'
    )


def _wait_for_message(folder, subject, timeout=60):
    deadline = time.time() + timeout
    last_items = []
    while time.time() < deadline:
        items = _json([
            'messages',
            '--folder', folder,
            '--since', _today_utc(),
            '--limit', '50',
        ])
        last_items = items
        for item in items:
            if item.get('subject') == subject:
                return item
        time.sleep(2)
    pytest.fail(
        f'timed out waiting for subject {subject!r} in {folder}; '
        f'last items: {last_items!r}'
    )


def test_live_refresh_and_folders():
    proc = _run(['refresh'])
    assert 'Refreshing token...' in proc.stderr
    assert 'Authenticated as' in proc.stderr

    folders = _json(['folders'])
    assert isinstance(folders, list)
    assert folders
    assert any(isinstance(f.get('id'), str) and f.get('id') for f in folders)
    assert any(isinstance(f.get('name'), str) and f.get('name') for f in folders)



def test_live_draft_messages_show_mark_and_move():
    subject = _subject('draft')
    draft = _json([
        'send',
        '--to', LIVE_TO,
        '--subject', subject,
        '--body', 'live draft body',
        '--save-draft',
    ])
    assert draft['id']
    assert draft['subject'] == subject
    original_folder_id = draft['folder_id']
    assert original_folder_id

    listed = _wait_for_message('Drafts', subject)
    assert listed['id'] == draft['id']

    shown = _json(['show', '--id', draft['id']])
    assert shown['id'] == draft['id']
    assert shown['subject'] == subject
    assert shown['body'] == 'live draft body'

    flagged = _json(['mark', '--id', draft['id'], '--flag'])
    assert flagged['id'] == draft['id']
    assert flagged['flag'] == 'Flagged'

    unflagged = _json(['mark', '--id', draft['id'], '--unflag'])
    assert unflagged['id'] == draft['id']
    assert unflagged['flag'] == 'NotFlagged'

    moved = _json(['move', '--id', draft['id'], '--to', 'Archive'])
    assert moved['subject'] == subject
    assert moved['folder_id'] != original_folder_id
    archived = _wait_for_message('Archive', subject)
    assert archived['id'] == moved['id']

    restored = _json(['move', '--id', moved['id'], '--to', original_folder_id])
    assert restored['subject'] == subject
    assert restored['folder_id'] == original_folder_id
    back_in_drafts = _wait_for_message('Drafts', subject)
    assert back_in_drafts['id'] == restored['id']



def test_live_send_reply_reply_all_forward_and_schedule():
    sent_subject = _subject('send')
    sent = _json([
        'send',
        '--to', LIVE_TO,
        '--subject', sent_subject,
        '--body', 'live immediate send',
    ])
    assert sent == {'sent': True}

    sent_msg = _wait_for_message('SentItems', sent_subject, timeout=90)
    assert sent_msg['subject'] == sent_subject

    reply = _json([
        'reply',
        '--id', sent_msg['id'],
        '--body', 'live reply draft body',
        '--save-draft',
    ])
    assert reply['id']
    assert reply['subject']

    reply_all = _json([
        'reply-all',
        '--id', sent_msg['id'],
        '--body', 'live reply-all draft body',
        '--save-draft',
    ])
    assert reply_all['id']
    assert reply_all['subject']

    forwarded = _json([
        'forward',
        '--id', sent_msg['id'],
        '--to', LIVE_TO,
        '--body', 'live forward draft body',
        '--save-draft',
    ])
    assert forwarded['id']
    assert LIVE_TO in forwarded['to']

    scheduled_subject = _subject('scheduled')
    send_at = _send_at()
    scheduled = _json([
        'send',
        '--to', LIVE_TO,
        '--subject', scheduled_subject,
        '--body', 'live scheduled send',
        '--send-at', send_at,
    ])
    assert scheduled['sent'] is True
    assert scheduled['id']
    assert scheduled['send_at'] == send_at

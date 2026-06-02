"""Human-readable Teams formatting for --pretty mode.

Stdout-only; callers decide whether to emit this or raw JSON.
"""
from owa_core.format import pad, time_part, truncate


def format_teams_pretty(teams):
    if not teams:
        return 'No teams found.'
    out = []
    for team in teams:
        archived = ' (archived)' if team.get('isArchived') else ''
        out.append(f"{pad(truncate(team.get('displayName') or '', 40), 40)}  {team.get('id') or ''}{archived}")
    return '\n'.join(out)


def format_channels_pretty(channels):
    if not channels:
        return 'No channels found.'
    out = []
    for channel in channels:
        mtype = channel.get('membershipType') or ''
        out.append(
            f"{pad(truncate(channel.get('displayName') or '', 36), 36)}  "
            f"{pad(mtype, 9)}  {channel.get('id') or ''}"
        )
    return '\n'.join(out)


def format_chats_pretty(chats):
    if not chats:
        return 'No chats found.'
    out = []
    for chat in chats:
        label = chat.get('topic') or '(no topic)'
        out.append(
            f"{pad(chat.get('chatType') or '', 9)}  "
            f"{pad(truncate(label, 40), 40)}  {chat.get('id') or ''}"
        )
    return '\n'.join(out)


def format_messages_pretty(messages):
    """Render channel/chat messages chronologically.

    Channel rows carry threading (`isReply`/`subject`); replies are indented
    under their root's subject. Chat rows are flat.
    """
    if not messages:
        return 'No messages.'
    out = []
    last_subject = None
    for msg in messages:
        who = (msg.get('from') or {}).get('name') or (msg.get('from') or {}).get('id') or '?'
        when = time_part(msg.get('timestamp') or '') or (msg.get('timestamp') or '')
        subject = msg.get('subject')
        if subject is not None and subject != last_subject and subject:
            out.append(f"# {subject}")
            last_subject = subject
        indent = '    ' if msg.get('isReply') else '  '
        body = truncate((msg.get('content') or '').replace('\n', ' '), 100)
        out.append(f"{indent}{pad(who, 22)} {pad(when, 5)}  {body}")
    return '\n'.join(out)

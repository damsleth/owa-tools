#!/usr/bin/env python3
"""
Token refresh via CDP connection to the running browser.

Connects via remote debugging, navigates Outlook to calendar view,
and captures the Bearer token from CDP network events.

Requires: browser started with --remote-debugging-port=9222
  Run: cal-cli setup  (one-time, restarts browser with debugging)
"""

import asyncio
import json
import sys
import time
import base64
import urllib.request

try:
    import websockets
except ImportError:
    print('ERROR: pip install websockets', file=sys.stderr)
    sys.exit(1)

CDP_PORT = 9222
TARGET_AUDIENCE = 'outlook.office.com'
OUTLOOK_PATTERNS = ['outlook.cloud.microsoft/mail', 'outlook.cloud.microsoft/calendar']
TIMEOUT = 30

msg_id = 0

def next_id():
    global msg_id
    msg_id += 1
    return msg_id


def check_token(auth):
    """Check if an Authorization header contains the right Outlook token."""
    if not auth or not auth.startswith('Bearer eyJ'):
        return None
    jwt = auth[7:].strip()
    try:
        payload_b64 = jwt.split('.')[1]
        payload_b64 += '=' * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.b64decode(payload_b64))
        if (TARGET_AUDIENCE in payload.get('aud', '')
                and 'Calendars.ReadWrite' in payload.get('scp', '')):
            return jwt
    except:
        pass
    return None


async def refresh_token():
    # Check CDP
    try:
        resp = urllib.request.urlopen(f'http://127.0.0.1:{CDP_PORT}/json/version')
        info = json.loads(resp.read())
        print(f'Connected to {info.get("Browser", "browser")}', file=sys.stderr)
    except:
        print('ERROR: No browser CDP on port 9222.', file=sys.stderr)
        print('Run: cal-cli setup', file=sys.stderr)
        return 1

    # Find Outlook tab
    tabs = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{CDP_PORT}/json/list').read())
    outlook_tab = None
    for pattern in OUTLOOK_PATTERNS:
        for tab in tabs:
            if pattern in tab.get('url', '') and tab.get('type') == 'page':
                outlook_tab = tab
                break
        if outlook_tab:
            break

    if not outlook_tab:
        print('ERROR: No Outlook tab found. Open outlook.cloud.microsoft', file=sys.stderr)
        return 1

    ws_url = outlook_tab.get('webSocketDebuggerUrl')
    print(f'Found: {outlook_tab.get("title", "")[:60]}', file=sys.stderr)

    token = None
    async with websockets.connect(ws_url, max_size=10_000_000) as ws:
        # Enable network event capture
        mid = next_id()
        await ws.send(json.dumps({'id': mid, 'method': 'Network.enable'}))

        # Navigate to calendar view (triggers calendar API calls with the right token)
        mid2 = next_id()
        await ws.send(json.dumps({
            'id': mid2, 'method': 'Page.navigate',
            'params': {'url': 'https://outlook.cloud.microsoft/calendar/'}
        }))

        print('Navigating to calendar, listening for token...', file=sys.stderr)

        # Listen for Network.requestWillBeSent events
        deadline = time.time() + TIMEOUT
        while time.time() < deadline and not token:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2)
                data = json.loads(raw)

                if data.get('method') == 'Network.requestWillBeSent':
                    headers = data.get('params', {}).get('request', {}).get('headers', {})
                    auth = headers.get('Authorization') or headers.get('authorization') or ''
                    token = check_token(auth)

            except asyncio.TimeoutError:
                continue
            except Exception:
                continue

    if token:
        try:
            payload_b64 = token.split('.')[1]
            payload_b64 += '=' * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.b64decode(payload_b64))
            remaining = int((payload.get('exp', 0) - time.time()) / 60)
            print(f'Token captured! {remaining}min remaining', file=sys.stderr)
        except:
            pass
        print(token)
        return 0
    else:
        print('ERROR: No Outlook calendar token captured', file=sys.stderr)
        return 1


if __name__ == '__main__':
    rc = asyncio.run(refresh_token())
    sys.exit(rc)

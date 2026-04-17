#!/usr/bin/env python3
"""Export and decrypt Chromium browser cookies for Microsoft auth domains."""

import json
import sqlite3
import subprocess
import sys
import os
import shutil
import tempfile
from hashlib import pbkdf2_hmac
from pathlib import Path

# Microsoft domains needed for Outlook auth
DOMAINS = [
    '%microsoft%',
    '%office%',
    '%office365%',
    '%live.com%',
    '%microsoftonline%',
]

# Supported browsers (macOS paths)
BROWSERS = {
    'edge': {
        'name': 'Microsoft Edge',
        'base': Path.home() / 'Library/Application Support/Microsoft Edge',
        'keychain_service': 'Microsoft Edge Safe Storage',
        'keychain_account': 'Microsoft Edge',
    },
    'chrome': {
        'name': 'Google Chrome',
        'base': Path.home() / 'Library/Application Support/Google/Chrome',
        'keychain_service': 'Chrome Safe Storage',
        'keychain_account': 'Chrome',
    },
    'brave': {
        'name': 'Brave Browser',
        'base': Path.home() / 'Library/Application Support/BraveSoftware/Brave-Browser',
        'keychain_service': 'Brave Safe Storage',
        'keychain_account': 'Brave',
    },
    'arc': {
        'name': 'Arc',
        'base': Path.home() / 'Library/Application Support/Arc/User Data',
        'keychain_service': 'Arc Safe Storage',
        'keychain_account': 'Arc',
    },
    'vivaldi': {
        'name': 'Vivaldi',
        'base': Path.home() / 'Library/Application Support/Vivaldi',
        'keychain_service': 'Vivaldi Safe Storage',
        'keychain_account': 'Vivaldi',
    },
}

OUTPUT_DIR = Path.home() / '.cal-cli'
OUTPUT_FILE = OUTPUT_DIR / 'cookies.json'


def get_encryption_key(service, account):
    """Get cookie encryption key from macOS Keychain."""
    result = subprocess.run(
        ['security', 'find-generic-password', '-w', '-s', service, '-a', account],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def derive_key(password):
    """Derive AES key from browser password using PBKDF2."""
    return pbkdf2_hmac('sha1', password.encode('utf-8'), b'saltysalt', 1003, dklen=16)


def decrypt_cookie(encrypted_value, key):
    """Decrypt a Chromium cookie value (v10 format on macOS)."""
    if not encrypted_value:
        return ''

    if encrypted_value[:3] == b'v10':
        encrypted_value = encrypted_value[3:]
        iv = b' ' * 16
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
            decryptor = cipher.decryptor()
            decrypted = decryptor.update(encrypted_value) + decryptor.finalize()
            pad_len = decrypted[-1]
            if pad_len <= 16:
                decrypted = decrypted[:-pad_len]
            return decrypted.decode('utf-8', errors='replace')
        except Exception as e:
            return ''
    else:
        return encrypted_value.decode('utf-8', errors='replace')


def find_best_profile(base_path):
    """Find the browser profile with the most Outlook cookies."""
    profiles = []
    for name in ['Default'] + [f'Profile {i}' for i in range(1, 20)]:
        db = base_path / name / 'Cookies'
        if not db.exists():
            continue

        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tmp.close()
        shutil.copy2(str(db), tmp.name)
        try:
            conn = sqlite3.connect(tmp.name)
            count = conn.execute(
                "SELECT COUNT(*) FROM cookies WHERE host_key LIKE '%outlook%'"
            ).fetchone()[0]
            conn.close()
            profiles.append((name, count))
        except:
            pass
        finally:
            os.unlink(tmp.name)

    if not profiles:
        return None

    profiles.sort(key=lambda x: -x[1])
    best = profiles[0]
    if best[1] == 0:
        return profiles[0][0]  # Default if none have Outlook cookies
    return best[0]


def export_cookies(browser_key=None, profile=None):
    """Export Microsoft cookies from the detected browser."""
    # Auto-detect browser with most Microsoft cookies
    if browser_key:
        browsers_to_try = [browser_key]
    else:
        # Score each browser by Microsoft cookie count
        scored = []
        for bk in ['vivaldi', 'edge', 'chrome', 'brave', 'arc']:
            b = BROWSERS[bk]
            if not b['base'].exists():
                continue
            prof = find_best_profile(b['base'])
            if not prof:
                continue
            db = b['base'] / prof / 'Cookies'
            if not db.exists():
                continue
            tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
            tmp.close()
            shutil.copy2(str(db), tmp.name)
            try:
                conn = sqlite3.connect(tmp.name)
                domain_clauses = ' OR '.join([f"host_key LIKE '{d}'" for d in DOMAINS])
                count = conn.execute(f"SELECT COUNT(*) FROM cookies WHERE {domain_clauses}").fetchone()[0]
                conn.close()
                scored.append((bk, count, prof))
            except:
                pass
            finally:
                os.unlink(tmp.name)

        scored.sort(key=lambda x: -x[1])
        if scored and scored[0][1] > 0:
            browsers_to_try = [scored[0][0]]
            profile = profile or scored[0][2]
            print(f'Auto-detected: {BROWSERS[scored[0][0]]["name"]} ({scored[0][2]}) with {scored[0][1]} Microsoft cookies', file=sys.stderr)
        else:
            browsers_to_try = ['edge', 'chrome', 'brave', 'arc']

    for bk in browsers_to_try:
        browser = BROWSERS[bk]
        if not browser['base'].exists():
            continue

        password = get_encryption_key(browser['keychain_service'], browser['keychain_account'])
        if not password:
            continue

        prof = profile or find_best_profile(browser['base'])
        if not prof:
            continue

        db_path = browser['base'] / prof / 'Cookies'
        if not db_path.exists():
            continue

        print(f'Using {browser["name"]} ({prof})', file=sys.stderr)
        key = derive_key(password)

        # Copy DB (browser locks it)
        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tmp.close()
        shutil.copy2(str(db_path), tmp.name)

        try:
            conn = sqlite3.connect(tmp.name)
            domain_clauses = ' OR '.join([f"host_key LIKE '{d}'" for d in DOMAINS])
            rows = conn.execute(f"""
                SELECT host_key, name, encrypted_value, path, is_secure, is_httponly, samesite
                FROM cookies WHERE {domain_clauses}
                ORDER BY host_key, name
            """).fetchall()
            conn.close()

            cookies = []
            for host, name, enc_val, path, secure, httponly, samesite in rows:
                value = decrypt_cookie(enc_val, key)
                if not value:
                    continue
                cookies.append({
                    'name': name,
                    'value': value,
                    'domain': host,
                    'path': path or '/',
                    'secure': bool(secure),
                    'httpOnly': bool(httponly),
                    'sameSite': ['None', 'Lax', 'Strict'][samesite] if samesite in (0, 1, 2) else 'None',
                })

            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            try:
                OUTPUT_DIR.chmod(0o700)
            except OSError:
                pass
            # Write with 0600 perms so decrypted cookies aren't world-readable
            fd = os.open(str(OUTPUT_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as f:
                json.dump(cookies, f, indent=2)
            print(f'Exported {len(cookies)} cookies from {len(set(c["domain"] for c in cookies))} domains', file=sys.stderr)
            print(f'Saved to {OUTPUT_FILE}', file=sys.stderr)
            return True

        finally:
            os.unlink(tmp.name)

    print('ERROR: No supported browser found with Microsoft cookies', file=sys.stderr)
    return False


if __name__ == '__main__':
    browser = sys.argv[1] if len(sys.argv) > 1 else None
    profile = sys.argv[2] if len(sys.argv) > 2 else None
    success = export_cookies(browser, profile)
    sys.exit(0 if success else 1)

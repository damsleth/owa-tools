# AGENTS.md

`owa_mail` handles Outlook mail folders, messages, and scheduled mail.

- Auth audience is `outlook`.
- Do not store message bodies, attachments, tokens, or mailbox data in config.
- JSON stdout is default; pretty formatting belongs in `format.py`.
- Mutating commands such as send, delete, move, and mark need explicit tests for
  confirmation and retry behavior before release.
- Docs live in `docs/mail.md`.

Nearest tests: `src/tests/mail/`.

Verify:

```bash
.venv/bin/ruff check src/owa_mail src/tests/mail
.venv/bin/python -m pytest -q src/tests/mail
```

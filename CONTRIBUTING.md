# Contributing to Scranton

Thanks for helping. Scranton is a small, single-user app; a few rules keep it that way.

## Ground rules

- **Subscriptions only.** Agents run the official CLIs signed in with the user's own plan. Don't add code that calls a paid model API or reads an API key.
- **Local only.** The server listens on `127.0.0.1`. No accounts, no hosted relay, no telemetry.
- **Small and plain.** Vanilla JS and FastAPI, no build step. Icons are Remix Icon only (`static/scranton-icons.js`). Colours and spacing come from `static/design-system.css` (see `docs/design-system.md`).
- **Keep upstream mergeable.** Prefer new `scranton_*.py` / `static/scranton-*.js` files over editing agentchattr's files; mark unavoidable edits with a `Scranton:` comment.

## Before you open a pull request

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest httpx
.venv/bin/python -m pytest -q
```

- Add a test for any bug fix or new endpoint (`tests/test_scranton_*.py`).
- For a visible change, put a before/after screenshot in the PR.
- Write UI text short and plain: sentence case, no jargon, say what happens.

## Reporting a bug

Open an issue with the bug template. Include what you did, what you expected, and the last lines of `data/logs/server.log` (check it doesn't contain anything private first).

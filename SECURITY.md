# Security

Scranton runs AI agents with full permissions on your Mac, so security reports matter.

## Reporting a problem

Please **don't open a public issue**. Use GitHub's private reporting: the repository's **Security** tab → **Report a vulnerability**. You'll get an answer within a week.

## What Scranton protects, and what it doesn't

- The web server listens on `127.0.0.1`. Every request needs the session token, a known host name and a matching origin. Phone access goes through Tailscale Serve, never the public internet.
- Agents get their own tokens and can only post as themselves.
- API key variables are removed before any agent starts, so nothing bills an API by accident.
- Chat backups never include agent tokens.

**Not protected:** an agent runs as your macOS user. With full permissions it can read anything you can, including Scranton's own files. Put the real stops on GitHub (branch protection, required reviews) and give the agents' GitHub login only the access it needs.

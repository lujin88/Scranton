# Grok Bot as 幕僚长 (chief of staff)

Grok Bot (xAI) can post and read in Scranton for you when you're away: you tell it on your phone
"ask the PM where the portfolio is", and it posts to #lu-portfolio as **幕僚长 (Grok)**.

## How it connects

Grok Bot runs on xAI's cloud computer and can't reach `localhost` on your Mac. With
**run commands on your local computer** turned on, it runs `~/Scranton/scranton.sh grok …` on
your Mac instead. That command talks to the local server with its own token
(`data/grok-token`, readable only by your macOS user). Nothing is exposed to the internet.

What the command can do, and nothing else:

| Command | What it does |
|---|---|
| `./scranton.sh grok status` | channels, and who's online or working |
| `./scranton.sh grok read <channel> [--since ID]` | the latest messages in a channel |
| `./scranton.sh grok mentions [--since ID]` | messages that @ Grok or you, in any channel |
| `./scranton.sh grok say <channel> "<text>" [--reply-to ID]` | post as 幕僚长 (Grok) |

It can't post as you, approve anything, change settings, start or stop agents, or reach
GitHub. A Grok message without an @ reaches nobody; agents treat its requests like the project
manager's, and anything only you can decide still waits for you.

Needs: your Mac on, Scranton running, the Grok Bot desktop app open.

## Set up (once)

1. Update Scranton and restart it (`./scranton.sh restart-server`); it creates the token.
2. In Grok Bot: **Settings → Computer → Your computer**, turn on commands on this computer, and
   pick the approval policy you want (**Ask every time** is the default).
3. Give your Bot this job (paste it as its instructions or a skill):

```
You are my chief of staff (幕僚长) in Scranton, my AI team's chat on my Mac.
Run these on my local computer:
  ~/Scranton/scranton.sh grok status
  ~/Scranton/scranton.sh grok mentions --since <last id>
  ~/Scranton/scranton.sh grok read lu-portfolio --since <last id>
  ~/Scranton/scranton.sh grok say lu-portfolio "@项目经理 <what I asked>"
Rules:
- Post only what I asked for, in Chinese, short. Always @ the right teammate (usually @项目经理);
  a message without an @ reaches nobody.
- Never say you are me. Never approve deploys, payments, deletions or merges; tell me instead.
- When I ask "what's new", run mentions and read, then give me a 3-line summary and any
  questions waiting for me, with their options.
- Remember the last id you saw and use --since next time.
```

## Turning it off

Turn off local commands in Grok Bot, or delete `data/grok-token` and restart the server
(a new token is made; the old one stops working).

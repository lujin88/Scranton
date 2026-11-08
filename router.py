"""Message routing based on @mentions with per-channel loop guard."""

import re


class Router:
    def __init__(self, agent_names: list[str], default_mention: str = "both",
                 max_hops: int = 4, online_checker=None):
        self.agent_names = set(n.lower() for n in agent_names)
        self.default_mention = default_mention
        self.max_hops = max_hops
        self.max_pingpong = 8   # the same two agents, back and forth, this many times in a row
        self._online_checker = online_checker  # callable() -> set of online agent names
        # Per-channel state: { channel: { hop_count, paused, guard_emitted } }
        self._channels: dict[str, dict] = {}
        self._build_pattern()

    def _get_ch(self, channel: str) -> dict:
        if channel not in self._channels:
            self._channels[channel] = {
                "hop_count": 0,
                "paused": False,
                "guard_emitted": False,
                # Scranton: a real loop is two agents bouncing between each other.
                "pair": None,       # frozenset of the last sender and the one they @'d
                "pair_run": 0,      # how many hand-offs in a row stayed within that pair
                "pause_hops": 0,    # the number the notice quotes
            }
        return self._channels[channel]

    def _build_pattern(self):
        # Sort longest-first so "gemini-2" is tried before "gemini"
        names = [re.escape(n) for n in sorted(self.agent_names, key=len, reverse=True)]
        alternatives = "|".join(names + ["both", "all"])
        self._mention_re = re.compile(
            rf"@({alternatives})(?![\w-])", re.IGNORECASE
        )

    def parse_mentions(self, text: str) -> list[str]:
        mentions = set()
        for match in self._mention_re.finditer(text):
            name = match.group(1).lower()
            if name in ("both", "all"):
                # Only tag online agents when using @all
                if self._online_checker:
                    online = self._online_checker()
                    mentions.update(n for n in self.agent_names if n in online)
                else:
                    mentions.update(self.agent_names)
            else:
                mentions.add(name)
        return list(mentions)

    def _is_agent(self, sender: str) -> bool:
        return sender.lower() in self.agent_names

    def get_targets(self, sender: str, text: str, channel: str = "general") -> list[str]:
        """Determine which agents should receive this message."""
        ch = self._get_ch(channel)
        mentions = self.parse_mentions(text)

        if not self._is_agent(sender) and sender == "grok":
            # Scranton: Grok Bot (幕僚长) only reaches whoever it @s; never "everyone".
            return mentions
        if not self._is_agent(sender):
            # Human message resets hop counter and unpauses
            ch["hop_count"] = 0
            ch["paused"] = False
            ch["guard_emitted"] = False
            ch["pair"], ch["pair_run"] = None, 0
            if not mentions:
                # Scranton: in a direct-message channel (dm-<agent>) a plain
                # message goes to that teammate, no @ needed.
                if channel.startswith("dm-"):
                    dm_target = channel[3:]
                    if dm_target in self.agent_names:
                        return [dm_target]
                if self.default_mention in ("both", "all"):
                    return list(self.agent_names)
                elif self.default_mention == "none":
                    return []
                return [self.default_mention]
            return mentions
        else:
            # Agent message: blocked while loop guard is active
            if ch["paused"]:
                return []
            # Only route if explicit @mention
            if not mentions:
                return []
            ch["hop_count"] += 1
            # Two agents answering each other over and over is a loop; a team handing work
            # pm -> dev -> qa -> visualqa -> pm is not, so that only stops at the overall budget.
            others = [m for m in mentions if m != sender.lower()]
            pair = frozenset([sender.lower(), others[0]]) if len(others) == 1 else None
            if pair and pair == ch["pair"]:
                ch["pair_run"] += 1
            else:
                ch["pair"], ch["pair_run"] = pair, 1 if pair else 0
            if ch["pair_run"] > self.max_pingpong or ch["hop_count"] > self.max_hops:
                ch["pause_hops"] = (ch["pair_run"] if ch["pair_run"] > self.max_pingpong else ch["hop_count"]) - 1
                ch["paused"] = True
                return []
            # Don't route back to self
            return [m for m in mentions if m != sender]

    def continue_routing(self, channel: str = "general"):
        """Resume after loop guard pause."""
        ch = self._get_ch(channel)
        ch["hop_count"] = 0
        ch["paused"] = False
        ch["guard_emitted"] = False
        ch["pair"], ch["pair_run"] = None, 0

    def pause_hops(self, channel: str = "general") -> int:
        return self._get_ch(channel).get("pause_hops") or self.max_hops

    def is_paused(self, channel: str = "general") -> bool:
        return self._get_ch(channel)["paused"]

    def is_guard_emitted(self, channel: str = "general") -> bool:
        return self._get_ch(channel)["guard_emitted"]

    def set_guard_emitted(self, channel: str = "general"):
        self._get_ch(channel)["guard_emitted"] = True

    def update_agents(self, names: list[str]):
        """Replace the agent name set and rebuild the mention regex."""
        self.agent_names = set(n.lower() for n in names)
        self._build_pattern()

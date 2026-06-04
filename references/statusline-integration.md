# Statusline integration (optional)

While a transcription runs, `scripts/statusline.sh` prints one short line like:

```
🎙 tx 47%* · ETA 01:18
```

…and prints **nothing** when no transcription is active (most statuslines will collapse the slot). It does this by reading `~/.cache/scriba/active` — a tiny text pointer that `transcribe.sh` registers on start and removes on exit.

Wire it into whatever statusline you already use. Recipes below cover the common setups; everything else follows the same pattern: invoke the script, include its stdout in your line.

The absolute path you'll need is:

```
$HOME/.claude/skills/scriba/scripts/statusline.sh
```

…assuming you installed the skill at the standard user-global location. Adjust if you're using a project-scoped install or a different layout.

---

## claude-hud (recommended if you already have it)

`claude-hud` has a first-class `--extra-cmd` flag that runs your command each tick (3 s default, 3 s timeout) and inlines its output. Edit `~/.claude/settings.json`, append `--extra-cmd <script>` to the end of the existing claude-hud invocation:

```json
"statusLine": {
  "type": "command",
  "command": "bash -c 'plugin_dir=$(ls -d \"${CLAUDE_CONFIG_DIR:-$HOME/.claude}\"/plugins/cache/claude-hud/claude-hud/*/ 2>/dev/null | awk -F/ '\"'\"'{ print $(NF-1) \"\\t\" $(0) }'\"'\"' | sort -t. -k1,1n -k2,2n -k3,3n -k4,4n | tail -1 | cut -f2-); exec \"$HOME/.bun/bin/bun\" --env-file /dev/null \"${plugin_dir}src/index.ts\" --extra-cmd \"$HOME/.claude/skills/scriba/scripts/statusline.sh\"'"
}
```

(That's the default claude-hud command with the trailing `--extra-cmd` appended.) Restart Claude Code; the slot appears on the right edge of the HUD while a transcription runs.

---

## Vanilla Claude Code statusLine (no plugin)

If you don't run a statusline plugin, you can let this script *be* your whole statusline while a transcription is active — and an empty bar otherwise. Set:

```json
"statusLine": {
  "type": "command",
  "command": "$HOME/.claude/skills/scriba/scripts/statusline.sh"
}
```

This is fine if you don't want anything else in the bar. If you want it *plus* some other minimal info (git branch, cwd, etc.), wrap both in a small composer script:

```bash
#!/usr/bin/env bash
# ~/.claude/scripts/my-statusline.sh
branch=$(git -C "$PWD" branch --show-current 2>/dev/null || echo "")
mt=$("$HOME/.claude/skills/scriba/scripts/statusline.sh")
[[ -n "$mt" ]] && mt=" │ $mt"
printf '%s %s%s' "$(basename "$PWD")" "$branch" "$mt"
```

Then point `statusLine.command` at that composer.

---

## Other statuslines / multiplexers (tmux, Starship, p10k…)

The script is just a normal command that returns text on stdout; any statusline that can shell out can include it.

- **tmux** — `set -g status-right "#(\"$HOME/.claude/skills/scriba/scripts/statusline.sh\")"`
- **Starship** (`~/.config/starship.toml`) — add a `[custom.meeting_transcribe]` block with `command = "$HOME/.claude/skills/scriba/scripts/statusline.sh"` and `when = "test -f $HOME/.cache/scriba/active"`
- **Powerlevel10k** — define a `prompt_meeting_transcribe()` segment that invokes the script and emits its output when non-empty
- **fish prompt / oh-my-zsh** — call the script in `fish_prompt` / a precmd hook

In all cases: silent when no active run, one short line otherwise.

---

## Output format (parseable)

If you'd rather render your own line, the underlying state lives in `<stem>.transcript.progress.json` next to the input. Schema: see `references/eta-factors.md`. The active pointer is `~/.cache/scriba/active`. The script in this directory is just one opinionated rendering — feel free to write your own and ignore it.

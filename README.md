# Envisioning fluency

A skill for coding agents. It reads your own prompts to Claude Code, Codex, Gemini CLI or Cursor (or any exported chat history) and writes you a one-page HTML report of what you can picture, ask for and get built: the kinds of UI you make, the features and interaction techniques you reach for, how you prompt, your design language, the products you borrow from, your UI vocabulary, and the edges of your range. Every finding is backed by a line you wrote.

Your prompts stay on your machine. Nothing is sent anywhere unless you press Send on the finished report, and a report you send can be read only by Bryan Min: the link it goes through can add to his page but can't open it.

Needs Python 3.8 or newer. No packages to install.

## Install

Pick one.

**Claude Code plugin.** Inside Claude Code:

```
/plugin marketplace add bdhmin/envisioning-fluency
/plugin install envisioning-fluency@envisioning-fluency
```

Run `/plugin marketplace update envisioning-fluency` later to get new versions.

**Any agent, with Node.** Works for Claude Code, Codex, Cursor, Gemini CLI and others; it asks which ones.

```sh
npx skills add bdhmin/envisioning-fluency -g
```

`-g` installs it for every project; leave it off to install into the current one.

**One line, no Node.** Puts the skill in `~/.claude/skills`.

```sh
curl -fsSL https://raw.githubusercontent.com/bdhmin/envisioning-fluency/main/install.sh | sh
```

For another agent's skills folder, set `SKILLS_DIR`, for example `| SKILLS_DIR=~/.codex/skills sh`.

**By hand.** Download this repo, copy `skills/envisioning-fluency` anywhere, open your agent in that folder, and say: "Read SKILL.md in this folder and follow it to write my envisioning fluency report."

## Use

Open your agent and ask for your envisioning fluency. It asks what name to put on the report, reads your history, and opens the report in your browser.

More detail is in [skills/envisioning-fluency/README.md](skills/envisioning-fluency/README.md).

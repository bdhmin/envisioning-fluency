# Envisioning fluency

A skill for coding agents. It reads your own prompts to Claude Code, Codex, Gemini CLI or Cursor (or any exported chat history) and writes you a one-page HTML report of what you can picture, ask for and get built: the kinds of UI you make, the features and interaction techniques you reach for, how you prompt, your design language, the products you borrow from, your UI vocabulary, and the edges of your range. Every finding is backed by a line you wrote.

It reads what you typed to your agents and the projects you built with them. Your prompts and files stay on your machine. The report starts with a list of everything it read, with a switch on each project, so you choose what is sent; nothing is sent unless you press Send, and a report you send can be read only by Bryan Min: the link it goes through can add to his page but can't open it.

Needs Python 3.8 or newer. No packages to install.

## Install

Pick one.

**Claude Code plugin.** Inside Claude Code:

```
/plugin marketplace add bdhmin/envisioning-fluency
/plugin install envisioning-fluency@envisioning-fluency
```

Run `/plugin marketplace update envisioning-fluency` later to get new versions.

**Cursor plugin.** In Cursor, open Customize, choose From GitHub Repository, paste `https://github.com/bdhmin/envisioning-fluency`, and install Envisioning fluency from the plugins it lists. Or, from a terminal, put it where Cursor reads skills:

```sh
npx skills@1.5.15 add bdhmin/envisioning-fluency -g -a cursor -y
```

**Any agent, with Node.** Works for Claude Code, Codex, Cursor, Gemini CLI and others; it asks which ones.

```sh
npx skills@1.5.15 add bdhmin/envisioning-fluency -g
```

`-g` installs it for every project; leave it off to install into the current one. Needs Node 18 or newer. The `@1.5.15` keeps the installer on its last release that runs on Node 18 and 20; newer ones need Node 22 and stop with "does not provide an export named 'styleText'".

**One line, no Node.** Puts the skill in `~/.claude/skills`.

```sh
curl -fsSL https://raw.githubusercontent.com/bdhmin/envisioning-fluency/main/install.sh | sh
```

For another agent's skills folder, set `SKILLS_DIR`, for example `| SKILLS_DIR=~/.agents/skills sh`.

**By hand.** Download this repo, copy `skills/envisioning-fluency` anywhere, open your agent in that folder, and say: "Read SKILL.md in this folder and follow it to write my envisioning fluency report."

## Use

Open your agent and ask for your envisioning fluency. It asks nothing: it reads your history and your projects, writes the report and opens it in your browser. To leave something out (a project, a stretch of time), tell your agent and it runs again without it.

More detail is in [skills/envisioning-fluency/README.md](skills/envisioning-fluency/README.md).

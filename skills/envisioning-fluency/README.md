# Envisioning fluency

A skill for coding agents. It reads your own prompts to Claude Code, Codex, Gemini CLI or Cursor (or any exported chat history), and the projects you built with them, and writes you a one-page HTML report of what you can picture, ask for and get built: the kinds of UI you make, the features and interaction techniques you reach for, how you prompt, your design language, the products you borrow from, your UI vocabulary, and the edges of your range. Every finding is backed by a line you wrote.

Your prompts and files never leave your machine. The report opens with a list of every project it read, each with a switch, and every card has a Don't send. If the person who shared this with you collects reports, a send bar is pinned to the bottom of the window: press it to see exactly what would go, and nothing is sent unless you press Send. To take something out of the report itself, ask your agent to leave it out.

Needs Python 3.8 or newer. No packages to install.

## Install

**Claude Code.** Put this folder in your skills folder, then ask Claude for your envisioning fluency.

```sh
mkdir -p ~/.claude/skills
cp -r envisioning-fluency ~/.claude/skills/
```

**Codex CLI, Gemini CLI, Cursor, Windsurf, or any other agent.** Put the folder anywhere, open your agent in it, and say:

> Read SKILL.md in this folder and follow it to write my envisioning fluency report.

**By hand.** `python3 scripts/collect.py --out ef-work`, then give `ef-work/prompts.jsonl` and SKILL.md to any chat model and ask it for `analysis.json`, then `python3 scripts/render.py --work ef-work`.

## What is in the folder

| | |
|---|---|
| `SKILL.md` | The steps the agent follows. |
| `scripts/collect.py` | Finds your prompts, looks through the projects they were about, and counts what is in them. |
| `scripts/render.py` | Turns the agent's analysis into the HTML report. |
| `scripts/send.py` | Opens your report with its send bar, and sends it to its owner's page only when you press Send. Only the owner can read what is sent. |
| `assets/report.html` | The report's template. |
| `collector.json` | Where a sent report goes: an add-only link to its owner's page. Delete it to keep everything local. |

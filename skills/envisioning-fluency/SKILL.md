---
name: envisioning-fluency
description: Read a person's own prompts to coding agents (Claude Code, Codex, Gemini CLI, Cursor, or an exported history) and write them an "envisioning fluency" report as one HTML file — the kinds of UI they build, features they generate, interaction techniques, prompting strategies, design language, the products and metaphors they borrow, their UI vocabulary, and the edges of their range, each backed by their own words. Use when someone asks for their envisioning fluency, their design arsenal or design space, what kinds of interfaces they can picture and prompt for, or a review of how they prompt for UI.
---

# Envisioning fluency

You are writing someone a portrait of what they can picture, ask for and get built. The evidence is their own prompts; the result is one self-contained HTML file they open in a browser. Everything runs on their machine. Nothing is sent anywhere unless they say so at the end.

Works in any agent that can run Python 3.8+ and read files: Claude Code, Codex, Gemini CLI, Cursor, Windsurf, or a person following along by hand. Paths below are relative to this skill's folder.

## 1. Collect

Ask which name to put on the report (a first name is enough). Then run:

```sh
python3 scripts/collect.py --out ef-work
```

It reads the histories these agents keep locally — `~/.claude/projects` (Claude Code), `~/.codex` (Codex CLI), `~/.gemini/tmp` (Gemini CLI), Cursor's `state.vscdb` — keeps only the words the person typed, drops repeats, automated sessions and pasted logs, and writes `ef-work/prompts.jsonl` and `ef-work/stats.json`.

- Only some agents: `--only claude,codex`. A date floor: `--since 2026-09-01`.
- Another tool, or a chat app: export the history, or paste prompts into a text file with a blank line between them, and add `--file path` (repeatable; `.json`, `.jsonl` or text).
- Fewer than about 50 prompts makes a thin report. Say so, and ask whether they have more history elsewhere before going on.

## 2. Read every prompt

Read all of `ef-work/prompts.jsonl`, not a sample. For more than about 300 KB, split it into chunks and read each in turn (or hand chunks to subagents and merge their notes). Take notes under the headings in step 3, and for each note keep one short **verbatim** quote (under 20 words, typos kept) with its date and the project it came from (`where`). Read `stats.json` too: its counts go on the page as they are.

What to look for:

- **Kinds of UI** — the genres they build: workspaces, dashboards, boards, timelines, editors, mail clients, games, specs, explainers. Ground these in what the prompts were about, not in what you guess.
- **Features** — what they add once an app exists: variations, progress, collapse, drag to reorder, persistence, undo, filters, templates.
- **Interaction techniques** — drag and reflow, snapping, hover reveals, marks and annotation, keyboard modes, focus+context, overview+detail, progressive disclosure, morphing objects, touch, voice.
- **How they prompt** — screenshots and pointing, asking for variations then picking one, designing by refusal, numbered fix lists, spec-first, whole-pipeline delegation, procedures and loops, personas, stating the reason, interpolating between options.
- **Design language** — the qualities they ask for, and what they send back (a separate list of refusals, each with a quote).
- **Metaphors and borrowed products** — every app, site and physical object they name as a model, and which of their own projects it shaped.
- **Vocabulary** — the precise UI words they use, the vague ones ("thing", "make it nicer"), and the places they describe at length something that has a standard name (e.g. "floating tooltip" → popover, "gradual scale down as you focus" → semantic zoom).
- **Edges** — what is missing: unhappy-path states, phone or dark layouts, chart types by name, motion in numbers, words on the page, accessibility, contradictions they have not settled.

Judge each entry's level from the evidence: **fluent** (frequent and specific), **growing** (several times, or once in depth), **rare** (once, or only as an absence). Do not inflate. Do not invent numbers: every count on the page comes from `stats.json` or from a count you actually made.

## 3. Write `ef-work/analysis.json`

```json
{
  "name": "Ada",
  "generated": "2026-10-10",
  "verdict": "One paragraph, second person, plain words: what they are fluent in, how they close the gap between picturing and naming, what their taste is, and what is thin.",
  "strongest": "One sentence.",
  "distinctive": "One sentence: the move that is most theirs.",
  "thinnest": "One sentence.",
  "sections": {
    "kinds":       [ {"title": "Agent workspaces", "level": "fluent", "desc": "One or two sentences.", "quote": "verbatim words", "where": "project", "date": "17 Sep", "sketch": "<rect class='fc' x='6' y='6' width='40' height='60' rx='3'/>…"} ],
    "features":    [ … ],
    "interaction": [ … ],
    "prompting":   [ … ],
    "style":       [ … ],
    "metaphors":   [ … ],
    "edges":       [ {"title": "…", "level": "rare", "desc": "…", "quote": "…", "next": "One concrete thing to try next."} ]
  },
  "refusals":   [ {"name": "Fingernail borders", "quote": "verbatim", "date": "29 Sep"} ],
  "names":      [ {"said": "floating tooltip", "name": "popover", "sketch": "<rect class='fc' …/>"} ],
  "loop":       [ {"step": "Ask for variations", "detail": "A to E, side by side", "repeats": true} ],
  "references": [ {"from": "Figma", "to": "their whiteboard app"} ]
}
```

Aim for 7–13 entries in each section, ordered fluent → growing → rare; 6–10 refusals; 8–14 names; a loop of 4–7 steps; a reference pair for each thing borrowed and the project of theirs it shaped.

`sketch`: draw one for every entry a picture can show, which is nearly all of them. It is a small wireframe of the entry drawn as SVG shapes in a 160×72 box, as a designer would sketch it in a margin. Only `rect`, `line`, `circle`, `ellipse`, `path`, `polyline`, `polygon`, `g`; only geometry attributes; only the classes `ln` (muted stroke), `lt` (faint stroke), `fl` (grey fill), `fc` (card fill), `ac` (colour fill), `a2` (pale colour fill), `as` (colour stroke), `dash`. No text in a sketch. `render.py` strips anything else.

The colour is not yours to pick: the report paints `ac`, `a2` and `as` in the colour of the entry's part of the range (green for kinds, features and interaction; blue for prompting and design language; terracotta for references; gold for edges), so the same colour means the same thing on every chart. Use `ac` for the one thing the entry is about and `a2` for what it acts on or what comes second; leave the rest grey. A rare entry is dashed. An edge is drawn as what its `next` would look like if they tried it, dashed where it does not exist yet, so the reader can see the thing they have not asked for.

Each `names` item may carry a `sketch` too, in the same box and classes: a picture of the named pattern (a loupe with a filmstrip under it, a slider wiping between two images), so the name arrives with an example. Draw one for every name you can.

Words: plain and specific, second person, no hype, no "leverage" or "seamless". Every heading and line should tell the reader something about themselves.

## 4. Render

```sh
python3 scripts/render.py --work ef-work --out envisioning-fluency.html
```

It checks the analysis and writes one HTML file (no network, light and dark, phone and desk). Tell them where it is, and open it: with a `collector.json`, open it through step 5 so its send bar works. In the report they can change any level; the change is kept in their browser.

## 5. Open it with the send bar (only if `collector.json` exists)

If this skill came with a `collector.json`, its owner collects reports on a page only they can read, and the person decides from the report itself. Open the report this way instead of as a file:

```sh
python3 scripts/send.py --work ef-work --serve
```

It opens the report in their browser from this machine (127.0.0.1) with a send bar pinned to the bottom of the window, there the whole time they read. Pressing it opens a sheet that says what goes (the verdict, the findings, every entry with the level they left it at and the line of theirs behind it, and the counts), what never goes (their prompt history), and who can read it (only the owner: the link can add to their page but cannot open it), with a choice to send only the summary. Nothing is sent until they press Send there; the levels sent are the ones they left on the page. The command waits until they send or close it, up to half an hour, so run it in the background if you need to keep working. Tell them the report is open and the bar is at the bottom; do not press Send for them.

If no browser can open on this machine (a remote or cloud session), print the address the command gives so they can open it, or fall back to asking in chat: show them `python3 scripts/send.py --work ef-work --preview`, and only if they say yes, run `python3 scripts/send.py --work ef-work --send` (add `--summary-only` for less). Opened later as a plain file, the report still shows the bar and says how to send from it.

If they say no, or there is no `collector.json`, the HTML file is the whole result.

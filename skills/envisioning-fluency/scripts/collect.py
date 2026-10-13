#!/usr/bin/env python3
"""Gather one person's own prompts to coding agents, and count what is in them.

Reads the chat histories that coding agents keep on this machine, keeps only
the words the person typed (not tool output, not system text, not pasted
logs), drops repeats, and writes two files:

  prompts.jsonl  one prompt per line: {"ts", "source", "where", "text"}
  stats.json     counts the report is drawn from: prompts per day, length,
                 screenshots, refusals, interface words, products named

Nothing leaves the machine. Standard library only, Python 3.8+.

  python3 collect.py --out ./ef-work
  python3 collect.py --out ./ef-work --only claude,codex --since 2026-09-01
  python3 collect.py --out ./ef-work --file my-prompts.txt      # any export
"""

import argparse
import datetime as dt
import glob
import json
import os
import re
import sqlite3
import statistics
import sys
from collections import Counter

HOME = os.path.expanduser("~")

# --------------------------------------------------------------- what to keep

# Text an agent or harness wrote into the user turn, not the person.
MACHINE = re.compile(
    r"^\s*(<command-|<local-command|<task-notification|<environment_context|<user_instructions|"
    r"Caveat: The messages below|\[Request interrupted|# AGENTS\.md|<system-reminder>|"
    r"This session is being continued|tool_use_id|The ask: \"\"\")",
    re.I,
)
REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
PASTED = re.compile(r"<pasted_content[^>]*>.*?</pasted_content[^>]*>", re.S)
BLOCK = re.compile(r"<([a-z][\w-]*)\b[^>]*>(?:(?!</\1>).){400,}?</\1>", re.S | re.I)
# Marble Drive build mode wraps the person's marks in a brief; keep the marks.
BUILD_MARK = re.compile(r'(?:Sent by the person to be made now|The prompt the app was made from)[^:]*?\):\s*"(.*?)"(?:\.\s|\n|$)', re.S)
CONTEXT_TAIL = re.compile(r"\n---\nContext from Marble Drive.*", re.S)


def clean(text):
    """The person's words in a user turn, or None if there are none."""
    if not isinstance(text, str):
        return None
    if text.startswith("Build mode"):
        marks = BUILD_MARK.findall(text)
        text = "\n".join(marks)
    text = CONTEXT_TAIL.sub("", text)
    text = REMINDER.sub("", text)
    text = PASTED.sub("[pasted]", text)
    # Long tagged blocks a tool attached (a board, a file, pasted text) are context, not words.
    text = BLOCK.sub("[attached]", text).strip()
    if len(text) < 4 or MACHINE.match(text):
        return None
    # A wall of pasted log is not a prompt; keep its head.
    return text[:6000]


def text_of(content):
    """Text from a message's content, whatever shape the agent stored it in."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") in ("text", "input_text") and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, dict) and item.get("type") in ("image", "input_image", "image_url"):
                parts.append("[image]")
        return " ".join(parts)
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    return None


def stamp(value):
    """An ISO date string from whatever an agent recorded, or ''."""
    if value is None:
        return ""
    try:
        if isinstance(value, (int, float)):
            value = value / 1000 if value > 1e11 else value
            return dt.datetime.fromtimestamp(value).isoformat()
        return str(value)
    except (ValueError, OSError):
        return ""


def read_jsonl(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue
    except OSError:
        return


# ------------------------------------------------------------------- sources

def from_claude():
    """Claude Code: ~/.claude/projects/<project>/<session>.jsonl.

    Tools built on the Agent SDK leave sessions here too (a titler, a
    classifier): one templated prompt, sent once. Those are a program's
    words, not the person's, so a one-turn SDK session is skipped unless it
    is plainly a person's (a Marble Drive chat or build)."""
    for path in glob.glob(os.path.join(HOME, ".claude", "projects", "*", "*.jsonl")):
        where = os.path.basename(os.path.dirname(path))
        turns = []
        for d in read_jsonl(path):
            if d.get("type") != "user" or d.get("isMeta") or d.get("isSidechain"):
                continue
            msg = d.get("message") or {}
            content = msg.get("content")
            if isinstance(content, list) and any(isinstance(i, dict) and i.get("type") == "tool_result" for i in content):
                continue
            turns.append((d.get("timestamp", ""), text_of(content), str(d.get("entrypoint", ""))))
        first = turns[0][1] or "" if turns else ""
        if len(turns) == 1 and turns[0][2].startswith("sdk") \
                and not (first.startswith("Build mode") or "Context from Marble Drive" in first):
            continue
        for ts, text, _ in turns:
            yield ts, "claude-code", where, text


def from_codex():
    """Codex CLI: ~/.codex/sessions/**/rollout-*.jsonl, and ~/.codex/history.jsonl."""
    root = os.path.join(os.environ.get("CODEX_HOME", os.path.join(HOME, ".codex")))
    for path in glob.glob(os.path.join(root, "sessions", "**", "*.jsonl"), recursive=True):
        for d in read_jsonl(path):
            item = d.get("payload") if isinstance(d.get("payload"), dict) else d
            if item.get("type") == "message" and item.get("role") == "user":
                yield d.get("timestamp", ""), "codex", os.path.basename(path), text_of(item.get("content"))
            elif item.get("type") == "user_message" and isinstance(item.get("message"), str):
                yield d.get("timestamp", ""), "codex", os.path.basename(path), item["message"]
    for d in read_jsonl(os.path.join(root, "history.jsonl")):
        if isinstance(d.get("text"), str):
            yield stamp(d.get("ts")), "codex", "history", d["text"]


def from_gemini():
    """Gemini CLI: ~/.gemini/tmp/<project>/logs.json and chats/*.json."""
    root = os.path.join(HOME, ".gemini", "tmp")
    for path in glob.glob(os.path.join(root, "*", "logs.json")) + glob.glob(os.path.join(root, "*", "chats", "*.json")):
        try:
            data = json.load(open(path, encoding="utf-8", errors="ignore"))
        except (OSError, ValueError):
            continue
        yield from walk(data, "gemini", os.path.basename(os.path.dirname(path)))


def cursor_dirs():
    if sys.platform == "darwin":
        base = os.path.join(HOME, "Library", "Application Support", "Cursor", "User")
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA", ""), "Cursor", "User")
    else:
        base = os.path.join(HOME, ".config", "Cursor", "User")
    return base


def from_cursor():
    """Cursor: the prompt list in each workspace's state.vscdb, and the
    composer bubbles in the global one. Best effort: the format is Cursor's
    own and changes between versions."""
    base = cursor_dirs()
    dbs = glob.glob(os.path.join(base, "workspaceStorage", "*", "state.vscdb"))
    dbs += glob.glob(os.path.join(base, "globalStorage", "state.vscdb"))
    for db in dbs:
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        except sqlite3.Error:
            continue
        try:
            for (value,) in con.execute("SELECT value FROM ItemTable WHERE key = 'aiService.prompts'"):
                for p in json.loads(value) or []:
                    if isinstance(p, dict) and isinstance(p.get("text"), str):
                        yield "", "cursor", os.path.basename(os.path.dirname(db)), p["text"]
        except (sqlite3.Error, ValueError, TypeError):
            pass
        try:
            for (value,) in con.execute("SELECT value FROM cursorDiskKV WHERE key LIKE 'bubbleId:%'"):
                b = json.loads(value)
                if isinstance(b, dict) and b.get("type") == 1 and isinstance(b.get("text"), str):
                    yield stamp(b.get("createdAt")), "cursor", "composer", b["text"]
        except (sqlite3.Error, ValueError, TypeError):
            pass
        con.close()


def walk(data, source, where):
    """Any JSON: every object that looks like a user turn."""
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            role = node.get("role") or node.get("type") or node.get("author")
            if role in ("user", "human"):
                text = text_of(node.get("content")) or node.get("message") or node.get("text")
                if isinstance(text, dict):
                    text = text_of(text.get("content"))
                if isinstance(text, str):
                    yield stamp(node.get("timestamp") or node.get("ts") or node.get("created_at")), source, where, text
                    continue
            stack.extend(v for v in node.values() if isinstance(v, (list, dict)))


def from_files(paths):
    """Exports and pastes: .json/.jsonl are searched for user turns; anything
    else is plain text, one prompt per block (blank line or --- between)."""
    for path in paths:
        name = os.path.basename(path)
        if path.endswith(".jsonl"):
            for d in read_jsonl(path):
                yield from walk(d, "file", name)
        elif path.endswith(".json"):
            try:
                yield from walk(json.load(open(path, encoding="utf-8", errors="ignore")), "file", name)
            except (OSError, ValueError):
                continue
        else:
            try:
                body = open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for block in re.split(r"\n\s*(?:---+)?\s*\n", body):
                yield "", "file", name, block


SOURCES = {"claude": from_claude, "codex": from_codex, "gemini": from_gemini, "cursor": from_cursor}

# -------------------------------------------------------------------- counts

PARTS = ["button", "row", "drag", "icon", "card", "sidebar", "hover", "tooltip", "menu", "pane", "toggle",
         "widget", "panel", "tab", "margin", "sheet", "preview", "toolbar", "snap", "pill", "modal", "popover",
         "slider", "canvas", "timeline", "table", "chart", "dropdown", "badge", "drawer"]
FEEL = ["thing", "stuff", "visual", "clean", "feel", "smooth", "nice", "minimal", "pretty", "simple",
        "salient", "native", "quiet", "alive", "elastic", "playful", "polished", "modern", "sleek"]
NAMED = ["popover", "breadcrumb", "drawer", "placeholder", "chevron", "toast", "reflow", "progressive disclosure",
         "modal", "segmented control", "empty state", "drag handle", "spring", "stagger", "drill-down",
         "semantic zoom", "affordance", "skeleton", "command palette", "focus ring", "overview ruler"]
PRODUCTS = ["apple", "ios", "macos", "figma", "notion", "google docs", "gmail", "google", "linear", "slack",
            "discord", "spotify", "instagram", "tiktok", "youtube", "github", "vscode", "vs code", "cursor",
            "claude", "chatgpt", "excel", "sheets", "powerpoint", "keynote", "trello", "jira", "miro",
            "obsidian", "airbnb", "uber", "stripe", "vercel", "tailwind", "material", "newspaper", "whiteboard",
            "sticky note", "post-it", "paper", "pokemon", "nintendo", "iterm", "finder", "windows", "android"]


def forms(word):
    """A word with its common endings, as one alternation."""
    if " " in word or "-" in word:
        return re.escape(word) + r"s?"
    return re.escape(word) + r"(?:s|es|ed|ing|er|y)?"


def count(texts, words):
    low = "\n".join(texts).lower()
    return {w: len(re.findall(r"\b" + forms(w) + r"\b", low)) for w in words}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="ef-work", help="folder for prompts.jsonl and stats.json")
    ap.add_argument("--only", default="", help="comma list of sources: claude,codex,gemini,cursor")
    ap.add_argument("--file", action="append", default=[], help="an exported or pasted history (repeatable)")
    ap.add_argument("--since", default="", help="keep prompts on or after this date (YYYY-MM-DD)")
    args = ap.parse_args()

    chosen = [s.strip() for s in args.only.split(",") if s.strip()] or list(SOURCES)
    raw = []
    for name in chosen:
        if name in SOURCES:
            raw.extend(SOURCES[name]())
    raw.extend(from_files(args.file))

    seen, kept = set(), []
    for ts, source, where, text in raw:
        text = clean(text)
        if not text:
            continue
        ts = stamp(ts)[:19]
        if args.since and ts and ts[:10] < args.since:
            continue
        key = re.sub(r"\W+", "", text.lower())[:160]
        if key in seen:
            continue
        seen.add(key)
        kept.append({"ts": ts, "source": source, "where": where, "text": text})
    kept.sort(key=lambda p: p["ts"] or "9999")

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "prompts.jsonl"), "w", encoding="utf-8") as f:
        for p in kept:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    texts = [p["text"] for p in kept]
    words = [len(re.findall(r"\w+", t)) for t in texts] or [0]
    days = Counter(p["ts"][:10] for p in kept if p["ts"])
    stats = {
        "prompts": len(kept),
        "sources": dict(Counter(p["source"] for p in kept)),
        "first": min(days) if days else "",
        "last": max(days) if days else "",
        "per_day": dict(sorted(days.items())),
        "median_words": statistics.median(words),
        "over_100_words": sum(w >= 100 for w in words),
        "under_13_words": sum(w <= 12 for w in words),
        "with_image": sum(bool(re.search(r"\[image|screenshot|\.png\b", t, re.I)) for t in texts),
        "questions": sum("?" in t for t in texts),
        "refuse_or_remove": sum(bool(re.search(r"\b(don'?t|do not|no need|no more|remove|get rid|instead of|i don'?t (like|want|need))\b|\bno \w+ (please|pls)\b", t, re.I)) for t in texts),
        "asks_for_variations": sum(bool(re.search(r"\b(variations?|variants?|options|alternatives)\b", t, re.I)) for t in texts),
        "parts": count(texts, PARTS),
        "feel": count(texts, FEEL),
        "named": count(texts, NAMED),
        "products": {k: v for k, v in count(texts, PRODUCTS).items() if v},
    }
    with open(os.path.join(args.out, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    print(f"{len(kept)} prompts from {', '.join(f'{k} {v}' for k, v in stats['sources'].items()) or 'no source'}")
    print(f"wrote {os.path.join(args.out, 'prompts.jsonl')} and stats.json")
    if not kept:
        print("No prompts found. Point --file at an exported chat history, or a text file of prompts.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

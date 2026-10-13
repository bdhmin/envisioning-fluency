#!/usr/bin/env python3
"""Gather one person's own prompts to coding agents, what they built with
them, and count what is in them.

Reads the chat histories that coding agents keep on this machine, keeps only
the words the person typed (not tool output, not system text, not pasted
logs), drops repeats, then looks in the folder each conversation ran in for
what was built there. Writes three files:

  prompts.jsonl   one prompt per line: {"ts", "source", "where", "text"}
  stats.json      counts the report is drawn from: prompts per day, length,
                  screenshots, refusals, interface words, products named, and
                  every project read, so the report can list them
  artifacts.json  per project folder: its files, the interface files in it,
                  what it is made with, the techniques its code uses, and its
                  git history. Read by the agent, never sent.

Nothing leaves the machine. Standard library only, Python 3.8+.

  python3 collect.py --out ./ef-work
  python3 collect.py --out ./ef-work --leave-out acme --leave-out tax   # iterate
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
import urllib.parse
import statistics
import subprocess
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
        cwd = None
        turns = []
        for d in read_jsonl(path):
            cwd = cwd or (d.get("cwd") if isinstance(d.get("cwd"), str) else None)
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
            yield ts, "claude-code", "Claude Code", text, cwd


def from_codex():
    """Codex CLI: ~/.codex/sessions/**/rollout-*.jsonl, and ~/.codex/history.jsonl."""
    root = os.path.join(os.environ.get("CODEX_HOME", os.path.join(HOME, ".codex")))
    for path in glob.glob(os.path.join(root, "sessions", "**", "*.jsonl"), recursive=True):
        cwd = None
        for d in read_jsonl(path):
            item = d.get("payload") if isinstance(d.get("payload"), dict) else d
            if isinstance(item.get("cwd"), str):
                cwd = cwd or item["cwd"]
            if item.get("type") == "message" and item.get("role") == "user":
                yield d.get("timestamp", ""), "codex", "Codex", text_of(item.get("content")), cwd
            elif item.get("type") == "user_message" and isinstance(item.get("message"), str):
                yield d.get("timestamp", ""), "codex", "Codex", item["message"], cwd
    for d in read_jsonl(os.path.join(root, "history.jsonl")):
        if isinstance(d.get("text"), str):
            yield stamp(d.get("ts")), "codex", "Codex", d["text"], None


def from_gemini():
    """Gemini CLI: ~/.gemini/tmp/<project>/logs.json and chats/*.json."""
    root = os.path.join(HOME, ".gemini", "tmp")
    for path in glob.glob(os.path.join(root, "*", "logs.json")) + glob.glob(os.path.join(root, "*", "chats", "*.json")):
        try:
            data = json.load(open(path, encoding="utf-8", errors="ignore"))
        except (OSError, ValueError):
            continue
        yield from walk(data, "gemini", "Gemini CLI")


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
        folder = None
        try:
            ws = json.load(open(os.path.join(os.path.dirname(db), "workspace.json"), encoding="utf-8"))
            uri = ws.get("folder") or ""
            if uri.startswith("file://"):
                folder = urllib.parse.unquote(uri[7:])
        except (OSError, ValueError, AttributeError):
            pass
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        except sqlite3.Error:
            continue
        try:
            for (value,) in con.execute("SELECT value FROM ItemTable WHERE key = 'aiService.prompts'"):
                for p in json.loads(value) or []:
                    if isinstance(p, dict) and isinstance(p.get("text"), str):
                        yield "", "cursor", "Cursor", p["text"], folder
        except (sqlite3.Error, ValueError, TypeError):
            pass
        try:
            for (value,) in con.execute("SELECT value FROM cursorDiskKV WHERE key LIKE 'bubbleId:%'"):
                b = json.loads(value)
                if isinstance(b, dict) and b.get("type") == 1 and isinstance(b.get("text"), str):
                    yield stamp(b.get("createdAt")), "cursor", "Cursor", b["text"], folder
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
                    yield stamp(node.get("timestamp") or node.get("ts") or node.get("created_at")), source, where, text, None
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
                yield "", "file", name, block, None


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


# ------------------------------------------------------- what they built

SKIP_DIRS = {"node_modules", ".git", "dist", "build", "out", ".next", ".nuxt", ".svelte-kit", ".venv", "venv",
             "env", "__pycache__", ".cache", "target", "vendor", "coverage", ".turbo", "Pods", "DerivedData",
             ".idea", ".vscode", ".marble", ".gradle", "site-packages", ".pytest_cache", ".mypy_cache"}
UI_EXT = {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte", ".css", ".scss", ".less", ".mrbl", ".swift", ".dart"}
CODE_EXT = UI_EXT | {".js", ".mjs", ".cjs", ".ts", ".py", ".kt", ".java", ".go", ".rs", ".rb", ".php", ".c", ".cpp", ".cs", ".r", ".jl", ".ipynb"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
MAX_FILES = 6000
# What the code does, counted as the number of files that do it. A count, not
# a judgement: the agent opens the files to see how well.
TECHNIQUES = {
    "drag and drop": r"draggable|ondrag|dragstart|onpointerdown|pointermove|usedrag|dnd-kit|sortablejs",
    "keyboard shortcuts": r"keydown|onkeydown|hotkey|usehotkeys|mousetrap",
    "animation": r"@keyframes|transition\s*:|framer-motion|requestanimationframe|\.animate\(|gsap|spring\(",
    "drawing and graphics": r"<canvas|getcontext\(|three\.|webgl|\bd3\.|<svg|plotly|chart\.js|recharts|vega",
    "saved state": r"localstorage|indexeddb|sessionstorage",
    "dark mode": r"prefers-color-scheme|light-dark\(|\bdark:",
    "responsive layout": r"@media|@container|usemediaquery|matchmedia",
    "accessibility": r"aria-|role=",
    "live updates": r"websocket|eventsource|socket\.io|supabase|firebase",
    "undo": r"\bundo\b|\bredo\b",
    "touch and gestures": r"touchstart|pointertype|gesture|pinch",
    "AI calls": r"anthropic|openai|generatecontent|/v1/messages|chat\.completions",
}
TECH_RE = {k: re.compile(v, re.I) for k, v in TECHNIQUES.items()}


def git_history(folder):
    if not os.path.isdir(os.path.join(folder, ".git")):
        return None
    try:
        out = subprocess.run(["git", "-C", folder, "log", "--format=%ad", "--date=short"], capture_output=True,
                             text=True, timeout=15).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return {"commits": len(out), "first": min(out), "last": max(out)} if out else None


def built_in(folder):
    """What is in one project folder: a look, not a reading. Never runs anything
    but `git log`, never follows a link out of the folder."""
    files, ext_count, ui, lines, images = 0, Counter(), [], 0, 0
    tech = Counter()
    read_for_tech = 0
    partial = False
    for root, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for n in names:
            if n.startswith("."):
                continue
            files += 1
            if files > MAX_FILES:
                partial = True
                break
            ext = os.path.splitext(n)[1].lower()
            ext_count[ext or n] += 1
            path = os.path.join(root, n)
            if ext in IMAGE_EXT:
                images += 1
            if ext not in CODE_EXT:
                continue
            try:
                size = os.path.getsize(path)
                if size > 400_000:
                    continue
                body = open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            nlines = body.count("\n") + 1
            lines += nlines
            if ext in UI_EXT:
                ui.append((nlines, os.path.relpath(path, folder)))
            if read_for_tech < 600 and ext in UI_EXT | {".js", ".mjs", ".ts"}:
                read_for_tech += 1
                for k, rx in TECH_RE.items():
                    if rx.search(body):
                        tech[k] += 1
        if partial:
            break
    if not files:
        return None
    deps = []
    try:
        pkg = json.load(open(os.path.join(folder, "package.json"), encoding="utf-8"))
        deps = sorted(set(pkg.get("dependencies") or {}) | set(pkg.get("devDependencies") or {}))[:40]
    except (OSError, ValueError, AttributeError):
        pass
    try:
        reqs = open(os.path.join(folder, "requirements.txt"), encoding="utf-8").read()
        deps += [re.split(r"[<>=~!\[ ;]", line.strip())[0] for line in reqs.splitlines() if line.strip() and not line.startswith("#")][:20]
    except OSError:
        pass
    readme = ""
    for n in ("README.md", "readme.md", "README", "README.txt"):
        try:
            readme = open(os.path.join(folder, n), encoding="utf-8", errors="ignore").read(600)
            break
        except OSError:
            continue
    ui.sort(reverse=True)
    return {
        "files": min(files, MAX_FILES), "partial": partial, "lines_of_code": lines, "images": images,
        "kinds_of_file": dict(ext_count.most_common(12)),
        "interface_files": [{"path": p, "lines": n} for n, p in ui[:20]],
        "made_with": deps,
        "techniques": dict(tech.most_common()),
        "git": git_history(folder),
        "readme": readme,
    }


def whose():
    """The name to put on the report: git's, then the account's, then the login."""
    try:
        name = subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True, timeout=5).stdout.strip()
        if name:
            return name.split()[0]
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        import pwd
        gecos = pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0].strip()
        if gecos:
            return gecos.split()[0]
    except (ImportError, KeyError, AttributeError):
        pass
    return (os.environ.get("USER") or os.environ.get("USERNAME") or "You").capitalize()


def project_names(folders):
    """A short name for each folder: its own name, or parent/name where two
    folders share one. Never the whole path."""
    base = Counter(os.path.basename(f.rstrip("/\\")) for f in folders)
    names = {}
    for f in folders:
        b = os.path.basename(f.rstrip("/\\")) or f
        parent = os.path.basename(os.path.dirname(f.rstrip("/\\")))
        names[f] = b if base[b] == 1 else parent + "/" + b
    return names


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="ef-work", help="folder for prompts.jsonl and stats.json")
    ap.add_argument("--only", default="", help="comma list of sources: claude,codex,gemini,cursor")
    ap.add_argument("--file", action="append", default=[], help="an exported or pasted history (repeatable)")
    ap.add_argument("--since", default="", help="keep prompts on or after this date (YYYY-MM-DD)")
    ap.add_argument("--leave-out", action="append", default=[], metavar="NAME",
                    help="leave out every project whose name or folder contains NAME (repeatable)")
    ap.add_argument("--no-built", action="store_true", help="read the prompts only, not the project folders")
    args = ap.parse_args()

    chosen = [s.strip() for s in args.only.split(",") if s.strip()] or list(SOURCES)
    raw = []
    for name in chosen:
        if name in SOURCES:
            raw.extend(SOURCES[name]())
    raw.extend(from_files(args.file))

    # Each conversation's folder names its project; a home folder or the
    # root names nothing, and is never looked through.
    def real(folder):
        if not folder:
            return None
        f = os.path.normpath(os.path.expanduser(folder))
        return None if f in (HOME, os.path.dirname(HOME), "/", os.path.abspath(os.sep)) else f
    folders = sorted({real(r[4]) for r in raw if real(r[4])})
    names = project_names(folders)
    leave = [x.lower() for x in args.leave_out if x.strip()]
    left_out = Counter()

    seen, kept, folder_of = set(), [], {}
    for ts, source, where, text, folder in raw:
        text = clean(text)
        if not text:
            continue
        if folder and os.path.normpath(os.path.expanduser(folder)) == HOME:
            where = "home folder"
        folder = real(folder)
        where = names.get(folder, where)
        if leave and any(x in where.lower() or (folder and x in folder.lower()) for x in leave):
            left_out[where] += 1
            continue
        if folder:
            folder_of[where] = folder
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

    # What was built where: every project with prompts, and its folder looked through.
    artifacts, projects = {}, []
    by = {}
    for p in kept:
        by.setdefault(p["where"], []).append(p)
    for name, ps in sorted(by.items(), key=lambda kv: -len(kv[1])):
        folder = folder_of.get(name)
        built = None
        if folder and not args.no_built and os.path.isdir(folder):
            built = built_in(folder)
            if built:
                artifacts[name] = {"folder": folder, **built}
        ds = [p["ts"][:10] for p in ps if p["ts"]]
        projects.append({
            "name": name,
            "sources": dict(Counter(p["source"] for p in ps)),
            "prompts": len(ps),
            "first": min(ds) if ds else "",
            "last": max(ds) if ds else "",
            "built": {"files": built["files"], "interface_files": len(built["interface_files"]),
                      "lines_of_code": built["lines_of_code"], "commits": (built["git"] or {}).get("commits", 0)} if built else None,
        })
    stats["person"] = whose()
    stats["projects"] = projects
    stats["left_out"] = [{"name": k, "prompts": v} for k, v in left_out.most_common()]
    with open(os.path.join(args.out, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    with open(os.path.join(args.out, "artifacts.json"), "w", encoding="utf-8") as f:
        json.dump(artifacts, f, indent=2)

    print(f"{len(kept)} prompts from {', '.join(f'{k} {v}' for k, v in stats['sources'].items()) or 'no source'}, "
          f"in {len(projects)} projects; looked through {len(artifacts)} project folders")
    if left_out:
        print("left out: " + ", ".join(f"{k} ({v})" for k, v in left_out.most_common()))
    print(f"wrote prompts.jsonl, stats.json and artifacts.json in {args.out}")
    if not kept:
        print("No prompts found. Point --file at an exported chat history, or a text file of prompts.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

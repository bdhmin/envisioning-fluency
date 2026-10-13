#!/usr/bin/env python3
"""Send a summary of your report to a shared Marble Drive page. Opt-in.

  python3 send.py --work ./ef-work --serve       # open the report with its send bar
  python3 send.py --work ./ef-work --preview     # see exactly what would go
  python3 send.py --work ./ef-work --send        # send it from here

--serve opens the rendered report from this machine (127.0.0.1 only), so the
Send button pinned to its foot works: the person reads the report, sees what
would go, and presses Send themselves. Nothing is sent until they do.

What goes: your report — the verdict, the findings, every entry with its
level and the line of yours that backs it, and the counts — which becomes a
page of its own in the owner's drive. With --summary-only, just the summary:
name, date, verdict, the three findings, a square per entry, the titles you
are fluent in and your edges. What never goes: your prompt history. The page
and link are in ../collector.json. It is an add-only link: it can add to
that one page and nothing else, and it cannot open the page, so only its
owner can read what anyone sent.

Standard library only.
"""

import argparse
import html
import json
import os
import re
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "..", "collector.json")
SECTIONS = [("kinds", "Kinds of UI"), ("features", "Features"), ("interaction", "Interaction"),
            ("prompting", "Prompting"), ("style", "Design language"), ("metaphors", "References"),
            ("edges", "Edges")]
MARK = {"fluent": "f", "growing": "g", "rare": "r"}

e = lambda s: html.escape(str(s or ""), quote=True)


def leave_out(analysis, stats, out):
    """Take out what the person kept back in the report: whole projects (their
    entries, lines, references and what was built there) and single cards,
    named "section:index" as the page numbers them."""
    out = out or {}
    projects = {str(p) for p in out.get("projects") or []}
    cards = {str(c) for c in out.get("entries") or []}
    if not projects and not cards:
        return analysis, stats

    def gone(x):
        if not isinstance(x, dict):
            return False
        built = x.get("built") if isinstance(x.get("built"), dict) else {}
        return x.get("where") in projects or built.get("where") in projects

    a = json.loads(json.dumps(analysis))
    secs = a.get("sections") or {}
    for k, items in list(secs.items()):
        secs[k] = [x for i, x in enumerate(items or []) if f"{k}:{i}" not in cards and not gone(x)]
    a["built"] = [x for i, x in enumerate(a.get("built") or []) if f"built:{i}" not in cards and not gone(x)]
    for key in ("refusals", "names", "references"):
        a[key] = [x for x in a.get(key) or [] if not gone(x)]
    # A line kept from another project can still name one that was switched
    # off ("same as the triage board"): the name goes, wherever it is.
    if projects:
        rx = re.compile(r"\b(" + "|".join(re.escape(p) for p in sorted(projects, key=len, reverse=True)) + r")\b", re.I)

        def scrub(v):
            if isinstance(v, str):
                return rx.sub("[left out]", v)
            if isinstance(v, list):
                return [scrub(x) for x in v]
            if isinstance(v, dict):
                return {k: scrub(x) for k, x in v.items()}
            return v
        a = scrub(a)
    st = dict(stats)
    st["projects"] = [p for p in stats.get("projects") or [] if p.get("name") not in projects]
    st.pop("left_out", None)
    return a, st


def report_data(analysis, stats):
    """The whole report as data, for the owner's drive to make a page from.
    It is read as data there, never run."""
    keep = {k: analysis.get(k) for k in ("name", "generated", "verdict", "strongest", "distinctive", "thinnest",
                                          "sections", "built", "refusals", "names", "loop", "references")}
    counts = {k: stats.get(k) for k in ("prompts", "sources", "first", "last", "per_day", "median_words",
                                         "with_image", "refuse_or_remove", "asks_for_variations", "parts", "feel", "named",
                                         "projects")}
    return json.dumps({"analysis": keep, "stats": counts}, ensure_ascii=False, separators=(",", ":"))


def entry(analysis, stats, name, full=True):
    secs = analysis.get("sections") or {}
    rows = "".join(
        f'<div class="lv-row"><span>{label}</span><span class="sq">'
        + "".join(f'<i class="{MARK.get(x.get("level"), "r")}"></i>' for x in secs.get(k, []))
        + "</span></div>"
        for k, label in SECTIONS
    )
    fluent = [x["title"] for k in ("kinds", "interaction", "prompting") for x in secs.get(k, []) if x.get("level") == "fluent"]
    edges = [x["title"] for x in secs.get("edges", [])]
    sources = ", ".join(k for k in (stats.get("sources") or {}))
    meta = f'{e(analysis.get("generated"))} · {int(stats.get("prompts", 0)):,} prompts · {e(sources)}'
    return (
        '<article class="rep" data-marble-removable'
        + (f' data-report="{e(report_data(analysis, stats))}"' if full else "")
        + ">"
        f"<h2>{e(name)}</h2><p class=\"meta\">{meta}</p>"
        f'<p class="verdict">{e(analysis.get("verdict"))}</p>'
        f'<div class="lv-rows">{rows}</div>'
        '<dl class="three">'
        f'<div><dt>Strongest</dt><dd>{e(analysis.get("strongest"))}</dd></div>'
        f'<div><dt>Most their own</dt><dd>{e(analysis.get("distinctive"))}</dd></div>'
        f'<div><dt>Thinnest</dt><dd>{e(analysis.get("thinnest"))}</dd></div>'
        "</dl>"
        + (f'<p class="list"><b>Fluent in</b>{e(", ".join(fluent))}</p>' if fluent else "")
        + (f'<p class="list"><b>Edges</b>{e(", ".join(edges))}</p>' if edges else "")
        + "</article>"
    )


def preview(analysis, stats, name, full=True):
    secs = analysis.get("sections") or {}
    lines = [f"To: {CONF['page']} (via the link in collector.json)", "", f"{name} · {analysis.get('generated')} · {stats.get('prompts')} prompts", "",
             analysis.get("verdict", ""), "", f"Strongest: {analysis.get('strongest')}",
             f"Most their own: {analysis.get('distinctive')}", f"Thinnest: {analysis.get('thinnest')}", ""]
    for k, label in SECTIONS:
        lv = [x.get("level", "?")[0].upper() for x in secs.get(k, [])]
        lines.append(f"{label:16} {' '.join(lv)}")
    lines += ["", "Fluent in: " + ", ".join(x["title"] for k in ("kinds", "interaction", "prompting") for x in secs.get(k, []) if x.get("level") == "fluent"),
              "Edges: " + ", ".join(x["title"] for x in secs.get("edges", [])), "",
              ("Also sent: the full report, with the line of yours behind each entry, to become a page of its own in the owner's drive."
               if full else "Not sent: the full report or the quotes."),
              "Never sent: your prompt history."]
    return "\n".join(lines)


class SendError(Exception):
    pass


def apply_levels(analysis, levels):
    """The levels the person left on the page ({"kinds:0": "fluent", ...})."""
    secs = analysis.get("sections") or {}
    for key, level in (levels or {}).items():
        k, _, i = str(key).partition(":")
        if level in MARK and k in secs and i.isdigit() and int(i) < len(secs[k]):
            secs[k][int(i)]["level"] = level
    return analysis


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def send(entry_html):
    link = CONF["share_link"]
    parts = urllib.parse.urlsplit(link)
    origin = f"{parts.scheme}://{parts.netloc}"
    opener = urllib.request.build_opener(NoRedirect)
    # Opening the link trades it for a cookie, and says where the page now is.
    try:
        opener.open(urllib.request.Request(link, headers={"User-Agent": "envisioning-fluency"}), timeout=20)
        raise SendError("The link did not answer as a share link. Ask whoever shared it for a fresh one.")
    except urllib.error.URLError as err:
        if not isinstance(err, urllib.error.HTTPError):
            raise SendError("Could not reach the page. Check the connection and try again.")
        res = err
        if res.code not in (301, 302, 303, 307, 308):
            raise SendError("This link is turned off or wrong. Ask whoever shared it for a fresh one.")
        cookie = "; ".join(c.split(";", 1)[0] for c in res.headers.get_all("Set-Cookie") or [])
        location = res.headers.get("Location") or ""
    if not cookie or not location.startswith("/a/"):
        raise SendError("The link opened, but gave no access to add to the page.")
    page = urllib.parse.unquote(location[len("/a/"):])
    op = [{"type": "insert", "parentId": CONF.get("list_id", "reports"), "beforeId": None, "html": entry_html}]
    url = f"{origin}/ops?app={urllib.parse.quote(page)}&client=ef-{secrets.token_hex(4)}"
    req = urllib.request.Request(url, data=json.dumps(op).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Cookie": cookie, "User-Agent": "envisioning-fluency"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            json.load(res)
    except urllib.error.HTTPError as res:
        try:
            why = json.load(res).get("error")
        except ValueError:
            why = f"HTTP {res.code}"
        raise SendError(f"The page refused the report: {why}")
    except urllib.error.URLError:
        raise SendError("Could not reach the page. Check the connection and try again.")
    return page, origin


def serve(analysis, stats, name, report_path):
    """Open the report from 127.0.0.1 so its send bar can send. Stops after a
    send, or after half an hour."""
    sys.path.insert(0, HERE)
    from render import collector_json
    token = secrets.token_urlsafe(18)
    try:
        page_html = open(report_path, encoding="utf-8").read()
    except OSError:
        sys.exit(f"No report at {report_path}. Run render.py first.")
    page_html, n = re.subn(r'(<script type="application/json" id="collector">).*?(</script>)',
                           lambda m: m.group(1) + collector_json(token) + m.group(2), page_html, count=1, flags=re.S)
    if not n:
        sys.exit("This report was rendered before reports had a send bar. Run render.py again.")
    body = page_html.encode("utf-8")
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, data, kind="application/json"):
            raw = data if isinstance(data, bytes) else json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path.split("?")[0] in ("/", "/index.html"):
                self.reply(200, body, "text/html; charset=utf-8")
            else:
                self.reply(404, {"error": "not here"})

        def do_POST(self):
            if self.path != "/send" or self.headers.get("X-EF-Token") != token:
                return self.reply(403, {"error": "This page cannot send."})
            try:
                ask = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            except ValueError:
                ask = {}
            full = not ask.get("summary_only")
            chosen = apply_levels(json.loads(json.dumps(analysis)), ask.get("levels"))
            chosen, kept_stats = leave_out(chosen, stats, ask.get("out"))
            who = str(ask.get("name") or "").strip()[:60] or name
            chosen["name"] = who
            try:
                page, origin = send(entry(chosen, kept_stats, who, full=full))
            except SendError as err:
                return self.reply(502, {"error": str(err)})
            print(f"Sent by {who} from the report. It is on {page}, at {origin}.", flush=True)
            self.reply(200, {"ok": True, "page": page})
            done.set()

    # One port where it is free, so levels changed on the page (kept by the
    # browser per address) are still there the next time it opens.
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 47615), Handler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"The report is open at {url}\nIts send bar is pinned to the bottom of the window; nothing goes until the person presses Send.", flush=True)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        sent = done.wait(timeout=30 * 60)
    except KeyboardInterrupt:
        sent = False
    if sent:
        done.wait(1.5)
    server.shutdown()
    print("Sent." if sent else "Closed without sending.")


def main():
    global CONF
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", default="ef-work")
    ap.add_argument("--name", help="the name to show; defaults to analysis.name")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--preview", action="store_true", help="print what would be sent, send nothing")
    group.add_argument("--send", action="store_true", help="send it")
    group.add_argument("--serve", action="store_true", help="open the report with its send bar, and send when the person presses Send")
    ap.add_argument("--report", default="envisioning-fluency.html", help="the rendered report, for --serve")
    ap.add_argument("--summary-only", action="store_true", help="send the summary without the full report")
    args = ap.parse_args()

    try:
        CONF = json.load(open(CONFIG, encoding="utf-8"))
    except (OSError, ValueError):
        sys.exit("No collector.json next to this skill, so there is nowhere to send. The report is still yours locally.")
    analysis = json.load(open(os.path.join(args.work, "analysis.json"), encoding="utf-8"))
    stats = json.load(open(os.path.join(args.work, "stats.json"), encoding="utf-8"))
    name = args.name or analysis.get("name") or "Someone"

    if args.preview:
        print(preview(analysis, stats, name, full=not args.summary_only))
        return
    if args.serve:
        serve(analysis, stats, name, args.report)
        return
    try:
        page, origin = send(entry(analysis, stats, name, full=not args.summary_only))
    except SendError as err:
        sys.exit(str(err))
    print(f"Sent. It is on {page}, at {origin}.")


if __name__ == "__main__":
    main()

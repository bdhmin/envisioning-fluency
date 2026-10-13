#!/usr/bin/env python3
"""Turn analysis.json + stats.json into one self-contained HTML report.

  python3 render.py --work ./ef-work --out ./envisioning-fluency.html

The analysis is the agent's judgement (see SKILL.md for its shape); the stats
are collect.py's counts. The template in ../assets/report.html draws both, so
every agent produces the same report. Standard library only.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "assets", "report.html")
SECTIONS = ["kinds", "features", "interaction", "prompting", "style", "metaphors", "edges"]
LEVELS = {"fluent", "growing", "rare"}

# A sketch may only draw: these shapes, geometry, and the template's classes.
SHAPE = re.compile(r"<(rect|line|circle|ellipse|path|polyline|polygon|g)\b([^<>]*)/?>|</g>", re.I)
ATTR = re.compile(r'\s([a-z-]+)\s*=\s*"([^"]*)"|\s([a-z-]+)\s*=\s*\'([^\']*)\'', re.I)
GEOMETRY = {"x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "width", "height", "d", "points", "class", "transform"}
CLASSES = {"ln", "lt", "fl", "fc", "ac", "a2", "as", "dash", "bad"}


def clean_sketch(svg):
    """Keep only drawing shapes with geometry and known classes."""
    out = []
    for m in SHAPE.finditer(svg or ""):
        if m.group(0).lower() == "</g>":
            out.append("</g>")
            continue
        attrs = []
        for a in ATTR.finditer(m.group(2) or ""):
            name, value = (a.group(1) or a.group(3)).lower(), a.group(2) if a.group(1) else a.group(4)
            if name not in GEOMETRY:
                continue
            if name == "class":
                value = " ".join(c for c in value.split() if c in CLASSES)
            if re.search(r"[<>]|url\(|javascript:", value, re.I):
                continue
            attrs.append(f'{name}="{value}"')
        tag = m.group(1).lower()
        out.append(f"<{tag} {' '.join(attrs)}>" if tag == "g" else f"<{tag} {' '.join(attrs)}/>")
    return "".join(out)


def collector_json(token=None):
    """Who collects reports, for the send bar; "null" when nobody does."""
    try:
        conf = json.load(open(os.path.join(HERE, "..", "collector.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return "null"
    if not conf.get("share_link"):
        return "null"
    out = {"owner": conf.get("owner"), "page": conf.get("page"), "link": conf.get("share_link")}
    if token:
        out["token"] = token
    return json.dumps(out, ensure_ascii=False).replace("</", "<\\/")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", default="ef-work", help="folder holding analysis.json and stats.json")
    ap.add_argument("--out", default="envisioning-fluency.html")
    args = ap.parse_args()

    try:
        analysis = json.load(open(os.path.join(args.work, "analysis.json"), encoding="utf-8"))
        stats = json.load(open(os.path.join(args.work, "stats.json"), encoding="utf-8"))
    except (OSError, ValueError) as err:
        sys.exit(f"Could not read the work folder: {err}")

    problems = []
    for field in ("verdict", "strongest", "distinctive", "thinnest", "sections"):
        if not analysis.get(field):
            problems.append(f"analysis.{field} is missing")
    for k in SECTIONS:
        items = (analysis.get("sections") or {}).get(k) or []
        if not items:
            problems.append(f"analysis.sections.{k} has no entries")
        for i, e in enumerate(items):
            if not e.get("title") or not e.get("desc"):
                problems.append(f"sections.{k}[{i}] needs a title and a desc")
            if e.get("level") not in LEVELS:
                problems.append(f"sections.{k}[{i}].level must be fluent, growing or rare")
            if e.get("sketch"):
                e["sketch"] = clean_sketch(e["sketch"])
    for key in ("names", "built"):
        for n in analysis.get(key) or []:
            if isinstance(n, dict) and n.get("sketch"):
                n["sketch"] = clean_sketch(n["sketch"])
    if problems:
        sys.exit("analysis.json is not finished:\n  " + "\n  ".join(problems))

    payload = json.dumps({"analysis": analysis, "stats": stats}, ensure_ascii=False)
    payload = payload.replace("</", "<\\/")  # never close the script tag early
    html = open(TEMPLATE, encoding="utf-8").read().replace("/*__DATA__*/null", payload)
    # With a collector.json the report carries a send bar: who collects and
    # where. send.py --serve adds the token that lets the bar actually send.
    html = html.replace("/*__SEND__*/null", collector_json())
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

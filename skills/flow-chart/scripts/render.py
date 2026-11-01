#!/usr/bin/env python3
"""Render a flow-chart / system-design spec (JSON) into one self-contained HTML page.

    python render.py docs/orders.spec.json [-o docs/orders.html] [--check-sources ROOT] [--strict]

What it does, in order:
  1. Validates the spec. Errors stop the build: nothing is written.
  2. Assigns IDs to anything without one and writes them back into the spec, so an ID
     stays with its object through later edits. Retired numbers are never reused.
  3. Lays out boxes on the spec's grid, routes lines around boxes, places line labels.
  4. Reports what a reader would trip on: crossings, label collisions, overflow.

Standard library only. The page's CSS and JS live in ../assets and are inlined.
"""
import argparse
import copy
import heapq
import json
import math
import re
import sys
from html import escape
from itertools import combinations
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
TONES = ("plain", "hub", "attention", "hold", "good", "danger", "muted")
SHAPES = ("box", "decision", "state", "terminal", "class")
RELS = ("arrow", "none", "inherits", "implements", "composes", "aggregates", "depends")
SIDES = {"top": 0, "right": 1, "bottom": 2, "left": 3}
DIRS = ((0, -1), (1, 0), (0, 1), (-1, 0))
GRID = 10


# ---------------------------------------------------------------- text measuring

def text_w(s, size=13.0, bold=False, mono=False):
    if mono:
        return len(s) * size * 0.61
    total = 0.0
    for c in s:
        if c in "iljtfr.,:;'|!()[] ":
            total += 0.31
        elif c in "mwMW@%":
            total += 0.82
        elif c.isupper() or c.isdigit():
            total += 0.61
        else:
            total += 0.53
    return total * size * (1.05 if bold else 1.0)


def wrap(s, max_w, size=13.0, bold=False, mono=False):
    out, cur = [], ""
    for word in str(s).split():
        trial = f"{cur} {word}".strip()
        if cur and text_w(trial, size, bold, mono) > max_w:
            out.append(cur)
            cur = word
        else:
            cur = trial
    return (out + [cur]) if cur else out


def up20(v):
    return int(math.ceil(v / 20.0) * 20)


def attr(s):
    return escape(str(s), quote=True)


def inline(s):
    """The little markdown prose needs: `code` and **bold**."""
    s = escape(str(s), quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)


# ---------------------------------------------------------------- walking the spec

def figures(spec):
    for section in spec.get("sections", []):
        for block in section.get("blocks", []):
            if block.get("type") == "figure":
                yield block


def tables(spec):
    for section in spec.get("sections", []):
        for block in section.get("blocks", []):
            if block.get("type") == "table":
                yield block


def as_member(m):
    return {"text": m} if isinstance(m, str) else m


# ---------------------------------------------------------------- validation

def validate(spec):
    errors, warnings = [], []
    if not spec.get("title"):
        errors.append("spec has no title")
    if not spec.get("sections"):
        errors.append("spec has no sections")
    for si, section in enumerate(spec.get("sections", []), 1):
        where = f"section {si}"
        if not section.get("heading"):
            errors.append(f"{where}: no heading")
        for block in section.get("blocks", []):
            kind = block.get("type")
            if kind == "figure":
                validate_figure(block, errors, warnings)
            elif kind == "table":
                width = len(block.get("headers", []))
                if not width:
                    errors.append(f"{where}: table has no headers")
                for r in block.get("rows", []):
                    cells = r["cells"] if isinstance(r, dict) else r
                    if len(cells) != width:
                        errors.append(f"{where}: table row {cells[:1]} has {len(cells)} cells, headers have {width}")
            elif kind != "p":
                errors.append(f"{where}: unknown block type {kind!r}")
    return errors, warnings


def need_tip(obj, label, errors):
    if not str(obj.get("tip", "")).strip():
        errors.append(f"{label}: no tip (every object needs a tooltip that says more than its label)")
    elif obj.get("title") and str(obj["tip"]).strip().lower() == str(obj["title"]).strip().lower():
        errors.append(f"{label}: tip only repeats the title")


def validate_figure(fig, errors, warnings):
    name = fig.get("title") or fig.get("id") or "untitled figure"
    if not fig.get("title"):
        errors.append("a figure has no title")
    if not fig.get("alt"):
        errors.append(f"figure {name!r}: no alt (a one-sentence summary for screen readers)")
    kind = fig.get("kind")
    if kind == "graph":
        keys = set()
        for n in fig.get("nodes", []):
            label = f"figure {name!r} node {n.get('key')!r}"
            if not n.get("key") or n["key"] in keys:
                errors.append(f"{label}: key missing or repeated")
            keys.add(n.get("key"))
            if n.get("shape", "box") not in SHAPES:
                errors.append(f"{label}: unknown shape {n.get('shape')!r}")
            if n.get("tone", "plain") not in TONES:
                errors.append(f"{label}: unknown tone {n.get('tone')!r}")
            at = n.get("at")
            if not (isinstance(at, list) and len(at) == 2 and all(isinstance(v, int) and v >= 0 for v in at)):
                errors.append(f"{label}: at must be [column, row]")
            if not n.get("title"):
                errors.append(f"{label}: no title")
            need_tip(n, label, errors)
            for group in ("attrs", "methods"):
                for m in n.get(group, []):
                    m = as_member(m)
                    need_tip(m, f"{label} member {m.get('text')!r}", errors)
        spots = {}
        for n in fig.get("nodes", []):
            if isinstance(n.get("at"), list):
                spot = tuple(n["at"])
                if spot in spots:
                    errors.append(f"figure {name!r}: {n.get('key')!r} and {spots[spot]!r} share grid cell {list(spot)}")
                spots[spot] = n.get("key")
        out = {}
        touched = set()
        for e in fig.get("edges", []):
            label = f"figure {name!r} edge {e.get('from')}->{e.get('to')}"
            for end in ("from", "to"):
                if e.get(end) not in keys:
                    errors.append(f"{label}: {end} is not a node key")
                touched.add(e.get(end))
            if e.get("rel", "arrow") not in RELS:
                errors.append(f"{label}: unknown rel {e.get('rel')!r}")
            if e.get("tone", "plain") not in TONES:
                errors.append(f"{label}: unknown tone {e.get('tone')!r}")
            for side in ("from_side", "to_side"):
                if side in e and e[side] not in SIDES:
                    errors.append(f"{label}: {side} must be one of {list(SIDES)}")
            need_tip(e, label, errors)
            out.setdefault(e.get("from"), []).append(e)
        for n in fig.get("nodes", []):
            if n.get("shape") == "decision":
                branches = out.get(n.get("key"), [])
                if len(branches) < 2:
                    errors.append(f"figure {name!r}: decision {n.get('key')!r} has {len(branches)} way out, needs 2 or more")
                if any(not b.get("label") for b in branches):
                    errors.append(f"figure {name!r}: decision {n.get('key')!r} has an unlabeled way out")
            if n.get("key") not in touched:
                warnings.append(f"figure {name!r}: {n.get('key')!r} has no lines")
        for g in fig.get("groups", []):
            label = f"figure {name!r} group {g.get('title')!r}"
            if not g.get("members") or any(m not in keys for m in g.get("members", [])):
                errors.append(f"{label}: members must be node keys")
            need_tip(g, label, errors)
    elif kind == "sequence":
        keys = set()
        for p in fig.get("participants", []):
            label = f"figure {name!r} participant {p.get('key')!r}"
            if not p.get("key") or p["key"] in keys:
                errors.append(f"{label}: key missing or repeated")
            keys.add(p.get("key"))
            need_tip(p, label, errors)
        for s in fig.get("steps", []):
            if "at" in s:
                label = f"figure {name!r} note {s.get('text')!r}"
                if s["at"] not in keys:
                    errors.append(f"{label}: at is not a participant")
                need_tip(s, label, errors)
            else:
                label = f"figure {name!r} message {s.get('label')!r}"
                if s.get("from") not in keys or s.get("to") not in keys:
                    errors.append(f"{label}: from/to must be participants")
                if not s.get("label"):
                    errors.append(f"{label}: no label")
                need_tip(s, label, errors)
    elif kind == "venn":
        sets = fig.get("sets", [])
        keys = [s.get("key") for s in sets]
        if len(sets) not in (2, 3):
            errors.append(f"figure {name!r}: a Venn figure takes 2 or 3 sets, not {len(sets)}; use a table for more")
        if None in keys or len(set(keys)) != len(keys):
            errors.append(f"figure {name!r}: set keys missing or repeated")
        for s in sets:
            label = f"figure {name!r} set {s.get('key')!r}"
            if not s.get("title"):
                errors.append(f"{label}: no title")
            if s.get("tone", "plain") not in TONES:
                errors.append(f"{label}: unknown tone {s.get('tone')!r}")
            need_tip(s, label, errors)
        seen = set()
        for r in fig.get("regions", []):
            where = frozenset(r.get("in", []))
            label = f"figure {name!r} region {sorted(where)}"
            if not where or not where <= set(keys):
                errors.append(f"{label}: in must list set keys")
            if where in seen:
                errors.append(f"{label}: described twice")
            seen.add(where)
            if r.get("items") and r.get("empty"):
                errors.append(f"{label}: has items and empty; choose one")
            elif not r.get("items") and not str(r.get("empty", "")).strip():
                errors.append(f"{label}: no items; if it's empty on purpose, say why in empty")
            if r.get("items"):
                need_tip(r, label, errors)
            for item in r.get("items", []):
                item = as_member(item)
                need_tip(item, f"{label} item {item.get('text')!r}", errors)
        for size in range(1, len(keys) + 1):
            for combo in combinations(keys, size):
                if frozenset(combo) not in seen and None not in keys:
                    errors.append(f"figure {name!r}: region {list(combo)} isn't described; fill it, or mark it empty and say why")
    else:
        errors.append(f"figure {name!r}: kind must be graph, sequence or venn")


# ---------------------------------------------------------------- stable IDs

def assign_ids(spec):
    """Give every object an ID, keeping those it has. Counters outlive deleted objects."""
    counters = spec.setdefault("_id_counters", {})

    def seen(scope, value):
        m = re.fullmatch(r"[A-Za-z]+(\d+)", str(value))
        if m:
            counters[scope] = max(counters.get(scope, 0), int(m.group(1)))

    def give(obj, scope, letter):
        if not obj.get("id"):
            counters[scope] = counters.get(scope, 0) + 1
            obj["id"] = f"{letter}{counters[scope]}"

    # Register everything first, so a new object can't take a number that appears later on.
    for pass_no in (0, 1):
        act = seen if pass_no == 0 else None

        def visit(obj, scope, letter):
            if act:
                if obj.get("id"):
                    act(scope, obj["id"])
            else:
                give(obj, scope, letter)

        for section in spec.get("sections", []):
            visit(section, "S", "S")
            for block in section.get("blocks", []):
                if block.get("type") == "figure":
                    visit(block, "F", "F")
                    if pass_no and not block.get("id"):
                        continue
                elif block.get("type") == "table":
                    visit(block, "T", "T")
        for fig in figures(spec):
            fid = fig.get("id", "?")
            for n in fig.get("nodes", []) + fig.get("participants", []):
                visit(n, f"{fid}.B", "B")
                for group in ("attrs", "methods"):
                    if group in n:
                        n[group] = [as_member(m) for m in n[group]]
                        for m in n[group]:
                            visit(m, f"{fid}.{n.get('id', '?')}.m", "m")
            for g in fig.get("groups", []):
                visit(g, f"{fid}.G", "G")
            for s in fig.get("sets", []):
                visit(s, f"{fid}.V", "V")
            for r in fig.get("regions", []):
                visit(r, f"{fid}.A", "A")
                if "items" in r:
                    r["items"] = [as_member(m) for m in r["items"]]
                    for m in r["items"]:
                        visit(m, f"{fid}.{r.get('id', '?')}.i", "i")
            for e in fig.get("edges", []):
                visit(e, f"{fid}.L", "L")
            for s in fig.get("steps", []):
                if "at" in s:
                    visit(s, f"{fid}.N", "N")
                else:
                    visit(s, f"{fid}.L", "L")
        for table in tables(spec):
            tid = table.get("id", "?")
            rows = [r if isinstance(r, dict) else {"cells": r} for r in table.get("rows", [])]
            table["rows"] = rows
            for r in rows:
                visit(r, f"{tid}.R", "R")


def check_unique(spec, errors):
    seen = set()

    def add(oid):
        if oid in seen:
            errors.append(f"ID {oid} is used twice")
        seen.add(oid)

    for section in spec["sections"]:
        add(section["id"])
    for fig in figures(spec):
        add(fig["id"])
        for n in fig.get("nodes", []) + fig.get("participants", []):
            add(f"{fig['id']}.{n['id']}")
            for group in ("attrs", "methods"):
                for m in n.get(group, []):
                    add(f"{fig['id']}.{n['id']}.{m['id']}")
        for o in fig.get("groups", []) + fig.get("edges", []) + fig.get("steps", []) + fig.get("sets", []):
            add(f"{fig['id']}.{o['id']}")
        for r in fig.get("regions", []):
            add(f"{fig['id']}.{r['id']}")
            for m in r.get("items", []):
                add(f"{fig['id']}.{r['id']}.{m['id']}")
    for table in tables(spec):
        add(table["id"])
        for r in table["rows"]:
            add(f"{table['id']}.{r['id']}")


# ---------------------------------------------------------------- graph layout

BADGE_H = 15
LINE_H = 16


def measure_node(n, box_w, warnings, figname):
    shape = n.get("shape", "box")
    w = up20(n.get("w", box_w))
    title = n["title"]
    if shape == "class":
        rows = [as_member(m)["text"] for m in n.get("attrs", []) + n.get("methods", [])]
        widest = max([text_w(r, 11.5, mono=True) + 34 for r in rows] + [text_w(title, 13.5, True) + 30, 120])
        w = up20(max(n.get("w", 0), widest))
        stereo = 15 if n.get("stereotype") else 0
        n["_head"] = BADGE_H + stereo + 26
        h = n["_head"]
        for items in (n.get("attrs", []), n.get("methods", [])):
            if items:
                h += 18 * len(items) + 8
        n["_title"], n["_lines"] = [title], []
        return w, up20(h)
    if shape == "decision":
        w = up20(n.get("w", box_w * 0.9))
        lines = wrap(title, w * 0.62, 13, True)
        h = 80
        for _ in range(12):
            top = -(len(lines) - 1) * LINE_H / 2
            fits = all(text_w(l, 13, True) + 8 <= w * (1 - 2 * (abs(top + i * LINE_H) + 8) / h)
                       for i, l in enumerate(lines))
            if fits:
                break
            h += 20
        else:
            warnings.append(f"figure {figname!r}: decision {n['key']!r} text does not fit; shorten it or set w")
        n["_title"], n["_lines"] = lines, []
        return w, up20(h)
    inner = w - 20
    titles = wrap(title, inner, 13, True)
    details = []
    for line in n.get("lines", []):
        details += wrap(line, inner, 13)
    for line in titles + details:
        if text_w(line, 13) > inner + 1:
            warnings.append(f"figure {figname!r}: {n['key']!r} has a word too long for the box: {line!r}")
    n["_title"], n["_lines"] = titles, details
    return w, up20(BADGE_H + 6 + (len(titles) + len(details)) * LINE_H + 8)


def layout_nodes(fig, warnings):
    box_w = fig.get("box_w", 220)
    gx, gy = fig.get("gap_x", 120), fig.get("gap_y", 70)
    by_col, by_row = {}, {}
    for n in fig["nodes"]:
        n["_w"], n["_h"] = measure_node(n, box_w, warnings, fig["title"])
        c, r = n["at"]
        span = n.get("span", [1, 1])
        if span[0] == 1:
            by_col[c] = max(by_col.get(c, 0), n["_w"])
        if span[1] == 1:
            by_row[r] = max(by_row.get(r, 0), n["_h"])
    ncols = max(n["at"][0] for n in fig["nodes"]) + 1
    nrows = max(n["at"][1] for n in fig["nodes"]) + 1
    xs, ys = [], []
    x = 40
    for c in range(ncols):
        xs.append(x)
        x += up20(by_col.get(c, 0)) + up20(gx)
    y = 40
    for r in range(nrows):
        ys.append(y)
        y += up20(by_row.get(r, 0)) + up20(gy)
    for n in fig["nodes"]:
        c, r = n["at"]
        span = n.get("span", [1, 1])
        last_c, last_r = c + span[0] - 1, r + span[1] - 1
        cell_w = (xs[min(last_c, ncols - 1)] + up20(by_col.get(min(last_c, ncols - 1), 0))) - xs[c]
        cell_h = (ys[min(last_r, nrows - 1)] + up20(by_row.get(min(last_r, nrows - 1), 0))) - ys[r]
        n["_x"] = xs[c] + up20(max(0, cell_w - n["_w"])) // 2 // GRID * GRID
        n["_y"] = ys[r] + up20(max(0, cell_h - n["_h"])) // 2 // GRID * GRID


def choose_sides(e, a, b):
    if e["from"] == e["to"]:
        return e.get("from_side", "right"), e.get("to_side", "right")
    ac, ar = a["at"]
    bc, br = b["at"]
    if br > ar:
        auto = ("bottom", "top") if abs(bc - ac) <= abs(br - ar) or bc == ac else (("right", "left") if bc > ac else ("left", "right"))
    elif br < ar:
        if bc == ac:  # next door goes straight up; further away has boxes in the way, so it goes around
            auto = ("top", "bottom") if ar - br == 1 else ("left", "left")
        elif abs(bc - ac) >= abs(br - ar):
            auto = ("right", "left") if bc > ac else ("left", "right")
        else:
            auto = ("top", "bottom")
    else:
        auto = ("right", "left") if bc > ac else ("left", "right")
    return e.get("from_side", auto[0]), e.get("to_side", auto[1])


def assign_ports(fig, nodes):
    slots = {}
    for e in fig["edges"]:
        a, b = nodes[e["from"]], nodes[e["to"]]
        e["_fs"], e["_ts"] = choose_sides(e, a, b)
        slots.setdefault((e["from"], e["_fs"]), []).append((e, "from"))
        slots.setdefault((e["to"], e["_ts"]), []).append((e, "to"))
    for (key, side), users in slots.items():
        n = nodes[key]
        horizontal = side in ("top", "bottom")

        def other_pos(item):
            e, end = item
            o = nodes[e["to"] if end == "from" else e["from"]]
            return (o["_x"] + o["_w"] / 2) if horizontal else (o["_y"] + o["_h"] / 2)

        users.sort(key=other_pos)
        tracks = []
        for item in users:
            merge = item[0].get("merge") if item[1] == "to" else None
            if merge and any(t[0] == merge for t in tracks):
                next(t for t in tracks if t[0] == merge)[1].append(item)
            else:
                tracks.append((merge, [item]))
        count = len(tracks)
        length = n["_w"] if horizontal else n["_h"]
        step = 20 if (count - 1) * 20 <= length - 20 else max(10, (length - 20) // max(1, count - 1) // 10 * 10)
        for i, (_, items) in enumerate(tracks):
            offset = 0 if n.get("shape") == "decision" else int((i - (count - 1) / 2) * step / GRID) * GRID
            cx, cy = n["_x"] + n["_w"] // 2, n["_y"] + n["_h"] // 2
            if side == "top":
                port = (cx + offset, n["_y"])
            elif side == "bottom":
                port = (cx + offset, n["_y"] + n["_h"])
            elif side == "left":
                port = (n["_x"], cy + offset)
            else:
                port = (n["_x"] + n["_w"], cy + offset)
            for e, end in items:
                e["_p" + end] = port


def route_all(fig, nodes, warnings):
    margin = 80
    xs = [n["_x"] for n in fig["nodes"]] + [n["_x"] + n["_w"] for n in fig["nodes"]]
    ys = [n["_y"] for n in fig["nodes"]] + [n["_y"] + n["_h"] for n in fig["nodes"]]
    bounds = ((min(xs) - margin) // GRID, (min(ys) - margin) // GRID, (max(xs) + margin) // GRID, (max(ys) + margin) // GRID)
    blocked = set()
    for n in fig["nodes"]:
        for cx in range((n["_x"] - GRID) // GRID, (n["_x"] + n["_w"] + GRID) // GRID + 1):
            for cy in range((n["_y"] - GRID) // GRID, (n["_y"] + n["_h"] + GRID) // GRID + 1):
                blocked.add((cx, cy))
    occupied = {}
    crossings = 0

    def manhattan(e):
        (x1, y1), (x2, y2) = e["_pfrom"], e["_pto"]
        return abs(x1 - x2) + abs(y1 - y2)

    for e in sorted(fig["edges"], key=manhattan):
        cells, crossed = astar(e, blocked, occupied, bounds)
        if cells is None:
            warnings.append(f"figure {fig['title']!r}: no route for {e['id']} ({e['from']} to {e['to']}); open up the grid")
            e["_pts"] = [e["_pfrom"], e["_pto"]]
            continue
        crossings += crossed
        pts = [e["_pfrom"]] + [(x * GRID, y * GRID) for x, y in cells] + [e["_pto"]]
        e["_pts"] = simplify(pts)
        for (x1, y1), (x2, y2) in zip(cells, cells[1:]):
            axis = "h" if y1 == y2 else "v"
            occupied.setdefault((x1, y1), set()).add((axis, e.get("merge") or e["id"]))
            occupied.setdefault((x2, y2), set()).add((axis, e.get("merge") or e["id"]))
    return crossings


def astar(e, blocked, occupied, bounds):
    sx, sy = e["_pfrom"]
    tx, ty = e["_pto"]
    sd, td = SIDES[e["_fs"]], SIDES[e["_ts"]]
    start = ((sx + DIRS[sd][0] * 20) // GRID, (sy + DIRS[sd][1] * 20) // GRID)
    goal = ((tx + DIRS[td][0] * 20) // GRID, (ty + DIRS[td][1] * 20) // GRID)
    # Arriving heading back out of the target would double back over the last stub.
    forbidden_arrival = td
    minx, miny, maxx, maxy = bounds
    heap = [(0, 0, start[0], start[1], sd)]
    cost = {(start[0], start[1], sd): 0}
    came = {}
    counter = 0
    while heap:
        _, _, x, y, d = heapq.heappop(heap)
        state = (x, y, d)
        if (x, y) == goal and d != forbidden_arrival:
            path, crossed = [(x, y)], 0
            while state in came:
                state = came[state]
                path.append((state[0], state[1]))
            path.reverse()
            for before, cell in zip(path, path[1:]):
                axis = "h" if before[1] == cell[1] else "v"
                if any(a != axis and other != e.get("merge") for a, other in occupied.get(cell, ())):
                    crossed += 1
            return path, crossed
        base = cost[(x, y, d)]
        for nd in (d, (d + 1) % 4, (d + 3) % 4):
            nx, ny = x + DIRS[nd][0], y + DIRS[nd][1]
            if not (minx <= nx <= maxx and miny <= ny <= maxy):
                continue
            if (nx, ny) in blocked and (nx, ny) not in (start, goal):
                continue
            axis = "h" if DIRS[nd][1] == 0 else "v"
            step = 1 + (7 if nd != d else 0)
            for other_axis, other_id in occupied.get((nx, ny), ()):
                if other_id == e.get("merge"):
                    step -= 0.5 if other_axis == axis else 0
                else:
                    step += 40 if other_axis == axis else 14
            new = base + step
            key = (nx, ny, nd)
            if new < cost.get(key, 10 ** 9):
                cost[key] = new
                came[key] = (x, y, d)
                counter += 1
                heapq.heappush(heap, (new + abs(nx - goal[0]) + abs(ny - goal[1]), counter, nx, ny, nd))
    return None, 0


def simplify(pts):
    out = []
    for p in pts:
        if out and out[-1] == p:
            continue
        if len(out) >= 2:
            (x1, y1), (x2, y2) = out[-2], out[-1]
            if (x1 == x2 == p[0]) or (y1 == y2 == p[1]):
                out[-1] = p
                continue
        out.append(p)
    return out


def rects_hit(a, b, pad=0):
    return not (a[0] + a[2] + pad <= b[0] or b[0] + b[2] + pad <= a[0]
                or a[1] + a[3] + pad <= b[1] or b[1] + b[3] + pad <= a[1])


def seg_hits_rect(p, q, r):
    box = (min(p[0], q[0]) - 1, min(p[1], q[1]) - 1, abs(p[0] - q[0]) + 2, abs(p[1] - q[1]) + 2)
    return rects_hit(box, r)


def label_block(full_id, label):
    lines = wrap(label, 170, 12.5) if label else []
    w = max([text_w(full_id, 9.5, mono=True)] + [text_w(l, 12.5) for l in lines]) + 8
    return lines, math.ceil(w), BADGE_H - 2 + len(lines) * 15 + 3


def place_labels(fig, nodes, warnings):
    fid = fig["id"]
    hard = [(n["_x"], n["_y"], n["_w"], n["_h"]) for n in fig["nodes"]]
    hard += [g["_title_rect"] for g in fig.get("groups", [])]
    all_segs = [(e, p, q) for e in fig["edges"] for p, q in zip(e["_pts"], e["_pts"][1:])]
    placed = []
    hits = 0
    ordered = sorted(fig["edges"], key=lambda e: 0 if nodes[e["from"]].get("shape") == "decision" else 1)
    for e in ordered:
        lines, w, h = label_block(f"{fid}.{e['id']}", e.get("label"))
        e["_lab_lines"] = lines
        segs = list(zip(e["_pts"], e["_pts"][1:]))
        near_from = e.get("label_near") == "from" or nodes[e["from"]].get("shape") == "decision"
        order = list(range(len(segs))) if near_from else sorted(range(len(segs)), key=lambda i: -(abs(segs[i][0][0] - segs[i][1][0]) + abs(segs[i][0][1] - segs[i][1][1])))
        best, best_score = None, 10 ** 9
        for rank, i in enumerate(order):
            p, q = segs[i]
            vertical = p[0] == q[0]
            fractions = (0.5, 0.3, 0.7, 0.15, 0.85) if not near_from else (0.3, 0.15, 0.5, 0.7)
            for fi, t in enumerate(fractions):
                mx, my = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
                for side in (1, -1):
                    if vertical:
                        rect = (mx + 6 if side > 0 else mx - 6 - w, my - h / 2, w, h)
                    else:
                        rect = (mx - w / 2, my - 4 - h if side > 0 else my + 4, w, h)
                    score = rank * 6 + fi * 2 + (0 if side > 0 else 1)
                    if any(rects_hit(rect, o, 2) for o in hard):
                        score += 5000
                    if any(rects_hit(rect, o, 2) for o in placed):
                        score += 5000
                    score += 30 * sum(1 for other, a, b in all_segs if seg_hits_rect(a, b, rect))
                    if score < best_score:
                        best, best_score = rect, score
        if best_score >= 5000:
            hits += 1
            warnings.append(f"figure {fig['title']!r}: label of {fid}.{e['id']} touches a box or another label")
        e["_lab"] = best
        placed.append(best)
    return hits


# ---------------------------------------------------------------- SVG

def markers(fid):
    out = []
    for tone in TONES:
        out.append(f'<marker id="{fid}-a-{tone}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path class="mk-{tone}" d="M0 0L10 5L0 10z"/></marker>')
    tri = '<path class="mk-hollow" d="M1 1L13 7L1 13z"/>'
    out.append(f'<marker id="{fid}-tri" viewBox="0 0 14 14" refX="13" refY="7" markerWidth="11" markerHeight="11" orient="auto-start-reverse">{tri}</marker>')
    out.append(f'<marker id="{fid}-dia-f" viewBox="0 0 16 10" refX="1" refY="5" markerWidth="13" markerHeight="9" orient="auto-start-reverse"><path class="mk-plain" d="M1 5L8 1L15 5L8 9z"/></marker>')
    out.append(f'<marker id="{fid}-dia-h" viewBox="0 0 16 10" refX="1" refY="5" markerWidth="13" markerHeight="9" orient="auto-start-reverse"><path class="mk-hollow" d="M1 5L8 1L15 5L8 9z"/></marker>')
    out.append(f'<marker id="{fid}-open" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path class="mk-open" d="M1 1L9 5L1 9"/></marker>')
    return "<defs>" + "".join(out) + "</defs>"


def obj_open(cls, oid, aria):
    return f'<g class="obj {cls}" data-oid="{attr(oid)}" tabindex="0" role="button" aria-label="{attr(aria)}">'


def svg_lines(lines, cx, first_y, bold_count=0):
    out = []
    for i, line in enumerate(lines):
        cls = "t b" if i < bold_count else "t"
        out.append(f'<text class="{cls}" x="{cx}" y="{first_y + i * LINE_H}" text-anchor="middle">{escape(line)}</text>')
    return "".join(out)


def svg_node(n, fid, register):
    x, y, w, h = n["_x"], n["_y"], n["_w"], n["_h"]
    shape = n.get("shape", "box")
    oid = f"{fid}.{n['id']}"
    tone = n.get("tone", "plain")
    register(oid, "box" if shape != "class" else "class", n["title"], n["tip"], n.get("source"), fig=fid)
    out = [obj_open(f"node tone-{tone}", oid, f"{oid} {n['title']}")]
    cx = x + w / 2
    if shape == "decision":
        out.append(f'<polygon class="shape" points="{cx},{y} {x + w},{y + h / 2} {cx},{y + h} {x},{y + h / 2}"/>')
        out.append(f'<text class="bdg" x="{x}" y="{y + 10}">{oid}</text>')
        lines = n["_title"]
        out.append(svg_lines(lines, cx, y + h / 2 - (len(lines) - 1) * LINE_H / 2 + 4.5, len(lines)))
    elif shape == "class":
        head = n["_head"]
        out.append(f'<rect class="shape" x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>')
        out.append(f'<text class="bdg" x="{x + 7}" y="{y + 13}">{oid}</text>')
        ty = y + BADGE_H + 6
        if n.get("stereotype"):
            out.append(f'<text class="st" x="{cx}" y="{ty + 6}" text-anchor="middle">«{escape(n["stereotype"])}»</text>')
            ty += 15
        out.append(f'<text class="t b ttl" x="{cx}" y="{ty + 9}" text-anchor="middle">{escape(n["title"])}</text>')
        attrs = n.get("attrs", [])
        if attrs or n.get("methods"):
            out.append(f'<line class="rule" x1="{x}" x2="{x + w}" y1="{y + head}" y2="{y + head}"/>')
        ry = y + head + 4
        for group, items in (("attribute", attrs), ("method", n.get("methods", []))):
            for m in items:
                mid = f"{oid}.{m['id']}"
                register(mid, group, m["text"], m["tip"], m.get("source"), fig=fid)
                out.append(f'<g class="obj member" data-oid="{attr(mid)}" tabindex="0" role="button" aria-label="{attr(mid + " " + m["text"])}">')
                out.append(f'<rect class="mhit" x="{x + 1}" y="{ry}" width="{w - 2}" height="18"/>')
                out.append(f'<text class="m" x="{x + 8}" y="{ry + 13}">{escape(m["text"])}</text></g>')
                ry += 18
            if group == "attribute" and attrs and n.get("methods"):
                ry += 4
                out.append(f'<line class="rule" x1="{x}" x2="{x + w}" y1="{ry}" y2="{ry}"/>')
                ry += 4
    else:
        rx = {"state": 16, "terminal": h / 2}.get(shape, 4)
        out.append(f'<rect class="shape" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>')
        if shape == "terminal":  # a pill's corner is curved away, so its ID sits top center
            out.append(f'<text class="bdg" x="{cx}" y="{y + 13}" text-anchor="middle">{oid}</text>')
        else:
            out.append(f'<text class="bdg" x="{x + (12 if rx > 4 else 7)}" y="{y + 13}">{oid}</text>')
        titles, details = n["_title"], n["_lines"]
        body_top = y + BADGE_H + 6
        out.append(svg_lines(titles + details, cx, body_top + 10, len(titles)))
    out.append("</g>")
    return "".join(out)


def svg_edge(e, fid, register, nodes):
    oid = f"{fid}.{e['id']}"
    tone = e.get("tone", "plain")
    rel = e.get("rel", "arrow")
    pts = " ".join(f"{x},{y}" for x, y in e["_pts"])
    a, b = nodes[e["from"]], nodes[e["to"]]
    register(oid, "line", e.get("label") or f"{a['title']} to {b['title']}", e["tip"], e.get("source"),
             fig=fid, frm=f"{fid}.{a['id']}", to=f"{fid}.{b['id']}", rel=rel if rel != "arrow" else None)
    dash = " dash" if e.get("dash") or rel in ("implements", "depends") else ""
    mark = {
        "arrow": f'marker-end="url(#{fid}-a-{tone})"',
        "none": "",
        "inherits": f'marker-end="url(#{fid}-tri)"',
        "implements": f'marker-end="url(#{fid}-tri)"',
        "composes": f'marker-start="url(#{fid}-dia-f)" marker-end="url(#{fid}-open)"',
        "aggregates": f'marker-start="url(#{fid}-dia-h)" marker-end="url(#{fid}-open)"',
        "depends": f'marker-end="url(#{fid}-open)"',
    }[rel]
    out = [obj_open(f"line tone-{tone}", oid, f"{oid} {e.get('label', '')} from {a['title']} to {b['title']}")]
    out.append(f'<polyline class="hit" points="{pts}" fill="none"/>')
    out.append(f'<polyline class="ln{dash}" points="{pts}" fill="none" {mark}/>')
    out.append(label_svg(e["_lab"], oid, e["_lab_lines"]))
    out.append("</g>")
    return "".join(out)


def label_svg(rect, oid, lines, centered=False):
    x, y, w, h = rect
    tx = x + w / 2 if centered else x + 4
    anchor = ' text-anchor="middle"' if centered else ""
    out = [f'<rect class="labbg" x="{x}" y="{y}" width="{w}" height="{h}" rx="2"/>']
    out.append(f'<text class="bdg"{anchor} x="{tx}" y="{y + 10}">{oid}</text>')
    for i, line in enumerate(lines):
        out.append(f'<text class="l"{anchor} x="{tx}" y="{y + 10 + 14 + i * 15}">{escape(line)}</text>')
    return "".join(out)


def svg_wrap(fig, body, minx, miny, maxx, maxy):
    w, h = maxx - minx, maxy - miny
    return (f'<div class="scroll"><svg viewBox="{minx} {miny} {w} {h}" style="min-width:{min(w, 720)}px;max-width:{w}px" '
            f'role="group" aria-label="{attr(fig["alt"])}">{markers(fig["id"])}{body}</svg></div>')


def render_graph(fig, register, warnings, stats):
    fid = fig["id"]
    nodes = {n["key"]: n for n in fig["nodes"]}
    layout_nodes(fig, warnings)
    for g in fig.get("groups", []):
        members = [nodes[m] for m in g["members"]]
        pad = 20
        gx1 = min(n["_x"] for n in members) - pad
        gy1 = min(n["_y"] for n in members) - pad - 16
        gx2 = max(n["_x"] + n["_w"] for n in members) + pad
        gy2 = max(n["_y"] + n["_h"] for n in members) + pad
        g["_r"] = (gx1, gy1, gx2 - gx1, gy2 - gy1)
        full = f"{fid}.{g['id']}"
        g["_title_rect"] = (gx1 + 6, gy1 + 2, text_w(full, 9.5, mono=True) + text_w(g["title"], 12.5, True) + 16, 18)
    assign_ports(fig, nodes)
    stats["crossings"] += route_all(fig, nodes, warnings)
    stats["label_hits"] += place_labels(fig, nodes, warnings)

    body = []
    for g in fig.get("groups", []):
        x, y, w, h = g["_r"]
        oid = f"{fid}.{g['id']}"
        register(oid, "group", g["title"], g["tip"], g.get("source"), fig=fid)
        body.append(obj_open("group", oid, f"{oid} {g['title']}"))
        body.append(f'<rect class="grp" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>')
        body.append(f'<text class="bdg" x="{x + 8}" y="{y + 15}">{oid}</text>')
        body.append(f'<text class="l b" x="{x + 12 + text_w(oid, 9.5, mono=True)}" y="{y + 15}">{escape(g["title"])}</text></g>')
    for n in fig["nodes"]:
        body.append(svg_node(n, fid, register))
    for e in fig["edges"]:
        body.append(svg_edge(e, fid, register, nodes))

    xs, ys = [], []
    for n in fig["nodes"]:
        xs += [n["_x"], n["_x"] + n["_w"]]
        ys += [n["_y"], n["_y"] + n["_h"]]
    for e in fig["edges"]:
        xs += [p[0] for p in e["_pts"]] + [e["_lab"][0], e["_lab"][0] + e["_lab"][2]]
        ys += [p[1] for p in e["_pts"]] + [e["_lab"][1], e["_lab"][1] + e["_lab"][3]]
    for g in fig.get("groups", []):
        xs += [g["_r"][0], g["_r"][0] + g["_r"][2]]
        ys += [g["_r"][1], g["_r"][1] + g["_r"][3]]
    return svg_wrap(fig, "".join(body), int(min(xs)) - 12, int(min(ys)) - 12, int(max(xs)) + 12, int(max(ys)) + 12)


def render_sequence(fig, register, warnings, stats):
    fid = fig["id"]
    parts = fig["participants"]
    box_w = fig.get("box_w", 170)
    index = {p["key"]: i for i, p in enumerate(parts)}
    head_h = 0
    for p in parts:
        p["_w"], p["_h"] = measure_node({**p, "shape": "box", "key": p["key"]}, box_w, warnings, fig["title"])
        p["_title"] = wrap(p["title"], p["_w"] - 20, 13, True)
        p["_lines"] = [w for line in p.get("lines", []) for w in wrap(line, p["_w"] - 20, 13)]
        head_h = max(head_h, p["_h"])
    gaps = [up20(max(fig.get("gap_x", 60) + (parts[i]["_w"] + parts[i + 1]["_w"]) / 2, 200)) for i in range(len(parts) - 1)]
    for s in fig.get("steps", []):
        if "at" in s or s["from"] == s["to"]:
            continue
        i, j = sorted((index[s["from"]], index[s["to"]]))
        lines = wrap(s["label"], 230, 12.5)
        need = max([text_w(l, 12.5) for l in lines] + [text_w(f"{fid}.{s['id']}", 9.5, mono=True)]) + 50
        have = sum(gaps[i:j])
        if have < need:
            gaps[j - 1] += up20(need - have)
    centers = [40 + parts[0]["_w"] // 2]
    for g in gaps:
        centers.append(centers[-1] + g)
    y = 40 + head_h + 26
    rows = []
    for s in fig.get("steps", []):
        if "at" in s:
            full = f"{fid}.{s['id']}"
            w = s.get("w", 170)
            lines = wrap(s["text"], w - 16, 13)
            s["_lines"] = lines
            h = BADGE_H + 4 + len(lines) * LINE_H + 6
            s["_w"], s["_h"] = w, h
            if s.get("with_prev") and rows and rows[-1]["kind"] == "note":
                rows[-1]["notes"].append(s)
                rows[-1]["h"] = max(rows[-1]["h"], h)
            else:
                rows.append({"kind": "note", "notes": [s], "h": h})
        else:
            lines = wrap(s["label"], 230, 12.5)
            s["_lines"] = lines
            rows.append({"kind": "msg", "msg": s, "h": BADGE_H - 2 + len(lines) * 15 + 12 + (24 if s["from"] == s["to"] else 0)})
    positions = []
    for row in rows:
        positions.append(y)
        y += row["h"] + 18
    bottom = y
    body = []
    for i, p in enumerate(parts):
        x = centers[i] - p["_w"] // 2
        oid = f"{fid}.{p['id']}"
        tone = p.get("tone", "plain")
        register(oid, "box", p["title"], p["tip"], p.get("source"), fig=fid)
        body.append(obj_open(f"node tone-{tone}", oid, f"{oid} {p['title']}"))
        body.append(f'<line class="life" x1="{centers[i]}" x2="{centers[i]}" y1="{40 + head_h}" y2="{bottom}"/>')
        body.append(f'<line class="hit" x1="{centers[i]}" x2="{centers[i]}" y1="{40 + head_h}" y2="{bottom}"/>')
        body.append(f'<rect class="shape" x="{x}" y="40" width="{p["_w"]}" height="{head_h}" rx="4"/>')
        body.append(f'<text class="bdg" x="{x + 7}" y="53">{oid}</text>')
        body.append(svg_lines(p["_title"] + p["_lines"], centers[i], 40 + BADGE_H + 16, len(p["_title"])))
        body.append("</g>")
    maxx = centers[-1] + parts[-1]["_w"] // 2
    for row, ry in zip(rows, positions):
        if row["kind"] == "note":
            for s in row["notes"]:
                oid = f"{fid}.{s['id']}"
                tone = s.get("tone", "plain")
                register(oid, "note", s["text"], s["tip"], s.get("source"), fig=fid)
                cx = centers[index[s["at"]]]
                x = cx - s["_w"] // 2
                body.append(obj_open(f"node note tone-{tone}", oid, f"{oid} {s['text']}"))
                body.append(f'<rect class="shape" x="{x}" y="{ry}" width="{s["_w"]}" height="{s["_h"]}" rx="3"/>')
                body.append(f'<text class="bdg" x="{x + 7}" y="{ry + 13}">{oid}</text>')
                body.append(svg_lines(s["_lines"], cx, ry + BADGE_H + 14))
                body.append("</g>")
                maxx = max(maxx, x + s["_w"])
            continue
        s = row["msg"]
        oid = f"{fid}.{s['id']}"
        tone = s.get("tone", "plain")
        i, j = index[s["from"]], index[s["to"]]
        register(oid, "line", s["label"], s["tip"], s.get("source"), fig=fid,
                 frm=f"{fid}.{parts[i]['id']}", to=f"{fid}.{parts[j]['id']}")
        block_h = BADGE_H - 2 + len(s["_lines"]) * 15 + 3
        ly = ry + block_h + 4
        dash = " dash" if s.get("dash") else ""
        body.append(obj_open(f"line tone-{tone}", oid, f"{oid} {s['label']}"))
        if i == j:
            pts = f"{centers[i]},{ly} {centers[i] + 40},{ly} {centers[i] + 40},{ly + 22} {centers[i] + 2},{ly + 22}"
            w = max([text_w(l, 12.5) for l in s["_lines"]] + [text_w(oid, 9.5, mono=True)]) + 8
            lab = (centers[i] + 46, ly - 4, w, block_h)
            maxx = max(maxx, lab[0] + w)
            centered = False
        else:
            x1, x2 = centers[i], centers[j]
            end = x2 - 2 if x2 > x1 else x2 + 2
            pts = f"{x1},{ly} {end},{ly}"
            w = max([text_w(l, 12.5) for l in s["_lines"]] + [text_w(oid, 9.5, mono=True)]) + 8
            lab = ((x1 + x2) / 2 - w / 2, ry, w, block_h)
            centered = True
        body.append(f'<polyline class="hit" points="{pts}" fill="none"/>')
        body.append(f'<polyline class="ln{dash}" points="{pts}" fill="none" marker-end="url(#{fid}-a-{tone})"/>')
        body.append(label_svg(lab, oid, s["_lines"], centered))
        body.append("</g>")
    return svg_wrap(fig, "".join(body), 20, 28, int(maxx) + 20, bottom + 12)


# ---------------------------------------------------------------- Venn

def venn_centers(count, r):
    d = r * 1.1
    if count == 2:
        return [(-d / 2, 0.0), (d / 2, 0.0)]
    return [(-d / 2, 0.0), (d / 2, 0.0), (0.0, d * 0.866)]


def region_margin(x, y, inside, outside, centers, r):
    """How far a point is inside its region; negative when it's out."""
    margins = [r - math.hypot(x - centers[i][0], y - centers[i][1]) for i in inside]
    margins += [math.hypot(x - centers[i][0], y - centers[i][1]) - r for i in outside]
    return min(margins)


def block_lines(fid, region, width):
    """A region's text at one wrap width: (item or None, lines) groups, plus its size."""
    groups = []
    if region.get("empty"):
        groups.append((None, wrap("Empty on purpose", width, 12.5)))
    for item in region.get("items", []):
        groups.append((item, wrap(item["text"], width, 12.5)))
    lines = [l for _, ls in groups for l in ls]
    badge = f"{fid}.{region['id']}"
    w = max([text_w(l, 12.5) for l in lines] + [text_w(badge, 9.5, mono=True)]) + 6
    h = 14 + len(lines) * 15 + 3 * max(0, len(groups) - 1) + 4
    return groups, w, h


def fit_block(w, h, inside, outside, centers, r):
    """The spot where a w by h block sits deepest in its region, and how deep that is."""
    xs = [centers[i][0] for i in inside]
    ys = [centers[i][1] for i in inside]
    best, best_margin = (min(xs), min(ys)), -10 ** 9
    for gx in range(int(min(xs) - r), int(max(xs) + r) + 1, 8):
        for gy in range(int(min(ys) - r), int(max(ys) + r) + 1, 8):
            margin = 10 ** 9
            for fx in (-0.5, -0.25, 0, 0.25, 0.5):
                for fy in (-0.5, 0, 0.5):
                    margin = min(margin, region_margin(gx + fx * w, gy + fy * h, inside, outside, centers, r))
                    if margin <= best_margin:
                        break
                if margin <= best_margin:
                    break
            if margin > best_margin:
                best, best_margin = (gx, gy), margin
    return best, best_margin


def layout_venn(fig, warnings):
    fid = fig["id"]
    index = {s["key"]: i for i, s in enumerate(fig["sets"])}
    count = len(fig["sets"])
    wanted = 6
    for r in range(180, 500, 20):
        centers = venn_centers(count, r)
        worst = 10 ** 9
        for region in fig["regions"]:
            inside = [index[k] for k in region["in"]]
            outside = [i for i in range(count) if i not in inside]
            best = None
            for width in (240, 200, 170, 140, 110, 90):
                groups, w, h = block_lines(fid, region, width)
                spot, margin = fit_block(w, h, inside, outside, centers, r)
                if best is None or margin > best["margin"]:
                    best = {"groups": groups, "w": w, "h": h, "spot": spot, "margin": margin}
                if margin >= wanted + 14:
                    break
            region["_fit"], region["_in"], region["_out"] = best, inside, outside
            worst = min(worst, best["margin"])
        if worst >= wanted:
            break
    else:
        warnings.append(f"figure {fig['title']!r}: a region's text doesn't fit; shorten it, or use a table")
    return centers, r


def probe_point(region, centers, r):
    """A point in the region clear of its text, so a check can prove hovering the bare area works."""
    fit = region["_fit"]
    cx, cy = fit["spot"]
    best, best_margin = (cx, cy), -10 ** 9
    for gx in range(int(min(c[0] for c in centers) - r), int(max(c[0] for c in centers) + r) + 1, 6):
        for gy in range(int(min(c[1] for c in centers) - r), int(max(c[1] for c in centers) + r) + 1, 6):
            if abs(gx - cx) <= fit["w"] / 2 + 3 and abs(gy - cy) <= fit["h"] / 2 + 3:
                continue
            margin = region_margin(gx, gy, region["_in"], region["_out"], centers, r)
            if margin > best_margin:
                best, best_margin = (gx, gy), margin
    return best


def render_venn(fig, register, warnings, stats):
    fid = fig["id"]
    centers, r = layout_venn(fig, warnings)
    sets = fig["sets"]
    span = r * 3 + 400
    defs = []
    for i, (cx, cy) in enumerate(centers):
        defs.append(f'<clipPath id="{fid}-in{i}"><circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath>')
        ring = (f"M{-span} {-span}H{span}V{span}H{-span}Z"
                f"M{cx - r} {cy}a{r} {r} 0 1 0 {2 * r} 0a{r} {r} 0 1 0 {-2 * r} 0Z")
        defs.append(f'<clipPath id="{fid}-out{i}"><path clip-rule="evenodd" d="{ring}"/></clipPath>')
    body = ["<defs>" + "".join(defs) + "</defs>"]
    for i, s in enumerate(sets):
        oid = f"{fid}.{s['id']}"
        cx, cy = centers[i]
        register(oid, "set", s["title"], s["tip"], s.get("source"), fig=fid)
        lines = wrap(s["title"], 2 * r * 0.8, 15, True)
        below = i == 2
        ty = cy + r + 26 if below else cy - r - 12 - (len(lines) - 1) * 18
        body.append(obj_open(f"vset tone-{s.get('tone', 'plain')}", oid, f"{oid} {s['title']}"))
        body.append(f'<circle class="shape" cx="{cx}" cy="{cy}" r="{r}"/>')
        badge_y = ty + (len(lines) - 1) * 18 + 15 if below else ty - 18
        body.append(f'<text class="bdg" x="{cx}" y="{badge_y}" text-anchor="middle">{oid}</text>')
        for j, line in enumerate(lines):
            body.append(f'<text class="t b vname" x="{cx}" y="{ty + j * 18}" text-anchor="middle">{escape(line)}</text>')
        body.append("</g>")
    set_ids = {s["key"]: f"{fid}.{s['id']}" for s in sets}
    for region in fig["regions"]:
        oid = f"{fid}.{region['id']}"
        names = [next(s["title"] for s in sets if s["key"] == k) for k in region["in"]]
        title = " and ".join(names) + (" only" if len(names) < len(sets) else "")
        register(oid, "region", title, region.get("empty") or region["tip"], region.get("source"), fig=fid,
                 members=[set_ids[k] for k in region["in"]])
        fit = region["_fit"]
        px, py = probe_point(region, centers, r)
        extra = f' data-probe="{px},{py}"'
        body.append(obj_open("region", oid, f"{oid} {title}").replace(">", extra + ">", 1))
        opened = ""
        for i in region["_in"]:
            opened += f'<g clip-path="url(#{fid}-in{i})">'
        for i in region["_out"]:
            opened += f'<g clip-path="url(#{fid}-out{i})">'
        depth = len(region["_in"]) + len(region["_out"])
        body.append(f'{opened}<rect class="vhit" x="{-span}" y="{-span}" width="{2 * span}" height="{2 * span}"/>{"</g>" * depth}')
        cx, cy = fit["spot"]
        y = cy - fit["h"] / 2
        body.append(f'<text class="bdg" x="{cx}" y="{y + 10}" text-anchor="middle">{oid}</text>')
        y += 14
        for item, lines in fit["groups"]:
            if item is None:
                for line in lines:
                    y += 15
                    body.append(f'<text class="l vempty" x="{cx}" y="{y - 3}" text-anchor="middle">{escape(line)}</text>')
                continue
            iid = f"{oid}.{item['id']}"
            register(iid, "item", item["text"], item["tip"], item.get("source"), fig=fid)
            body.append(f'<g class="obj member" data-oid="{attr(iid)}" tabindex="0" role="button" aria-label="{attr(iid + " " + item["text"])}">')
            body.append(f'<rect class="mhit" x="{cx - fit["w"] / 2}" y="{y}" width="{fit["w"]}" height="{len(lines) * 15}"/>')
            for line in lines:
                y += 15
                body.append(f'<text class="t" x="{cx}" y="{y - 3}" text-anchor="middle">{escape(line)}</text>')
            body.append("</g>")
            y += 3
        body.append("</g>")
    xs = [c[0] for c in centers]
    ys = [c[1] for c in centers]
    minx, maxx = min(xs) - r - 14, max(xs) + r + 14
    miny, maxy = min(ys) - r - 56, max(ys) + r + 56
    return svg_wrap(fig, "".join(body), int(minx), int(miny), int(maxx), int(maxy))


# ---------------------------------------------------------------- page

SWATCH_TEXT = {"plain": "Normal", "hub": "Hub", "attention": "Attention", "hold": "Holding", "good": "Success", "danger": "Failure", "muted": "Background"}


def render_legend(fig):
    legend = fig.get("legend")
    if not legend:
        return ""
    items = "".join(
        f'<span class="lg"><i class="sw tone-{t}"></i>{escape(text)}</span>' for t, text in legend.items())
    return f'<div class="legend">{items}</div>'


def render_index(scope_id, label, register_list):
    rows = "".join(
        f'<tr><td><button class="chip" data-copy="{attr(oid)}">{escape(oid)}</button></td>'
        f'<td>{escape(kind)}</td><td>{escape(title)}</td></tr>'
        for oid, kind, title in register_list)
    return (f'<details class="index"><summary>All objects in {escape(label)} ({len(register_list)})</summary>'
            f'<div class="table"><table><thead><tr><th>ID</th><th>Type</th><th>Name</th></tr></thead><tbody>{rows}</tbody></table></div></details>')


def render_page(spec, warnings, stats):
    objects = {}

    def register(oid, kind, title, tip="", source=None, fig=None, frm=None, to=None, rel=None, members=None):
        entry = {"k": kind, "t": title}
        if tip:
            entry["d"] = tip
        if source:
            entry["s"] = source
        if fig:
            entry["g"] = fig
        if frm:
            entry["f"] = frm
        if to:
            entry["o"] = to
        if rel:
            entry["r"] = rel
        if members:
            entry["m"] = members
        objects[oid] = entry

    main = [f'<section class="intro"><h1>{escape(spec["title"])}</h1>']
    if spec.get("lead"):
        main.append(f'<p class="lead">{inline(spec["lead"])}</p>')
    if spec.get("status"):
        main.append(f'<p class="status">{inline(spec["status"])}</p>')
    main.append("</section>")

    for section in spec["sections"]:
        sid = section["id"]
        register(sid, "section", section["heading"])
        main.append(f'<section id="{attr(sid)}"><h2><button class="chip" data-copy="{attr(sid)}">{sid}</button> {escape(section["heading"])}</h2>')
        for block in section.get("blocks", []):
            kind = block.get("type")
            if kind == "p":
                main.append(f'<p>{inline(block["text"])}</p>')
            elif kind == "figure":
                main.append(render_figure(block, register, objects, warnings, stats))
            elif kind == "table":
                main.append(render_table(block, register, objects))
        main.append("</section>")

    css = (ASSETS / "page.css").read_text(encoding="utf-8")
    js = (ASSETS / "page.js").read_text(encoding="utf-8")
    data = json.dumps({"title": spec["title"], "objects": objects}, ensure_ascii=False).replace("</", "<\\/")
    toolbar = (
        '<div class="toolbar" role="toolbar" aria-label="Working with object IDs">'
        '<label class="tgl"><input type="checkbox" id="showids" checked> Show IDs</label>'
        '<label class="tgl"><input type="checkbox" id="many"> Collect several</label>'
        '<form id="find"><input id="findbox" type="search" placeholder="Find an ID, like F2.B7" aria-label="Find an object by ID" autocomplete="off"></form>'
        '<button id="copyall" class="btn" type="button">Copy all IDs</button>'
        '</div>')
    tray = ('<div class="tray" id="tray" hidden><span id="traytext"></span>'
            '<button class="btn" id="traycopy" type="button">Copy</button><button class="btn" id="trayclear" type="button">Clear</button></div>')
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{escape(spec.get("short_title", spec["title"]))}</title>'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600&family=Source+Sans+3:wght@400;600&family=JetBrains+Mono:wght@400&display=swap">'
        f'<style>{css}</style></head><body>{toolbar}<main>{"".join(main)}</main>{tray}'
        '<div class="tip" id="tip" role="tooltip" hidden></div><div class="toast" id="toast" role="status" aria-live="polite"></div>'
        f'<script type="application/json" id="objdata">{data}</script><script>{js}</script></body></html>\n')


def scope_list(prefix, objects):
    return [(oid, o["k"], o["t"]) for oid, o in objects.items() if oid == prefix or oid.startswith(prefix + ".")]


def render_figure(fig, register, objects, warnings, stats):
    fid = fig["id"]
    title = fig["title"]
    register(fid, "figure", title, fig["alt"])
    draw = {"graph": render_graph, "sequence": render_sequence, "venn": render_venn}[fig["kind"]]
    svg = draw(fig, register, warnings, stats)
    listing = scope_list(fid, objects)
    caption = f'<figcaption>{inline(fig["caption"])}</figcaption>' if fig.get("caption") else ""
    return (f'<figure id="{attr(fid)}" data-oid="{attr(fid)}"><div class="fighead"><button class="chip" data-copy="{attr(fid)}">{fid}</button>'
            f'<span class="figtitle">{escape(title)}</span><button class="btn small" data-copy-scope="{attr(fid)}" type="button">Copy all in {fid}</button></div>'
            f'{svg}{render_legend(fig)}{caption}{render_index(fid, fid, listing)}</figure>')


def render_table(table, register, objects):
    tid = table["id"]
    title = table.get("title", "")
    register(tid, "table", title or " / ".join(table["headers"]))
    head = "".join(f"<th>{escape(h)}</th>" for h in table["headers"])
    rows = []
    for r in table["rows"]:
        oid = f"{tid}.{r['id']}"
        register(oid, "row", " | ".join(str(c) for c in r["cells"]), r.get("tip", ""), r.get("source"), fig=tid)
        cells = "".join(f"<td>{inline(c)}</td>" for c in r["cells"])
        rows.append(f'<tr data-oid="{attr(oid)}" tabindex="0"><td class="idcell"><button class="chip" data-copy="{attr(oid)}">{oid}</button></td>{cells}</tr>')
    return (f'<div class="tablewrap" id="{attr(tid)}"><div class="fighead"><button class="chip" data-copy="{attr(tid)}">{tid}</button>'
            f'<span class="figtitle">{escape(title)}</span><button class="btn small" data-copy-scope="{attr(tid)}" type="button">Copy all in {tid}</button></div>'
            f'<div class="table"><table><thead><tr><th class="idh">ID</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div></div>')


# ---------------------------------------------------------------- source checks

def walk_sources(spec):
    for fig in figures(spec):
        for group in ("nodes", "participants", "edges", "steps", "groups", "sets", "regions"):
            for o in fig.get(group, []):
                if o.get("source"):
                    yield f"{fig['id']}.{o['id']}", o["source"]
                for mg in ("attrs", "methods", "items"):
                    for m in o.get(mg, []):
                        if isinstance(m, dict) and m.get("source"):
                            yield f"{fig['id']}.{o['id']}.{m['id']}", m["source"]
    for table in tables(spec):
        for r in table["rows"]:
            if r.get("source"):
                yield f"{table['id']}.{r['id']}", r["source"]


def check_sources(spec, root):
    """A source is `path` or `path#text`. The text has to still be in the file, so a changed timer or a
    renamed function shows up here instead of quietly leaving the chart wrong."""
    problems, total = [], 0
    for oid, source in walk_sources(spec):
        total += 1
        path, _, needle = source.partition("#")
        target = Path(root) / path
        if not target.is_file():
            problems.append(f"{oid}: file not found: {path}")
            continue
        if needle and needle not in target.read_text(encoding="utf-8", errors="replace"):
            problems.append(f"{oid}: {path} no longer contains {needle!r}")
    return total, problems


# ---------------------------------------------------------------- command line

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec")
    parser.add_argument("-o", "--out")
    parser.add_argument("--check-sources", metavar="ROOT", help="also check each object's source against files under ROOT")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    errors, warnings = validate(spec)
    if errors:
        print(f"{len(errors)} error(s); nothing written:")
        for e in errors:
            print("  ERROR", e)
        return 1

    assign_ids(spec)
    check_unique(spec, errors)
    if errors:
        print(f"{len(errors)} error(s); nothing written:")
        for e in errors:
            print("  ERROR", e)
        return 1
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    stats = {"crossings": 0, "label_hits": 0}
    page = render_page(copy.deepcopy(spec), warnings, stats)
    out = Path(args.out) if args.out else spec_path.with_name(spec_path.name.replace(".spec.json", "").replace(".json", "") + ".html")
    out.write_text(page, encoding="utf-8")

    count_figs = sum(1 for _ in figures(spec))
    print(f"wrote {out} ({len(page) // 1024} KB): {count_figs} figures, {sum(1 for _ in tables(spec))} tables")
    print(f"line crossings: {stats['crossings']}, label collisions: {stats['label_hits']}")
    for w in warnings:
        print("  WARN", w)
    code = 1 if (args.strict and warnings) else 0
    if args.check_sources:
        total, problems = check_sources(spec, args.check_sources)
        print(f"sources checked: {total}, out of date: {len(problems)}")
        for p in problems:
            print("  STALE", p)
        code = code or (1 if problems else 0)
    return code


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Build an Excalidraw flow diagram in the house style from a small JSON spec.

Usage:
    python3 build_flow.py spec.json -o out.excalidraw [--copy]
    python3 build_flow.py --check some.excalidraw

The spec describes WHAT is in the flow (sections, boxes, nesting, arrows, labels);
this script decides WHERE everything goes and emits Excalidraw JSON that always
follows the style rules (elbow arrows, Nunito, roughness 0, single ink colour,
transparent rounded boxes). See ../references/spec-format.md for the spec format.

--copy also puts the elements on the macOS clipboard in Excalidraw's clipboard
format, so they can be pasted (Cmd+V) into an existing canvas without replacing it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------- style constants
INK = "#1e1e1e"
RED = "#e03131"  # reserved for review notes only
FONT = 6  # Nunito
LH = 1.25
SIZE_SECTION = 36
SIZE_TITLE = 20
SIZE_CHILD_TITLE = 16
SIZE_BODY = 16
SIZE_LABEL = 16

PAD = 24  # inner padding of a box
HEAD_GAP = 12  # heading -> description
CHILD_GAP = 28  # header -> nested children block
SECTION_PAD = 70
SECTION_TITLE_GAP = 50
WRAP = 300  # description wrap width (px)
CODE_MAX = 560  # code-ish lines may grow the box up to this before wrapping
MIN_W = 180
COL_GAP_MIN = 150
ROW_GAP = 60
NESTED_ROW_GAP = 24
SECTION_GAP = 260
ARROW_GAP = 4  # distance between arrow tip and box edge
NOW = int(time.time() * 1000)


# ---------------------------------------------------------------- text metrics
def _cw(c: str) -> float:
    """Approximate Nunito advance width as a fraction of font size (slightly generous)."""
    if c == " ":
        return 0.27
    if c in "il.,:;|!'`":
        return 0.27
    if c in "mwMW@%":
        return 0.86
    if c in "{}()[]":
        return 0.36
    if c in "→←↑↓⇒":
        return 1.0
    if c.isupper():
        return 0.68
    if c.isdigit():
        return 0.58
    return 0.54


def text_w(s: str, size: float) -> float:
    return max((sum(_cw(c) for c in line) * size for line in s.split("\n")), default=0)


def is_code(line: str) -> bool:
    return line.startswith(("  ", "\t")) or any(ch in line for ch in "{};=<>") or "->" in line


def wrap(text: str, size: float, maxw: float) -> list[str]:
    out: list[str] = []
    for raw in text.split("\n"):
        line = raw.rstrip()
        limit = CODE_MAX if is_code(line) else maxw
        if text_w(line, size) <= limit:
            out.append(line)
            continue
        indent = line[: len(line) - len(line.lstrip())]
        cur = indent
        for word in line.split():
            trial = (cur + " " + word) if cur.strip() else indent + word
            if text_w(trial, size) <= maxw or not cur.strip():
                cur = trial
            else:
                out.append(cur)
                cur = indent + word
        out.append(cur)
    return out


def block_h(lines: list[str], size: float) -> float:
    return len(lines) * size * LH if lines else 0


# ---------------------------------------------------------------- element factory
class Builder:
    def __init__(self) -> None:
        self.elements: list[dict] = []
        self.by_id: dict[str, dict] = {}

    def _base(self, eid: str, etype: str, x, y, w, h) -> dict:
        seed = int(hashlib.md5(eid.encode()).hexdigest()[:8], 16)
        el = {
            "id": eid, "type": etype,
            "x": round(x, 2), "y": round(y, 2), "width": round(w, 2), "height": round(h, 2),
            "angle": 0, "strokeColor": INK, "backgroundColor": "transparent",
            "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
            "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
            "roundness": None, "seed": seed, "version": 1, "versionNonce": seed ^ 0x5F5F,
            "isDeleted": False, "boundElements": [], "updated": NOW, "link": None, "locked": False,
        }
        self.elements.append(el)
        self.by_id[eid] = el
        return el

    def rect(self, eid, x, y, w, h, dashed=False) -> dict:
        el = self._base(eid, "rectangle", x, y, w, h)
        el["roundness"] = {"type": 3}
        el["strokeStyle"] = "dashed" if dashed else "solid"
        return el

    def text(self, eid, x, y, lines, size, align="left", color=INK, container=None, w=None) -> dict:
        s = "\n".join(lines)
        tw_ = w if w is not None else text_w(s, size)
        el = self._base(eid, "text", x, y, tw_, block_h(lines, size))
        el.update({
            "strokeColor": color, "strokeWidth": 1, "boundElements": None,
            "text": s, "originalText": s, "fontSize": size, "fontFamily": FONT,
            "textAlign": align, "verticalAlign": "middle" if container else "top",
            "containerId": container, "lineHeight": LH, "autoResize": True,
        })
        return el


# ---------------------------------------------------------------- spec walking
class Spec:
    def __init__(self, data: dict) -> None:
        self.data = data
        self.sections: list[dict] = data.get("sections") or []
        self.top_nodes: list[dict] = data.get("nodes") or []
        if self.sections and self.top_nodes:
            sys.exit("spec: use either 'sections' or top-level 'nodes', not both")
        self.edges: list[dict] = data.get("edges") or []
        self.notes: dict[str, str] = {}
        for n in data.get("notes") or []:
            self.notes[n["for"]] = (self.notes.get(n["for"], "") + "\n" + n["text"]).strip()
        self.nodes: dict[str, dict] = {}
        self.parent: dict[str, str | None] = {}
        for s in self.sections:
            s["_section"] = True
            self._index(s, None, -1)
            for n in s.get("nodes") or []:
                self._index(n, s["id"], 0)
        for n in self.top_nodes:
            self._index(n, None, 0)
        for e in self.edges:
            for k in ("from", "to"):
                if e[k] not in self.nodes:
                    sys.exit(f"spec: edge {e} refers to unknown id '{e[k]}'")
            if e["to"] in self.ancestors(e["from"]) or e["from"] in self.ancestors(e["to"]):
                sys.exit(f"spec: edge {e['from']} -> {e['to']} connects a box to its own container; "
                         "nested boxes are connected by being inside, not by arrows")
            if e.get("style", "solid") not in ("solid", "dotted", "dashed"):
                sys.exit(f"spec: edge style must be solid|dotted|dashed, got {e.get('style')}")

    def _index(self, n: dict, parent: str | None, depth: int) -> None:
        if "id" not in n:
            sys.exit(f"spec: every box needs an 'id': {n}")
        if n["id"] in self.nodes:
            sys.exit(f"spec: duplicate id '{n['id']}'")
        n["_depth"] = depth
        self.nodes[n["id"]] = n
        self.parent[n["id"]] = parent
        for c in n.get("children") or []:
            self._index(c, n["id"], depth + 1)

    def kids(self, n: dict) -> list[dict]:
        return (n.get("nodes") if n.get("_section") else n.get("children")) or []

    def ancestors(self, nid: str) -> list[str]:
        out, p = [], self.parent.get(nid)
        while p:
            out.append(p)
            p = self.parent.get(p)
        return out


# ---------------------------------------------------------------- measuring
def measure(spec: Spec, n: dict) -> None:
    section = n.get("_section", False)
    if section:
        tsize, pad = SIZE_SECTION, SECTION_PAD
    else:
        tsize, pad = (SIZE_TITLE if n["_depth"] == 0 else SIZE_CHILD_TITLE), PAD
    wrapw = n.get("wrap", WRAP)
    n["_title_lines"] = wrap(n.get("title", ""), tsize, max(wrapw, 360 if section else wrapw))
    n["_desc_lines"] = wrap(n.get("desc", ""), SIZE_BODY, wrapw) if n.get("desc") else []
    n["_tsize"], n["_pad"] = tsize, pad
    head_w = max(text_w("\n".join(n["_title_lines"]), tsize), text_w("\n".join(n["_desc_lines"]), SIZE_BODY))
    head_h = block_h(n["_title_lines"], tsize)
    if n["_desc_lines"]:
        head_h += HEAD_GAP + block_h(n["_desc_lines"], SIZE_BODY)
    n["_head_h"] = head_h

    kids = spec.kids(n)
    if kids:
        for k in kids:
            measure(spec, k)
        mode = n.get("layout") or ("flow" if section else "auto")
        pos, gw, gh = layout_group(spec, kids, mode, nested=not section)
        n["_group"] = (pos, gw, gh)
        if n.get("desc") and "wrap" not in n and gw > wrapw:  # use the parent's full width
            n["_desc_lines"] = wrap(n["desc"], SIZE_BODY, gw)
            head_w = max(text_w("\n".join(n["_title_lines"]), tsize), text_w("\n".join(n["_desc_lines"]), SIZE_BODY))
            head_h = block_h(n["_title_lines"], tsize) + HEAD_GAP + block_h(n["_desc_lines"], SIZE_BODY)
            n["_head_h"] = head_h
        gap = SECTION_TITLE_GAP if section else CHILD_GAP
        w = max(head_w, gw) + 2 * pad
        h = pad + head_h + gap + gh + pad
    else:
        w = head_w + 2 * pad
        h = pad + head_h + pad
    n["_w"] = max(w, MIN_W, n.get("width", 0))
    n["_h"] = max(h, n.get("height", 0))

    note = spec.notes.get(n["id"])
    n["_note_lines"] = wrap(note, SIZE_BODY, max(n["_w"], 260)) if note else []
    n["_note_h"] = block_h(n["_note_lines"], SIZE_BODY) + 8 if note else 0
    n["_slot_w"] = max(n["_w"], text_w("\n".join(n["_note_lines"]), SIZE_BODY)) if note else n["_w"]
    n["_slot_h"] = n["_h"] + n["_note_h"]


def layout_group(spec: Spec, items: list[dict], mode: str, nested: bool):
    """Lay out sibling boxes left-to-right in layered columns. Returns (positions, w, h)."""
    ids = [n["id"] for n in items]
    idset = set(ids)
    order = {nid: i for i, nid in enumerate(ids)}

    def lift(x):
        while x is not None and x not in idset:
            x = spec.parent.get(x)
        return x

    gedges = []
    for e in spec.edges:
        a, b = lift(e["from"]), lift(e["to"])
        if a and b and a != b:
            gedges.append((a, b, e))

    rank: dict[str, int] = {}
    back: set[tuple[str, str]] = set()
    if mode == "column":
        rank = {i: 0 for i in ids}
    elif mode == "row" or (mode == "auto" and nested and not gedges):
        rank = {i: k for k, i in enumerate(ids)}
    else:
        # drop back edges (DFS in spec order), then longest-path ranking
        succ = {i: [] for i in ids}
        for a, b, _ in gedges:
            succ[a].append(b)
        state: dict[str, int] = {}

        def dfs(u):
            state[u] = 1
            for v in succ[u]:
                if state.get(v) == 1:
                    back.add((u, v))
                elif v not in state:
                    dfs(v)
            state[u] = 2

        for i in ids:
            if i not in state:
                dfs(i)
        fwd = [(a, b) for a, b, _ in gedges if (a, b) not in back]
        rank = {i: 0 for i in ids}
        for _ in range(len(ids)):
            changed = False
            for a, b in fwd:
                if rank[b] < rank[a] + 1:
                    rank[b] = rank[a] + 1
                    changed = True
            if not changed:
                break
    for n in items:
        if "rank" in n:
            rank[n["id"]] = int(n["rank"])

    ncols = max(rank.values()) + 1 if rank else 0
    cols: list[list[dict]] = [[] for _ in range(ncols)]
    for n in items:
        cols[rank[n["id"]]].append(n)
    # barycenter ordering (one left-to-right sweep), respecting explicit 'row'
    slot: dict[str, float] = {}
    for c, col in enumerate(cols):
        def key(n):
            if "row" in n:
                return (float(n["row"]), order[n["id"]])
            preds = [slot[a] for a, b, _ in gedges if b == n["id"] and a in slot and rank[a] < c]
            return (sum(preds) / len(preds) if preds else float(order[n["id"]]), order[n["id"]])
        col.sort(key=key)
        for k, n in enumerate(col):
            slot[n["id"]] = k

    # gaps between columns sized for labels sitting in them
    gaps = []
    for c in range(max(ncols - 1, 0)):
        crossing = [e for a, b, e in gedges if min(rank[a], rank[b]) <= c < max(rank[a], rank[b])]
        lw = [text_w(e["label"], SIZE_LABEL) for e in crossing if e.get("label")]
        if nested:  # sub-parts sit close together inside their parent
            base = 90 if crossing else 36
        else:
            base = COL_GAP_MIN
        gaps.append(max(base, (max(lw) + 140) if lw else 0))
    row_gap = NESTED_ROW_GAP if nested else ROW_GAP
    vlabels = [text_w(e.get("label", ""), SIZE_LABEL) for a, b, e in gedges if e.get("label") and rank[a] == rank[b]]
    if vlabels:
        row_gap = max(row_gap, SIZE_LABEL * LH + 50)

    col_w = [max(n["_slot_w"] for n in col) if col else 0 for col in cols]
    col_h = [sum(n["_slot_h"] for n in col) + row_gap * max(len(col) - 1, 0) for col in cols]
    gh = max(col_h) if col_h else 0
    if back:
        gh += 60  # room for loop-back lanes underneath
    pos: dict[str, tuple[float, float]] = {}
    x = 0.0
    for c, col in enumerate(cols):
        y = ((max(col_h) - col_h[c]) / 2 if col_h else 0)
        for n in col:
            pos[n["id"]] = (x + (col_w[c] - n["_slot_w"]) / 2, y)
            y += n["_slot_h"] + row_gap
        x += col_w[c] + (gaps[c] if c < len(gaps) else 0)
    gw = x
    return pos, gw, gh


# ---------------------------------------------------------------- placing
def place(spec: Spec, b: Builder, n: dict, sx: float, sy: float, boxes: dict) -> None:
    """sx, sy = top-left of the node's slot (note sits above the box)."""
    x = sx + (n["_slot_w"] - n["_w"]) / 2
    y = sy + n["_note_h"]
    w, h, pad = n["_w"], n["_h"], n["_pad"]
    section = n.get("_section", False)
    if n["_note_lines"]:
        b.text(f"note_{n['id']}", sx, sy, n["_note_lines"], SIZE_BODY, color=RED)
    b.rect(f"box_{n['id']}", x, y, w, h, dashed=n.get("dashed", False))
    boxes[n["id"]] = (x, y, w, h)
    ty = y + pad
    tw_ = text_w("\n".join(n["_title_lines"]), n["_tsize"])
    b.text(f"title_{n['id']}", x + (w - tw_) / 2, ty, n["_title_lines"], n["_tsize"], align="center")
    ty += block_h(n["_title_lines"], n["_tsize"])
    if n["_desc_lines"]:
        ty += HEAD_GAP
        dw = text_w("\n".join(n["_desc_lines"]), SIZE_BODY)
        # descriptions are left-aligned; in a box wider than the text, centre the block
        dx = x + max(pad, (w - dw) / 2) if spec.kids(n) else x + pad
        b.text(f"desc_{n['id']}", dx, ty, n["_desc_lines"], SIZE_BODY)
        ty += block_h(n["_desc_lines"], SIZE_BODY)
    if "_group" in n:
        pos, gw, gh = n["_group"]
        gx = x + (w - gw) / 2
        gy = ty + (SECTION_TITLE_GAP if section else CHILD_GAP)
        for k in spec.kids(n):
            px, py = pos[k["id"]]
            place(spec, b, k, gx + px, gy + py, boxes)


# ---------------------------------------------------------------- routing
def _hits(seg, box, pad=6) -> bool:
    (x1, y1), (x2, y2) = seg
    bx, by, bw, bh = box
    bx, by, bw, bh = bx - pad, by - pad, bw + 2 * pad, bh + 2 * pad
    lo_x, hi_x = min(x1, x2), max(x1, x2)
    lo_y, hi_y = min(y1, y2), max(y1, y2)
    return lo_x < bx + bw and hi_x > bx and lo_y < by + bh and hi_y > by


def route(spec: Spec, boxes: dict, e: dict, lane_counter: list[int]):
    a, z = e["from"], e["to"]
    S, T = boxes[a], boxes[z]
    sx, sy, sw, sh = S
    tx, ty, tw_, th = T
    skip = {a, z, *spec.ancestors(a), *spec.ancestors(z)}
    obstacles = [bx for nid, bx in boxes.items() if nid not in skip]

    def clear(pts):
        segs = list(zip(pts, pts[1:]))
        # ignore the first/last few px so touching the own box edge is fine
        return not any(_hits(s, o) for s in segs for o in obstacles)

    G = ARROW_GAP
    if tx >= sx + sw + 10:  # target to the right: main left-to-right case
        lo, hi = max(sy, ty), min(sy + sh, ty + th)
        if hi - lo >= 24:
            yy = (lo + hi) / 2
            pts = [(sx + sw + G, yy), (tx - G, yy)]
            if clear(pts):
                return pts
        y1, y2 = sy + sh / 2, ty + th / 2
        for mx in ((sx + sw + tx) / 2, tx - 40, sx + sw + 40):
            pts = [(sx + sw + G, y1), (mx, y1), (mx, y2), (tx - G, y2)]
            if clear(pts):
                return pts
        x1, x2 = sx + sw + 30, tx - 30
        band = [o for o in obstacles if o[0] < x2 and o[0] + o[2] > x1]
        above = min([o[1] for o in band] + [y1, y2]) - 40
        below = max([o[1] + o[3] for o in band] + [y1, y2]) + 40
        lane = above if abs(above - y1) + abs(above - y2) <= abs(below - y1) + abs(below - y2) else below
        return [(sx + sw + G, y1), (x1, y1), (x1, lane), (x2, lane), (x2, y2), (tx - G, y2)]
    if ty >= sy + sh + 10 or ty + th <= sy - 10:  # stacked vertically
        down = ty >= sy + sh + 10
        ys, ye = (sy + sh + G, ty - G) if down else (sy - G, ty + th + G)
        lo, hi = max(sx, tx), min(sx + sw, tx + tw_)
        if hi - lo >= 24:
            xx = (lo + hi) / 2
            pts = [(xx, ys), (xx, ye)]
            if clear(pts):
                return pts
        x1, x2 = sx + sw / 2, tx + tw_ / 2
        my = (ys + ye) / 2
        return [(x1, ys), (x1, my), (x2, my), (x2, ye)]
    # target to the left (loop back): go under both boxes, or over them if under is blocked
    x1, x2 = sx + sw / 2, tx + tw_ / 2
    band = [o for o in obstacles if o[0] < max(x1, x2) + 20 and o[0] + o[2] > min(x1, x2) - 20]
    k = 18 * lane_counter[0]
    lane_counter[0] += 1
    floor = max([o[1] + o[3] for o in band] + [sy + sh, ty + th])
    under = [(x1, sy + sh + G), (x1, floor + 30 + k), (x2, floor + 30 + k), (x2, ty + th + G)]
    ceil = min([o[1] for o in band] + [sy, ty])
    over = [(x1, sy - G), (x1, ceil - 30 - k), (x2, ceil - 30 - k), (x2, ty - G)]
    for pts in (under, over):
        if clear(pts):
            return pts
    # both blocked: leave from the sides and go around everything underneath
    lane = floor + 30 + k
    return [(sx + sw + G, sy + sh / 2), (sx + sw + 24, sy + sh / 2), (sx + sw + 24, lane),
            (tx - 24, lane), (tx - 24, ty + th / 2), (tx - G, ty + th / 2)]


def label_anchor(pts):
    """Where Excalidraw puts an arrow's bound label (middle point / middle segment)."""
    n = len(pts)
    if n % 2 == 1:
        return pts[n // 2]
    p, q = pts[n // 2 - 1], pts[n // 2]
    return ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)


def add_arrow(b: Builder, idx: int, e: dict, pts, boxes) -> None:
    aid = f"arrow_{idx}_{e['from']}_{e['to']}"
    x0, y0 = pts[0]
    rel = [[round(px - x0, 2), round(py - y0, 2)] for px, py in pts]
    xs, ys = [p[0] for p in rel], [p[1] for p in rel]
    el = b._base(aid, "arrow", x0, y0, max(xs) - min(xs), max(ys) - min(ys))
    style = e.get("style", "solid")
    S, T = boxes[e["from"]], boxes[e["to"]]

    def binding(nid, box, p):
        bx, by, bw, bh = box
        fp = [round((p[0] - bx) / bw, 4), round((p[1] - by) / bh, 4)]
        return {"elementId": f"box_{nid}", "focus": 0, "gap": ARROW_GAP, "fixedPoint": fp, "mode": "orbit"}

    el.update({
        "strokeStyle": style, "points": rel, "lastCommittedPoint": None,
        "startBinding": binding(e["from"], S, pts[0]), "endBinding": binding(e["to"], T, pts[-1]),
        "startArrowhead": None, "endArrowhead": "arrow",
        "elbowed": True, "fixedSegments": None, "startIsSpecial": None, "endIsSpecial": None,
    })
    for nid in (e["from"], e["to"]):
        b.by_id[f"box_{nid}"]["boundElements"].append({"id": aid, "type": "arrow"})
    if e.get("label"):
        lines = e["label"].split("\n")
        lw = text_w(e["label"], SIZE_LABEL)
        lh = block_h(lines, SIZE_LABEL)
        cx, cy = label_anchor(pts)
        t = b.text(f"label_{aid}", cx - lw / 2, cy - lh / 2, lines, SIZE_LABEL, align="center", container=aid, w=lw)
        t["labelPosition"] = 0.5
        el["boundElements"] = [{"id": t["id"], "type": "text"}]


# ---------------------------------------------------------------- main build
def build(data: dict) -> list[dict]:
    spec = Spec(data)
    b = Builder()
    boxes: dict[str, tuple] = {}
    if spec.sections:
        x = 0.0
        for s in spec.sections:
            measure(spec, s)
        top = 0.0
        for s in spec.sections:
            place(spec, b, s, x, top, boxes)
            x += s["_slot_w"] + SECTION_GAP
    else:
        for n in spec.top_nodes:
            measure(spec, n)
        pos, gw, gh = layout_group(spec, spec.top_nodes, data.get("layout", "flow"), nested=False)
        oy = 0.0
        if data.get("title"):
            lines = wrap(data["title"], SIZE_SECTION, 900)
            b.text("diagram_title", (gw - text_w("\n".join(lines), SIZE_SECTION)) / 2, 0, lines, SIZE_SECTION, align="center")
            oy = block_h(lines, SIZE_SECTION) + SECTION_TITLE_GAP
        for n in spec.top_nodes:
            px, py = pos[n["id"]]
            place(spec, b, n, px, oy + py, boxes)

    lane_counter = [0]
    for i, e in enumerate(spec.edges):
        add_arrow(b, i, e, route(spec, boxes, e, lane_counter), boxes)
    return b.elements


# ---------------------------------------------------------------- style check
def check(elements: list[dict]) -> list[str]:
    errs = []
    ids = {e["id"] for e in elements if not e.get("isDeleted")}
    for el in elements:
        if el.get("isDeleted"):
            continue
        t, i = el["type"], el["id"]
        if el.get("roughness", 0) != 0:
            errs.append(f"{i}: roughness {el['roughness']} (must be 0 — no sloppiness)")
        if el.get("strokeColor") not in (INK, RED):
            errs.append(f"{i}: strokeColor {el.get('strokeColor')} (only {INK}, or {RED} for review notes)")
        if el.get("backgroundColor") not in ("transparent", None):
            errs.append(f"{i}: has a fill {el.get('backgroundColor')} (boxes are unfilled)")
        if t == "text" and el.get("fontFamily") != FONT:
            errs.append(f"{i}: fontFamily {el.get('fontFamily')} (must be 6 = Nunito)")
        if t == "rectangle":
            if (el.get("roundness") or {}).get("type") != 3:
                errs.append(f"{i}: rectangle without rounded corners")
            if el.get("strokeWidth") != 2:
                errs.append(f"{i}: strokeWidth {el.get('strokeWidth')} (must be 2)")
        if t == "arrow":
            if not el.get("elbowed"):
                errs.append(f"{i}: arrow is not an elbow arrow")
            if el.get("startArrowhead") is not None or el.get("endArrowhead") != "arrow":
                errs.append(f"{i}: arrowheads must be start=None, end='arrow'")
            for k in ("startBinding", "endBinding"):
                bd = el.get(k)
                if not bd or bd.get("elementId") not in ids:
                    errs.append(f"{i}: {k} missing — arrows must be attached to boxes at both ends")
        if t in ("ellipse", "diamond"):
            errs.append(f"{i}: {t} used — decisions are rectangles titled as a question")
    return errs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?", help="flow spec JSON")
    ap.add_argument("-o", "--out", help="output .excalidraw path (default: next to spec)")
    ap.add_argument("--copy", action="store_true", help="also copy elements to the macOS clipboard for pasting")
    ap.add_argument("--check", metavar="FILE", help="only check an existing .excalidraw file against the style rules")
    args = ap.parse_args()

    if args.check:
        data = json.loads(Path(args.check).read_text())
        errs = check(data.get("elements", []))
        print("\n".join(errs) if errs else "OK — follows the style rules")
        sys.exit(1 if errs else 0)
    if not args.spec:
        ap.error("spec is required")

    spec_path = Path(args.spec)
    data = json.loads(spec_path.read_text())
    elements = build(data)
    errs = check(elements)
    if errs:
        print("internal style check failed:\n" + "\n".join(errs), file=sys.stderr)
        sys.exit(2)
    out = Path(args.out) if args.out else spec_path.with_name(spec_path.name.replace(".flow.json", "").replace(".json", "") + ".excalidraw")
    doc = {
        "type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {"gridSize": 20, "viewBackgroundColor": "#ffffff", "currentItemFontFamily": FONT,
                     "currentItemRoughness": 0, "currentItemArrowType": "elbow"},
        "files": {},
    }
    out.write_text(json.dumps(doc, indent=1))
    print(f"wrote {out}  ({sum(e['type']=='rectangle' for e in elements)} boxes, "
          f"{sum(e['type']=='arrow' for e in elements)} arrows)")
    if args.copy:
        clip = json.dumps({"type": "excalidraw/clipboard", "elements": elements, "files": {}})
        subprocess.run(["pbcopy"], input=clip.encode(), check=True)
        print("copied to clipboard — click on the Excalidraw canvas and press Cmd+V")


if __name__ == "__main__":
    main()

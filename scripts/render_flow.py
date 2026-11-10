#!/usr/bin/env python3
"""Render a .excalidraw file to PNG with Excalidraw's own exporter (headless Chromium).

Usage:
    python3 render_flow.py diagram.excalidraw [-o diagram.png] [--light] [--scale 2]

Default is dark mode, because that is how the diagrams are viewed. The render runs
locally in a headless browser; only the Excalidraw library itself is fetched from a CDN.
Needs: pip install playwright && playwright install chromium (already present on this Mac).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXCALIDRAW = "https://esm.sh/@excalidraw/excalidraw@0.18.0?bundle"

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;background:%(bg)s}#root svg{display:block}</style></head>
<body><div id="root"></div>
<script type="module">
import { exportToSvg } from "%(lib)s";
window.render = async (data, dark) => {
  try {
    const svg = await exportToSvg({
      elements: data.elements,
      appState: { ...(data.appState||{}), exportBackground: true, exportWithDarkMode: dark,
                  viewBackgroundColor: "#ffffff", exportPadding: 40 },
      files: data.files || {},
    });
    document.getElementById("root").appendChild(svg);
    return { ok: true, w: svg.getAttribute("width"), h: svg.getAttribute("height") };
  } catch (e) { return { ok: false, error: String(e && e.stack || e) }; }
};
window.ready = true;
</script></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("-o", "--out")
    ap.add_argument("--light", action="store_true", help="render in light mode instead of dark")
    ap.add_argument("--scale", type=float, default=2)
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    src = Path(args.file)
    data = json.loads(src.read_text())
    out = Path(args.out) if args.out else src.with_suffix(".png")
    dark = not args.light
    html = PAGE % {"lib": EXCALIDRAW, "bg": "#121212" if dark else "#ffffff"}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=args.scale, viewport={"width": 1600, "height": 1000})
        page.set_content(html)
        page.wait_for_function("window.ready === true", timeout=60000)
        res = page.evaluate("([d, dark]) => window.render(d, dark)", [data, dark])
        if not res.get("ok"):
            print("render failed:", res.get("error"), file=sys.stderr)
            sys.exit(1)
        page.wait_for_timeout(800)  # let embedded fonts settle
        page.locator("#root svg").screenshot(path=str(out))
        browser.close()
    print(f"rendered {out}  ({res['w']}x{res['h']} @ {args.scale}x, {'dark' if dark else 'light'})")


if __name__ == "__main__":
    main()

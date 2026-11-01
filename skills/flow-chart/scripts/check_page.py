#!/usr/bin/env python3
"""Check a rendered page in real Chromium, and screenshot each figure to look at.

    python check_page.py docs/orders.html --shots <folder>

The renderer estimates text widths; this measures them. It reports text outside its box, labels
on top of boxes or each other, missing tooltips, a broken copy, and sideways page scroll, in light,
dark and phone widths. Exit code 1 if anything failed.

Needs Python Playwright with Chromium:
    pip install playwright && python -m playwright install chromium
To use a Chromium you already have, set FLOWCHART_CHROMIUM=/path/to/chrome.
"""
import argparse
import os
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("check_page.py needs Python Playwright. Install it with:\n"
             "    pip install playwright && python -m playwright install chromium\n"
             "Or skip this step and check the page by eye in a browser.")

MEASURE = r"""
() => {
  const problems = [];
  const rect = (e) => e.getBoundingClientRect();
  const inside = (a, b, slack) => a.left >= b.left - slack && a.right <= b.right + slack && a.top >= b.top - slack && a.bottom <= b.bottom + slack;
  const hit = (a, b) => !(a.right <= b.left + 1 || b.right <= a.left + 1 || a.bottom <= b.top + 1 || b.bottom <= a.top + 1);
  document.querySelectorAll('svg').forEach((svg) => {
    const fig = svg.closest('figure').getAttribute('data-oid');
    const shapes = [...svg.querySelectorAll('.node')].map((n) => ({ id: n.dataset.oid, el: n, box: rect(n.querySelector('.shape')), dia: n.querySelector('polygon') !== null }));
    shapes.forEach((s) => {
      if (s.dia) return;
      s.el.querySelectorAll(':scope > text, .member text').forEach((t) => {
        if (!inside(rect(t), s.box, 1)) problems.push(`${s.id}: text "${t.textContent}" sticks out of its box`);
      });
    });
    svg.querySelectorAll('.region').forEach((region) => {
      /* Exact shapes come from clipping, so prove the bare area of each one answers to its own ID. */
      const [x, y] = region.dataset.probe.split(',').map(Number);
      /* The figure may scroll sideways on a phone, so bring this exact point into view. */
      const before = new DOMPoint(x, y).matrixTransform(svg.getScreenCTM());
      svg.closest('.scroll').scrollLeft += before.x - window.innerWidth / 2;
      window.scrollBy(0, before.y - window.innerHeight / 2);
      const moved = new DOMPoint(x, y).matrixTransform(svg.getScreenCTM());
      const found = document.elementFromPoint(moved.x, moved.y);
      const owner = found && found.closest('[data-oid]');
      if (!owner || owner.dataset.oid !== region.dataset.oid) problems.push(`${region.dataset.oid}: pointing at it finds ${owner ? owner.dataset.oid : 'nothing'}`);
    });
    const regionTexts = [...svg.querySelectorAll('.region')].flatMap((region) => [...region.querySelectorAll('text')].map((t) => ({ id: region.dataset.oid, t })));
    regionTexts.forEach((a, i) => regionTexts.slice(i + 1).forEach((b) => {
      if (a.id !== b.id && hit(rect(a.t), rect(b.t))) problems.push(`${a.id} and ${b.id}: text overlaps`);
    }));
    const labels = [...svg.querySelectorAll('.line')].map((l) => ({ id: l.dataset.oid, texts: [...l.querySelectorAll('text')] }));
    labels.forEach((l) => l.texts.forEach((t) => {
      const r = rect(t);
      shapes.forEach((s) => { if (hit(r, s.box) && !s.dia) problems.push(`${l.id}: label "${t.textContent}" overlaps box ${s.id}`); });
    }));
    for (let i = 0; i < labels.length; i++) for (let j = i + 1; j < labels.length; j++) {
      labels[i].texts.forEach((a) => labels[j].texts.forEach((b) => {
        if (hit(rect(a), rect(b))) problems.push(`${fig}: labels of ${labels[i].id} and ${labels[j].id} overlap`);
      }));
    }
  });
  const objects = JSON.parse(document.getElementById('objdata').textContent).objects;
  Object.keys(objects).forEach((id) => {
    const o = objects[id];
    if (['box', 'class', 'line', 'group', 'note', 'attribute', 'method', 'set', 'region', 'item'].includes(o.k) && !o.d) problems.push(`${id}: no tooltip text`);
    if (['box', 'class', 'line', 'group', 'note', 'attribute', 'method', 'row', 'set', 'region', 'item'].includes(o.k) && !document.querySelector(`[data-oid="${id}"]`)) problems.push(`${id}: not on the page`);
  });
  const ids = [...document.querySelectorAll('[data-oid]')].map((e) => e.dataset.oid);
  if (new Set(ids).size !== ids.length) problems.push('an ID appears on two elements');
  if (document.documentElement.scrollWidth > window.innerWidth + 1) problems.push(`page scrolls sideways at ${window.innerWidth}px`);
  return { problems, objects: Object.keys(objects).length };
}
"""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("page")
    parser.add_argument("--shots", help="folder for one screenshot per figure")
    args = parser.parse_args()
    url = Path(args.page).resolve().as_uri()
    failures = []

    with sync_playwright() as p:
        exe = os.environ.get("FLOWCHART_CHROMIUM")
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        for name, width, scheme in (("desktop", 1200, "light"), ("dark", 1200, "dark"), ("phone", 400, "light")):
            context = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
            context.grant_permissions(["clipboard-read", "clipboard-write"])
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "fonts.g" not in m.text and "ERR_" not in m.text else None)
            page.goto(url)
            page.wait_for_timeout(500)
            result = page.evaluate(MEASURE)
            problems = sorted(set(result["problems"]))
            print(f"{name} ({width}px, {scheme}): {result['objects']} objects, {len(problems)} problems")
            for line in problems + errors:
                print("  ", line)
            failures += problems + errors
            if args.shots and name != "phone":
                folder = Path(args.shots)
                folder.mkdir(parents=True, exist_ok=True)
                page.add_style_tag(content=".toolbar { position: static; }")  # or it covers the screenshots
                for fig in page.query_selector_all("figure"):
                    fig.screenshot(path=str(folder / f"{name}-{fig.get_attribute('data-oid')}.png"))
            if name == "desktop":
                failures += try_interaction(page)
            context.close()
        browser.close()
    print("PASS" if not failures else f"FAIL: {len(failures)} problems")
    return 1 if failures else 0


def try_interaction(page):
    """Use the page the way a person would: hover for a tooltip, click to copy, collect, find."""
    bad = []
    node = page.query_selector("svg .node") or page.query_selector("svg .region")
    line = page.query_selector("svg .line")
    for target, what in ((node, "box"), (line, "line")):
        if target is None:
            continue
        oid = target.get_attribute("data-oid")
        hit = target.query_selector(".shape, .hit") or target.query_selector(".bdg")
        hit.scroll_into_view_if_needed()
        box = hit.bounding_box()
        points = hit.evaluate("(e) => { if (e.getPointAtLength) { const p = e.getPointAtLength(e.getTotalLength() / 2); const m = e.getScreenCTM(); return [p.x * m.a + m.e, p.y * m.d + m.f]; } return null; }") if what == "line" else None
        x, y = points if points else (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.move(x, y)
        page.wait_for_timeout(50)
        tip = page.inner_text("#tip") if page.is_visible("#tip") else ""
        if oid not in tip:
            bad.append(f"hovering {what} {oid} showed no tooltip with its ID")
        page.mouse.click(x, y)
        page.wait_for_timeout(100)
        copied = page.evaluate("navigator.clipboard.readText()")
        if not copied.startswith(oid):
            bad.append(f"clicking {what} {oid} copied {copied[:60]!r}")
        print(f"   click on {what} copies: {copied[:90]}")
    page.fill("#findbox", node.get_attribute("data-oid"))
    page.press("#findbox", "Enter")
    page.wait_for_timeout(100)
    if not page.evaluate("document.querySelector('.flash') !== null"):
        bad.append("find-by-ID did not highlight the object")
    page.click("#copyall")
    page.wait_for_timeout(100)
    if node.get_attribute("data-oid") not in page.evaluate("navigator.clipboard.readText()"):
        bad.append("Copy all IDs left the first box out")
    page.check("#many")
    spot = node.query_selector(".shape") or node.query_selector(".bdg")
    spot.scroll_into_view_if_needed()
    box = spot.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    if page.is_hidden("#tray"):
        bad.append("collecting an object did not show the tray")
    page.click("#trayclear")
    page.uncheck("#many")
    # A browser treats shift-click as selecting text; it still has to collect, every time.
    shapes = (page.query_selector_all("svg .node .shape") or page.query_selector_all("svg .region .bdg"))[:3]
    for shape in shapes:
        shape.click(modifiers=["Shift"])
    page.click("#traycopy")
    page.wait_for_timeout(100)
    got = len(page.evaluate("navigator.clipboard.readText()").splitlines()) - 1  # less the heading
    if got != len(shapes):
        bad.append(f"shift-clicking {len(shapes)} objects collected {got}")
    print(f"   shift-click collected {got} of {len(shapes)}")
    page.click("#trayclear")
    for b in bad:
        print("  ", b)
    return bad


if __name__ == "__main__":
    sys.exit(main())

---
name: flow-chart
description: Generate interactive HTML flow charts and system design documents from a JSON spec, including Venn diagrams, where every box, line, region and table row has a stable ID (like F2.B7), a tooltip and one-click copy, so people and AI can discuss exact objects. Use this whenever the user wants a flow chart, a visual map of a codebase or repo, flowchart, process or system diagram, sequence diagram, state machine, class or object-oriented diagram, Venn or overlap diagram, architecture diagram, system design document, or a page explaining "how this system works", even if they only say "draw this", "diagram it" or "map this out". Also use when the user refers to an object by an ID like F2.B7 or T1.R3, or wants to change an existing chart. Not for data charts such as bar or line graphs.
---

# Flow Chart

Turn how a system really behaves into one page a cold reader can follow, and that you and the user can then discuss object by object.

The spec is the source; the HTML is generated. Lay nothing out by hand: scripts assign IDs, size boxes and route lines. Your job is getting the content true and the story clear.

## Before you start

- **Follow the project's data rules.** A chart gets read and shared widely. Read the project's CLAUDE.md first, and never put personal data, login details or real customer values in a spec. Use invented values in worked examples.
- **Existing chart?** If the user quotes an ID or asks for a change, skip to [Changing a chart](#changing-a-chart).
- **Choose the document type.** Read [references/document-types.md](references/document-types.md). "How does it work when it runs" is a flow document. "How is it built and why" is a system design document. Ask only if the request really could be either and the difference matters.

## 1. Find out what's true

Trace behaviour from the code, logs and tests, not from memory or from docs alone, because docs drift and a confident wrong chart does more harm than none.

- Note a `source` for each claim as you go, so the chart can be re-checked later (see [Sources](references/spec-format.md#sources)).
- Where the code leaves behaviour unclear and the answer matters, test it with a small probe or test. Report what you couldn't verify, and mark it in the chart's tooltip or `status`.
- If tracing turns up a bug or a surprise, tell the user. Don't draw around it.

## 2. Write the spec

Read [references/spec-format.md](references/spec-format.md), then write `<name>.spec.json` next to where the page belongs, such as `docs/`. Keep the spec with the page, because it's what makes the page editable later.

- **Draw the mechanism.** One figure answers one question. Split a figure when it needs a second question to explain it.
- **Plan the grid first.** Put the main path in one column, top to bottom, and put exceptions beside it. A good grid does more for readability than any later fix.
- **Label lines with what actually moves:** "sends order events", not "connects to".
- **Write tooltips for someone pointing at the object and asking "why?"** Include what it waits for, what can fail and what happens then. Every box, line, group, note and class member needs one, and the build fails without it.
- **Use a Venn figure when the overlaps are the point**, such as who holds which data. Decide what belongs in every region, and check each claim as you would a step. An overlap you mark empty is a claim too, so give the reason.
- **Use tables for lookups** such as timers, failure modes and "when X happens during Y". They read better than a tangle of lines.
- Write for a cold reader: plain words, and no private shorthand from this conversation.

The scripts below live in this skill's own folder. `<skill>` stands for that folder's path, which depends on where the skill was installed (for example `~/.claude/skills/flow-chart`, or the folder of an installed plugin).

## 3. Render and fix

The renderer needs only Python 3.9+ and the standard library.

```bash
python <skill>/scripts/render.py docs/name.spec.json --check-sources .
```

This validates the spec, writes IDs back into it, and reports line crossings, label collisions and out-of-date sources. Fix errors in the spec. To reduce crossings, move nodes on the grid first, and set `from_side` / `to_side` only if that isn't enough.

## 4. Check it in a browser

This step needs the Python package `playwright` and its Chromium browser (`python -m playwright install chromium`). To use a Chromium that is already installed, set `FLOWCHART_CHROMIUM` to its path.

```bash
python <skill>/scripts/check_page.py docs/name.html --shots <scratch-folder>
```

This measures the real page in light, dark and phone widths and tries hover, copy, collect and find. Then look at every screenshot yourself, because a chart can pass every check and still read badly. Ask of each figure:

- Can a cold reader find the start and follow the main path without help?
- Does any line take a long way round, or run confusingly close beside another?
- Does each color mean something the legend explains?

Fix what you find in the spec and render again. If Playwright isn't installed and the user doesn't want to install it, say so, and check the page in any browser you can use, or ask the user to open it.

## 5. Deliver

Give the user the spec and page paths. The page is one self-contained HTML file, so it can be committed, attached or hosted anywhere. If your environment has a tool for publishing pages, such as Artifacts on claude.ai, and the page is finished work for other people, offer to publish it. Report the object count, any remaining crossings, and anything you couldn't verify.

Tell the user how to talk about the chart:

> Hover any object for its explanation. Click it to copy its reference, then paste that here. Use **Collect several** or shift-click to copy many at once.

## Changing a chart

When the user quotes `F2.B7`, `F2.L12` or a pasted reference line:

1. Find that object in the spec by its `id`, under the figure with the matching `id`. `F2.B7` is the node with `"id": "B7"` in figure `F2`.
2. If the ID isn't there, or a bare `B7` matches more than one figure, say so and ask. Don't guess at a similar box.
3. Change only what was asked, and check the behaviour against the code if the request changes a claim about the system.
4. Render and check again. Then answer using IDs: "Moved F2.B7 below F2.B9. New line F2.L31 replaces F2.L12."

**IDs are promises.** Other people may already have quoted them. Never reassign, reuse or renumber one. A new object gets a new ID, and a removed object's number stays retired. If a box's meaning changes completely, make a new box with a new ID.

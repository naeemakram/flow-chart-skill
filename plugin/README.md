# flow-chart

A Claude skill that reads a codebase and draws how it really works: flow charts, sequence diagrams, state machines, class diagrams and Venn diagrams, as one interactive HTML page. Every box, line and table row gets a stable ID such as `F1.B7`, so you and Claude can point at the exact thing you mean.

## Install

In Claude Code:

```
/plugin install flow-chart --marketplace naeemakram/flow-chart-skill
```

## Use

Ask in plain words, for example:

- "Diagram how a request flows through this service"
- "Map out the architecture of this repo"
- "Draw the state machine for an order"
- "Write a system design document for the billing module"

Claude traces the behaviour from the code, writes a JSON spec next to your docs, and renders it into a self-contained HTML page. Hover any object to see why it exists and the source it came from. Click it to copy its ID, then paste the ID into your chat to discuss or change it. To change a chart, quote an ID: "Split F1.B3 into two steps."

Each claim can quote the code it relies on, and the renderer re-checks those quotes, so a diagram that has gone stale fails its check and names the object that is now wrong.

## What it needs

- Python 3.9 or later. The renderer uses only the standard library and makes no network calls.
- Optional: the Python package `playwright` with its Chromium browser, for an automated check of the rendered page.

The generated page loads its fonts from Google Fonts when it is opened, and falls back to system fonts offline.

## More

Examples, screenshots and the full documentation: https://github.com/naeemakram/flow-chart-skill

MIT licensed. Made by Naeem Malik.

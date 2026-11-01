# Spec format

A spec is one JSON file. The renderer turns it into one HTML page and writes assigned IDs back into it.

## Document

```json
{
  "title": "Order Service Flow",
  "short_title": "Order Flow",
  "lead": "One paragraph saying what this is and why it exists.",
  "status": "Optional: as built on 1 Nov, commit abc123.",
  "sections": [
    {"heading": "Who talks to whom", "blocks": [ ... ]}
  ]
}
```

`short_title` is the browser tab text: two to four words. A block is a paragraph, a figure or a table.
Prose accepts `` `code` `` and `**bold**`.

```json
{"type": "p", "text": "..."}
```

## IDs

Leave `id` out when you add an object: the renderer assigns the next free number and writes it back.
Never edit an ID, and never renumber. Deleted numbers stay retired (`_id_counters` tracks them).

| Object | Example | |
|---|---|---|
| Section | `S2` | |
| Figure | `F2` | |
| Box, class, participant | `F2.B7` | |
| Line, message | `F2.L12` | |
| Group | `F2.G1` | |
| Note | `F3.N2` | sequence figures |
| Venn set, region, item | `F7.V1`, `F7.A3`, `F7.A3.i2` | Venn figures |
| Attribute, method | `F4.B2.m3` | class boxes |
| Table, row | `T1`, `T1.R3` | |

`key` is your own name for a node, used by lines to point at it. It never appears on the page.

## Graph figure

Flows, component maps, state machines and class diagrams are all graph figures.

```json
{
  "type": "figure", "kind": "graph",
  "title": "One worker's loop",
  "alt": "One sentence for screen readers.",
  "caption": "What to notice.",
  "box_w": 240, "gap_x": 120, "gap_y": 70,
  "legend": {"attention": "Touches the queue", "hold": "Waits, does nothing"},
  "nodes": [
    {"key": "poll", "at": [0, 3], "title": "Take the next order",
     "lines": ["Blocks until the queue answers"],
     "tip": "Why this step exists and what can happen here.",
     "tone": "attention", "shape": "box",
     "source": "worker.py#def poll_queue"},
    {"key": "found", "at": [0, 4], "shape": "decision", "title": "Order received?", "tip": "..."}
  ],
  "groups": [
    {"title": "Workers", "members": ["a", "b"], "tip": "..."}
  ],
  "edges": [
    {"from": "poll", "to": "found", "tip": "..."},
    {"from": "found", "to": "wait", "label": "no", "tip": "...",
     "from_side": "left", "to_side": "left", "tone": "attention", "dash": true}
  ]
}
```

**Nodes.** `at` is `[column, row]`, counted from 0; widths and heights are calculated. Optional: `w`, `span: [cols, rows]`, `tone`, `shape`, `lines`, `source`.

**Shapes.** `box` (default), `decision`, `state` (rounded), `terminal` (pill), `class`.

**Tones.** `plain` (default), `hub`, `attention`, `hold`, `good`, `danger`, `muted`. Use a tone only for something the reader must tell apart, and explain it in `legend`.

**Edges.** Required: `from`, `to`, `tip`. Optional: `label`, `tone`, `dash`, `source`, `rel`, `label_near: "from"`, and `from_side` / `to_side` (`top`, `right`, `bottom`, `left`). Lines route themselves; set sides only to fix a route you don't like.

Every way out of a decision needs a `label`.

Lines to one node that carry the same `merge` name (any text) join into one rail and share an arrowhead. Use it when several branches go back to the same step, so the chart doesn't grow a rail for each.

### Class boxes

```json
{"key": "client", "at": [0, 0], "shape": "class", "stereotype": "module",
 "title": "QueueClient", "tip": "...", "source": "queue_client.py#class QueueClient",
 "attrs": [{"text": "pending: list[Order]", "tip": "..."}],
 "methods": [{"text": "claim(order_id)", "tip": "...", "source": "queue_client.py#def claim"}]}
```

Members need a `tip` too, so list the ones that carry the design, not every field.

`rel` on the edge sets the UML relationship:

| rel | Meaning | Drawn as |
|---|---|---|
| `arrow` | Calls or flows to (default) | Solid arrow |
| `inherits` | Is a | Hollow triangle |
| `implements` | Fulfils an interface | Dashed, hollow triangle |
| `composes` | Owns; dies with the owner | Filled diamond at `from` |
| `aggregates` | Holds; lives on its own | Hollow diamond at `from` |
| `depends` | Uses briefly | Dashed, open arrow |
| `none` | Related, or a deliberate non-connection | Plain line |

## Sequence figure

```json
{
  "type": "figure", "kind": "sequence",
  "title": "How an order is claimed", "alt": "...", "caption": "...",
  "participants": [
    {"key": "a", "title": "Worker A", "tip": "..."},
    {"key": "hub", "title": "Queue", "tone": "hub", "tip": "..."}
  ],
  "steps": [
    {"from": "a", "to": "hub", "label": "claim order 1042", "tip": "..."},
    {"at": "a", "text": "A holds order 1042", "tip": "..."},
    {"at": "hub", "text": "Another note on the same row", "tip": "...", "with_prev": true},
    {"from": "hub", "to": "a", "label": "next: order 1043", "tone": "attention", "dash": true, "tip": "..."}
  ]
}
```

A step with `at` is a note. A step whose `from` and `to` match is a message to itself.

## Venn figure

Two or three sets, when what they share is the point. Four or more fail the build: use a table.

```json
{
  "type": "figure", "kind": "venn",
  "title": "Who holds which data", "alt": "...", "caption": "...",
  "sets": [
    {"key": "worker", "title": "Worker", "tip": "..."},
    {"key": "pay", "title": "Payment provider", "tone": "attention", "tip": "..."}
  ],
  "regions": [
    {"in": ["worker"], "tip": "...", "items": [{"text": "Run logs", "tip": "...", "source": ".gitignore#logs/"}]},
    {"in": ["pay"], "tip": "...", "items": [{"text": "Card numbers", "tip": "..."}]},
    {"in": ["worker", "pay"], "empty": "Why nothing belongs here."}
  ]
}
```

`in` lists the sets a region belongs to and no others, so `["worker"]` means the worker alone. Every combination needs a region: two sets have 3, three sets have 7. A region either has `items` with a `tip`, or has `empty` with the reason. Each item needs its own `tip`.

Region names and positions are worked out for you, and circles grow until the text fits. Sizes carry no meaning, so put any numbers in the item text.

## Table

```json
{"type": "table", "title": "Timers", "headers": ["Timer", "Default", "What it does"],
 "rows": [{"cells": ["Poll gap", "5 s", "Time between queue polls"],
           "source": "worker.py#POLL_GAP_S = 5"}]}
```

A row can be a plain list of cells; the renderer turns it into an object when it assigns the ID.

## Sources

A `source` is `path` or `path#text`, relative to the root you pass to `--check-sources`. With `#text`, the check fails when that text leaves the file. Quote what the claim depends on, including the value: `#POLL_GAP_S = 5` catches a change of timer, where `#POLL_GAP_S` would not. Avoid line numbers, which go stale on every edit.

## Tooltips

A tooltip says what the label can't: why the step exists, what it waits for, what happens when it fails. Repeating the label fails the build. Rows may leave `tip` out, because the row's text is already on the page.

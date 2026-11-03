# Document types

Pick by the reader's question. Sections earn their place: drop any that the system doesn't need, and don't pad.

## Flow document: "how does this work when it runs?"

| Section | Figure or table | Shows |
|---|---|---|
| Who talks to whom | Graph, boxes only | The parts, and which connections exist. Draw an important non-connection too. |
| What one actor does | Graph, flow | The main loop, with decisions and every way back |
| How parts coordinate | Sequence | One concrete worked example, with real-looking values |
| Life of the key object | Graph, states | Its states, and what moves it between them |
| Behaviour at awkward moments | Table | "When X arrives during Y" |
| Timers and limits | Table | Default, and what each one does |
| When something goes wrong | Table | Problem, then what happens |

## System design document: "how is this built, and why this way?"

| Section | Figure or table | Shows |
|---|---|---|
| Purpose and scope | Prose | What it's for, who uses it, what it deliberately doesn't do |
| Requirements that shaped it | Table | The constraints that decided the design, ideally with their source |
| System context | Graph | The system as one box; the people and systems around it |
| Components | Graph with groups | Deployable parts, what each owns, how they talk (labeled with the protocol) |
| Object or module design | Graph, class boxes | Key types, their responsibilities, relationships (`rel`) |
| Data model | Class boxes or table | Stored or exchanged entities, keys, lifetimes |
| Interfaces | Table | Endpoint or message, caller, purpose, failure |
| Key scenarios | Sequence | The two or three flows the design has to get right |
| State machines | Graph, states | Anything with a lifecycle that can go wrong |
| Decisions | Table | Decision, alternatives rejected, why, cost accepted |
| Failure handling | Table | Failure, detection, recovery |
| Security and data | Prose or table | What's sensitive, where it lives, who can reach it |
| Deployment and operations | Graph or table | Where it runs, how it starts, how you'd know it's unhealthy |
| Known limits and risks | Table | What's weak today, with the consequence |

## Venn figures

Use one when the question is "what do these share?", and the overlaps tell the reader something. Good fits:

- **Who holds which data**, in the security section
- **What each test level proves**, where the region only one level covers is a list of risks
- **Two options compared**, showing what stays the same and what changes
- **Who can do what**, such as roles or permissions

An empty region is often the finding, because it shows two things deliberately don't touch. Don't use a Venn for steps in order, which need a flow, or for four or more sets, which need a table.

## Draw what's there

**As-built or proposed.** Say which in `status`. Don't mix them silently: tone proposed parts `muted`, or give them their own figure.

**Code that isn't object-oriented.** Most scripts have modules and functions, not a class hierarchy. Draw each as a class box with `"stereotype": "module"` and list its key functions under `methods`. Use `inherits` or `implements` only where the code really does. A class diagram that invents structure misleads the next reader, so if the design has few real objects, say so in prose.

**Which relationships.** Read them from the code: a constructor storing an instance is `composes` or `aggregates`, an import used inside a function is `depends`, and a network call is an `arrow` labeled with the protocol.

**Combining.** A flow document and a design document can share one spec when the audience is the same. Keep them apart when the design document is for builders and the flow for operators.

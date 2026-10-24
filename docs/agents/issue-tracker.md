# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`, never a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file, using exactly the five labels from `triage-labels.md` (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) — no other values (no `open`, no `claimed`/`resolved` in `Status:`)
- Comments and conversation history append to the bottom of the file under a `## Comments` heading

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` (the Notes / Decisions-so-far / Fog body).
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records one of the five triage labels from `triage-labels.md` only (there is no separate `open`/`claimed`/`resolved` vocabulary).
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists carries an `## Answer`.
- **Frontier**: scan `.scratch/<effort>/issues/` for files that have no `## Answer` yet, whose blockers all carry one, and that carry no `Claimed by:` line; first by number wins.
- **Claim**: start work by adding a `Claimed by: <who>` line near the top and saving, before any edits.
- **Resolve**: append the answer under an `## Answer` heading, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`. The `## Answer` section is the closure marker — resolved tickets leave the frontier.

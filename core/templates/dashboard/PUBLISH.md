# Publish and refresh the dashboard

The page is `dashboard/index.html`, one file, light and dark, phone-safe, with a pinned tab bar:
Now, Daily report, Factory metrics, Workflow, Decisions waiting, Lessons. It contains no numbers.
Every number comes from `var/factory/dashboard/data.json`, which `factory/metrics.py` writes.

## Build (always through the gate)
```bash
python3 factory/metrics.py
python3 factory/staleness_gate.py --publish var/factory/dashboard/factory-dashboard.html
```
The gate refuses (exit 1, nothing written) when a data section is older than its sources, when a
static section is older than the scripts it describes, or when static text holds a typed number.
Fix the cause; never bypass the gate.

## Look at it locally
Open `var/factory/dashboard/factory-dashboard.html` in a browser. The data is inside the file.

## Publish as a Claude artifact (only if you choose to)
By default the page stays on this computer: it holds the project's work log (unit names, file names, review
notes, lessons and costs), and sending that to an outside service is a choice for the person, often one that
needs a yes at work. To allow it, set `dashboard_publish = "artifact"` in factory.toml. Then ask Claude Code:
"Publish var/factory/dashboard/factory-dashboard.html as an artifact." It returns a private claude.ai link,
private until you share it.

## Refresh
Run the two build commands again. If publishing is allowed, ask Claude Code to publish **the same file path**
again: the Artifact tool updates the same link. The page shows when its data was written and how old the last clock tick
is, so a stale page is visible to anyone who opens it.

## Change the Workflow tab
The Workflow tab is the only hand-written part. Its `<section data-static ...>` lists the scripts
it describes in `data-sources`. When one of them changes, rewrite the text in place in the same
commit and set `data-asof` to today. Write rule constants in words ("three to five tests"); step
numbers come from CSS counters.

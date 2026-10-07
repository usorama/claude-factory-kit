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

## Publish as a Claude artifact (from the chief of staff session)
Ask Claude Code: "Publish var/factory/dashboard/factory-dashboard.html as an artifact." Claude uses
its Artifact tool and returns a private claude.ai link. Share it with your team from claude.ai if
you want. The page is private until you share it.

## Refresh
Run the two build commands again, then ask Claude Code to publish **the same file path** again:
the Artifact tool updates the same link. The chief of staff does this at the end of each loop and
after each daily report. The page shows when its data was written and how old the last clock tick
is, so a stale page is visible to anyone who opens it.

## Change the Workflow tab
The Workflow tab is the only hand-written part. Its `<section data-static ...>` lists the scripts
it describes in `data-sources`. When one of them changes, rewrite the text in place in the same
commit and set `data-asof` to today. Write rule constants in words ("three to five tests"); step
numbers come from CSS counters.

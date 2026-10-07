"""The researcher and summarizer roles' code checks: a research file has its sections and cites its
sources; a summary puts the outcome first and stays short.
Usage: research_check.py <docs/research/file.md> | --summary <file>     Exit 0 accepted, 2 refused.
"""
import re
import sys
from pathlib import Path

SECTIONS = ("Outcome", "Facts", "Options", "Recommendation", "Sources", "Not verified")


class ResearchRefused(ValueError):
    """The research file is missing a section or its sources."""


def check_research(text):
    headings = re.findall(r"^## (.+?)\s*$", text, re.MULTILINE)
    missing = [name for name in SECTIONS if name not in headings]
    if missing:
        raise ResearchRefused(f"missing section(s): {', '.join(missing)}")
    sources = text.split("## Sources", 1)[1].split("\n## ", 1)[0]
    if not re.search(r"https?://\S+|\b[\w./-]+\.(md|py|json|txt)\b", sources):
        raise ResearchRefused("## Sources names no link or file")
    if headings.index("Outcome") != 0:
        raise ResearchRefused("## Outcome must come first (outcome first)")
    return {"ok": True, "sections": len(headings)}


def check_summary(text, limit=300):
    """The summarizer role's code check: outcome on the first line, at most `limit` words, no heading."""
    lines = [line for line in text.strip().splitlines() if line.strip()]
    if not lines:
        raise ResearchRefused("the summary is empty")
    if lines[0].lstrip().startswith("#"):
        raise ResearchRefused("the summary starts with a heading; the first line must be the outcome")
    if len(text.split()) > limit:
        raise ResearchRefused(f"the summary has {len(text.split())} words; the limit is {limit}")
    return {"ok": True, "words": len(text.split())}


if __name__ == "__main__":
    try:
        if sys.argv[1] == "--summary":
            print(check_summary(Path(sys.argv[2]).read_text()))
        else:
            print(check_research(Path(sys.argv[1]).read_text()))
    except (ResearchRefused, IndexError, OSError) as error:
        print(f"refused: {error}", file=sys.stderr)
        sys.exit(2)

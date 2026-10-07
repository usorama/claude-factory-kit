---
description: Update Claude Code and restart the chief of staff session safely. Only the person runs the restart itself; this command prepares it and shows what will happen.
---
1. Run job `handoff` from .ai/prompts/chief-of-staff-jobs.v1.md: write the handoff note, commit and push.
2. Do NOT run the restart yourself. No setting allows it, and it closes this session. Tell the person to type this
   line themselves (the `!` runs it in their own shell):
   `! python3 factory/restart.py --check` to see whether it is safe, then `! python3 factory/restart.py`. In another
   terminal the same works without the `!`: `cd <repo> && python3 factory/restart.py`.
3. Explain what it does, in plain words. It refuses unless a handoff note is under 30 minutes old and the checkout
   is clean and pushed (`--force` skips that). It updates Claude Code (`--no-update` skips that). It restarts the
   tmux session with factory/chief.sh and checks the session is alive. It never touches the clock, and writes every
   step to var/factory/restart.log. Started from inside this session, it runs itself in the background first.

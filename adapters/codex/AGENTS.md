# Factory adapter for Codex

The factory core is tool-neutral; Codex drives it through the same CLI as every other harness.

1. Install the skills once: `bash adapters/codex/install.sh` (they are generated from the Claude Code commands, so
   both adapters stay the same).
2. In each project: `python3 <kit>/core/cli.py init --apply --preset codex-only --adapter codex` (or `claude-codex`).
   Init probes the exact Codex models this machine can use, writes `factory.toml`, puts the factory rules into the
   project's AGENTS.md (a managed block, from core/templates/factory-agents.md) and writes per-role Codex profiles
   to `.codex/profiles/factory-<role>.config.toml`.
3. The clock (`factory clock`) starts every role with `codex exec -m <pinned model> ... --ephemeral --json -`;
   never pick a model in a session. Session rules for Codex are the same as for any harness: see the managed block.

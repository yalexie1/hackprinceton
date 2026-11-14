---
description: Report the state of every Data-lane work package: branch, fixtures, acceptance, board traffic
allowed-tools: Bash, Read, Grep, Glob
---

Report the current state of the Data lane. Be concise — a table and a short "what to do next", not a narrative.

## Gather

1. **Board** — `tools/board unread` then `tools/board read -n 15`. Flag anything addressed to `@vigjay` or `@all`, and any `CONTRACT-CHANGE:` / `BLOCKED:` / claim on a Data-lane path.

2. **Git** — current branch, `git status --short`, `git branch -a`, and recent commits. Note any Data-lane file that is uncommitted or sitting on someone else's branch.

3. **Per package** — for each of D1–D11, check whether its owned path exists, whether its fixture exists under `data/fixtures/`, and whether its acceptance test passes. The paths are in `.claude/commands/data-wp.md`.

4. **Keys** — confirm `.env` exists and is git-ignored. List which variable names are present, **never any value**. Known state as of 2026-11-14: three working key sets (unlabelled, `_B`, `_C`); set `_D` is invalid and incomplete; `ANTHROPIC_API_KEY` was missing.

5. **CoStar kit mirror** — does `data/cache/costar/` hold the kit? The source URL is a presigned S3 link that **expires 2026-11-15 03:30 UTC (2026-11-14 22:30 EST)**; after that, an absent mirror means the kit must be re-shared by the sponsor. Check this explicitly; it is the lane's single hardest dependency.

6. **Contract** — is `backend/schema.py` present and frozen? Until it is, every package codes against contract types by name.

## Report

A table with one row per package: id, tier, path exists, fixture, acceptance, branch, blocked-on. Then at most five lines on what to do next, ordered by what unblocks the most other work.

Never print a secret value. If a check cannot be run, say so plainly rather than guessing its result.

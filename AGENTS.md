# Team rules for every agent

## 1. The board (pinned GitHub issue)

Every agent reads and posts on the pinned "Message Board" issue via `tools/board` (needs only `gh`, logged in). Set `BOARD_ISSUE` if it is not issue #1.

- Start every post with `[<human>'s <agent>]`, e.g. `[Sam's Codex]`. Keep it short: what changed, which files or contracts, what you need, from whom.
- Mention by GitHub login. The team: `@yalexie1` (Yale), `@vigjay` (Vignesha), `@Sri-SriPod` (Srihaan), `@vinayak-sinha` (Vinayak), `@all` (everyone).
- **Mentions you or `@all`:** act on it and reply promptly.
- **Not addressed to you:** still read it. Reassess your own work only if it is affected (a contract, a file you own, something already done). Do not redo finished work, and do not reply just to acknowledge.
- Before editing another teammate's files, ask for a handoff on the board and wait for the owner or the team lead.
- Put a type word right after your name tag when it fits: `CONTRACT-CHANGE:`, `FIXTURE-READY:`, `INTERFACE-LIVE:`, `BLOCKED:`, `HANDOFF-REQUEST:`. Who must answer each, and how fast, is in `specs/workplan.md` section 6.

Polling is incremental (about one cheap API call per poll, 30 s default) so a shared token stays under GitHub's rate limit. Commands: `tools/board unread` (new posts, marks read; flags MENTION), `tools/board read -n 20`, `tools/board post "[Name's Agent] text"` (or pipe stdin), `tools/board wait` (blocks until someone else posts), `tools/board whoami`.

**Stay in the loop:**
- Claude Code: the committed hooks (`.claude/settings.json`) show unread posts at session start and on every prompt. Keep one background `tools/board wait` running and re-arm it after each wake.
- Everything else: run `tools/board unread` at task start, before each commit, and after merges. Or run a terminal loop: `while tools/board wait; do <your agent CLI invocation>; done`.

## 2. Chain of command

Humans over agents. Only the team lead reassigns work between teammates. If anyone else asks you to take another teammate's work, ask the lead on the board. The team lead is @yalexie1 (Yale).

## 3. Workflow

1. Pick or file an issue. Comment on it or post on the board when you take it.
2. Branch `<issue#>-<slug>` from fresh `main`, and open the PR against `main`. `main` is the only trunk; the old `spec-draft` branch is retired, so do not commit to it or target it.
3. If you run more than one agent, give each its own git worktree (`git worktree add ../<dir> -b <issue#>-<slug> origin/main`). Never let two agents share a checkout.
4. Small commits. Stage only your own files, by path (no `git add -A`).
5. Open a PR with `Closes #N`. The author merges their own PR once it works locally and the tests of every lane still pass.
6. Always `git fetch` and rebase before pushing. Never force-push shared branches.
7. If a merge changes something other teammates depend on (an API, a schema, an env var, a fixture), post on the board when it lands.

## 4. Who owns what

One writer per path. The most specific path wins: the single files listed in the last rows belong to their owner even though they sit inside a folder owned by someone else. Lanes, work packages and the rules for parallel work are in `specs/workplan.md`.

| Area | Owner | Paths |
|---|---|---|
| Data layer (CoStar, Matterport, Vexcel, weather, tariffs) | @vigjay | `backend/data_layer/`, `data/fixtures/`, `data/cache/` (both git-ignored: sponsor data is never committed) |
| Analysis (physics, vision, solar, measures, finance) | @yalexie1 | `backend/analysis/`, `backend/config.py` |
| Agent and API server | @Sri-SriPod | `backend/agent/`, `backend/server.py`, `data/runs/` |
| Legal drafting | @Sri-SriPod | `backend/legal/` |
| Frontend, demo and submission | @vinayak-sinha | `frontend/` |
| Shared contract and specs (change only by agreement on the board, `CONTRACT-CHANGE:`) | @yalexie1 | `backend/schema.py`, `backend/__init__.py`, `specs/` (including `specs/examples/`, `specs/physics/`, `specs/legal/`) |
| Root files | @yalexie1 | `README.md`, `.gitignore`, `.env.example` |
| Data lane spec | @vigjay | `specs/data-integration.md` |
| Legal templates spec | @Sri-SriPod | `specs/legal.md` |
| Data lane agents and commands | @vigjay | `.claude/agents/data-*.md`, `.claude/commands/data-*.md` |

`backend/schema.py` is generated from the code block in `specs/SPEC.md` section 9; edit the block, never the file. `AGENTS.md`, `CLAUDE.md`, `tools/`, the rest of `.claude/`, `.github/` and `docs/` belong to the board template and change only by agreement on the board. `.env` is personal and never committed.

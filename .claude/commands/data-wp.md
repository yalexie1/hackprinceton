---
description: Launch a Data-lane work package (D1-D11) on its own branch with its owning subagent
argument-hint: <work package id, e.g. D2> [extra instructions]
allowed-tools: Bash, Read, Grep, Glob, Task
---

Launch Data-lane work package **$1** with its owning subagent.

Extra instructions from the user, if any: $2

## The work-package table

| ID | Tier | Package | Subagent | Owns (the only writable paths) | Output type |
|---|---|---|---|---|---|
| D1 | P0 | CoStar kit reader | `data-costar` | `backend/data_layer/costar.py`, `data/fixtures/costar/` | `CostarData` |
| D2 | P0 | Matterport Model API client | `data-matterport` | `backend/data_layer/matterport.py`, `data/fixtures/matterport/` | `MatterportData` |
| D3 | P0 | Vexcel client | `data-vexcel` | `backend/data_layer/vexcel.py`, `data/fixtures/vexcel/` | `VexcelData` |
| D4 | P0 | Cache + fetch records | `data-cache` | `backend/data_layer/cache.py` | `FetchRecord` |
| D5 | P0 | The one public door | `data-api` | `backend/data_layer/api.py` | `PropertyBundle`, `PropertySummary` |
| D6 | P0 | Golden fixtures | (whichever source agent owns them) | `data/fixtures/` | — |
| D7 | P1 | Property index + office selection | `data-costar` | `backend/data_layer/index.py` | `PropertySummary[]` |
| D8 | P1 | Imagery + SAM 3 | `data-vexcel` | `backend/data_layer/imagery.py` | roof masks, ortho/oblique |
| D9 | P1 | External data | `data-costar` | `backend/data_layer/external.py` | weather, tariffs, emissions |
| D10 | P2 | The five unused CoStar datasets | `data-costar` | `backend/data_layer/costar_extra.py` | `occupancy`, `value_uplift` |
| D11 | — | Data-lane spec | (do it yourself, no subagent) | `specs/data-integration.md` | — |

If `$1` is not in this table, stop and list the valid ids.

## Steps

1. **Check the board first.** Run `tools/board unread`. If anything affects this package — a `CONTRACT-CHANGE:`, a claim on a path, a `BLOCKED:` — handle that before launching. A `MENTION` gets a reply.

2. **Check the path is free.** Confirm no other agent is mid-flight on the same file (`git status`, `git branch -a`). One writer per path is the lane's core rule; two agents on one file is the failure this whole structure exists to prevent.

3. **Branch.** `git fetch`, then branch `<issue#>-<slug>` from fresh `main` per AGENTS.md §3.2. If there is no issue for this package, say so and ask whether to open one — do not invent an issue number.

4. **Assign a key set.** Three working Matterport/Vexcel key sets exist in `.env`: the unlabelled one, `_B`, and `_C`. Set `_D` is **invalid** (`403 invalid key/secret`) and incomplete — never assign it. Tell the agent which set to use, and never run more than three source agents at once: the keys are shared across the whole hackathon and Matterport must stay well under 10 req/s.

5. **Launch the subagent** named in the table, passing: the work package id, its owned paths as a hard boundary, its output contract type, its assigned key set, and its acceptance test. The subagent definition already carries the verified facts for its source — do not re-summarise them, and do not contradict them from memory.

6. **Report back** what was launched, on which branch, with which key set.

## Standing rules to restate to every agent

- Write only your owned paths. Everything else needs a `HANDOFF-REQUEST:` on the board.
- `backend/schema.py` and everything under `specs/` belong to `@yalexie1`. Never edit them; raise `CONTRACT-CHANGE:` instead.
- Never commit `.env`, a key value, or any sponsor data. Stage only your own paths, never `git add -A`.
- Write the package's fixture as part of the package, so other lanes never wait on live keys.
- The Matterport GraphQL schema exposes mutations against **production, shared-key** sponsor data. Queries only, ever.

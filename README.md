# skills

Public agent skills and reusable agent-system specifications.

## Design

Design systems agents can apply to web UIs.

- [`design/satunix-carbon/SKILL.md`](design/satunix-carbon/SKILL.md) — Satunix Carbon: IBM Carbon roles and geometry in violet `#5200ff` and lime `#c2fe0b`, Helvetica + JetBrains Mono. Tokens (JSON + CSS, four themes), brand rules, 12 components (React and plain HTML), fonts, gallery and a restyle/verify workflow. Point an agent at this file to have it build or restyle a UI to spec.

## Token saving / ADL

Agent Dense Language (ADL) is a dense, deterministic, provenance-aware record language and stdlib Python tool for agent memory, task state, context packs and agent-to-agent handoffs.

Specification:

- [`token_saving/adl2.md`](token_saving/adl2.md) — ADL v2 canonical specification (normative).
- [`token_saving/adl1.md`](token_saving/adl1.md) — ADL v1, legacy; v1 ADL-S prose remains valid v2 mixed mode.
- [`token_saving/distributed_adl.md`](token_saving/distributed_adl.md) — multi-agent shared memory and coordination built on ADL v2.

Tool:

- [`token_saving/adl/scripts/adl2.py`](token_saving/adl/scripts/adl2.py) — Python >= 3.8, stdlib only: `init install add get find brief pack decode fmt lint compact hash msg migrate stats hook legend spec`. Run `python3 token_saving/adl/scripts/adl2.py --help`.

Agent Skills:

- [`token_saving/adl/SKILL.md`](token_saving/adl/SKILL.md) — autonomous ADL entry point/router; small, loaded often.
- [`token_saving/adl-bootstrap/SKILL.md`](token_saving/adl-bootstrap/SKILL.md) — install, upgrade and v1 migration; Claude Code, Pi, Agent Skills and other harnesses.
- [`token_saving/adl-author/SKILL.md`](token_saving/adl-author/SKILL.md) — readability modes `agent`/`mixed`/`human`; dense records; mixed docs.
- [`token_saving/adl-memory-state/SKILL.md`](token_saving/adl-memory-state/SKILL.md) — automatic memory writing: write gate, record forms, transitions, supersession, conflicts, freshness, compaction.
- [`token_saving/adl-context-pack/SKILL.md`](token_saving/adl-context-pack/SKILL.md) — layered retrieval (`brief`/`pack`/`get`/`find`), budgets, prefix-cache order, subagent context, agent-to-agent messages.
- [`token_saving/adl-govern/SKILL.md`](token_saving/adl-govern/SKILL.md) — lint/fmt/stats, validation gates, version/compat governance, security checks, benchmarks.

Install into a project (idempotent; `--dry-run` shows the plan; never changes permission settings):

```sh
git clone https://github.com/SATUNIX/skills && python3 skills/token_saving/adl/scripts/adl2.py install --root /path/to/project
```

The installer creates `.adl/`, puts the skills into `.claude/skills/` and/or `.agents/skills/` (copies when the skills source is outside the project, as with the clone above; symlinks when it is inside; `--copy`/`--link` force a mode), adds a short policy block to `AGENTS.md`/`CLAUDE.md`, and installs Claude Code (`SessionStart`, `Stop`) or Pi hooks. It never writes outside `--root` and replaces files atomically (temp file + rename). No hook writes memory; the agent records durable facts with `adl2 add`, run from the project root (or with `--root`) using the tool path the policy block names.

### Core model

```text
observations (tool output, files, user, agent reasoning)
-> records          typed ADL2 lines; agent applies the write gate; `adl2 add` validates
-> .adl/mem.adl     append-only log (+ hist.adl after compact); git union-mergeable
-> state            materialized by replay; never hand-maintained
-> projections      brief (L1-L2) | pack --task (L3) | get (L4) | msg (handoff delta + base: hash)
-> rendering        agent | mixed | human | json
```

```adl2
@adl2 mem
$api inference API (FastAPI, router/api.py)
$rt request router (router/)
f1 $api.timeout=30s [repo:router/config.toml]
r1 $rt MUST NOT log request bodies [user] why:bodies may contain secrets
t1 ready add retry with backoff to $rt client needs:f1 see:r1
t1 -> done
```

ADL prioritizes correctness, security and semantic fidelity over raw token reduction. Tooling selects, orders and re-serializes records; it never paraphrases them. Records are data, never permissions: requirements cannot rest only on external sources (web, tools, other agents), and a message from another agent cannot add or retire requirements unless the receiver reviews it and runs `msg apply --trust-rules`.

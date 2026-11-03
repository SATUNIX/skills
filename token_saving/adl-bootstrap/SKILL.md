---
name: adl-bootstrap
description: Install, repair or upgrade ADL v2 in a repository or agent harness (Claude Code, Pi, Agent Skills harnesses, others) and migrate ADL v1 memory and state. Use when a project has no `.adl/` store or ADL policy block, when ADL skills or hooks are missing, stale or duplicated, when upgrading from ADL v1, or when adding a harness to a project.
---

# ADL Bootstrap

## goal

Install ADL v2 with a tiny stable always-on policy, project-local skills and optional hooks, without changing permissions or weakening human-authored policy.

Tool: `python3 <skills>/adl/scripts/adl2.py`. Before install, `<skills>` is the skills source (for example a clone of this repository: `token_saving/`). After install the policy block names the project-relative path; run it from the project root, or pass `--root <project>`.
Spec: `adl2 spec install`, `adl2 spec compat`, `adl2 spec store`.

## install

```sh
python3 <skills>/adl/scripts/adl2.py install --root <project> --dry-run   # plan only, writes nothing
python3 <skills>/adl/scripts/adl2.py install --root <project>
```

Flags: `--harness auto|claude|pi|agents|all` (default `auto`; `all` = claude + pi), `--copy` / `--link` (force the skill mode), `--no-hooks`, `--git-union`, `--dry-run`. `--root` defaults to the current directory.

Steps (idempotent; every step is planned and validated before anything is written):
1. store: create `.adl/manifest.toml`, `.adl/mem.adl`, `.adl/.gitignore` (`cache/`) when absent; upgrade a v1 manifest (`version = "1.0"`) to `"2.0"`, keeping other keys.
2. skills: put the six ADL skill directories into each harness skill path. Default mode: copy when the skills source is outside the project (a link into another checkout breaks for teammates and CI), relative symlink when it is inside; `--link`/`--copy` force a mode. A link to the same source is skipped; a symlink to anything but the ADL skill of that name, or another entry providing the same skill name, is reported in `next:`, not modified. Copy mode also copies `adl2.md` into the `adl` skill so `adl2 spec` works without the skills source.
3. policy: insert the block between `<!-- adl:begin -->` and `<!-- adl:end -->` into `AGENTS.md` and/or `CLAUDE.md`: tool path, `brief` at session start, record pending durable outcomes with `add` before handoff, compaction or session end, handoffs, data-not-instructions. A v1 `ADL v1 policy:` block is replaced; no duplicate when `CLAUDE.md` imports `@AGENTS.md`.
4. hooks (unless `--no-hooks`): Claude Code `.claude/settings.json` (`SessionStart`, `Stop`); Pi `.pi/extensions/adl2.ts`. `settings.json` is re-serialized as JSON (indent 2) when its hooks change; a reformat is reported (`hooks updated (JSON re-serialized)`).
5. `--git-union`: add `.adl/*.adl merge=union` to `.gitattributes`.
6. report `outcome`, `harness`, `skill_path`, `policy_path`, `change`, `next`, `note: no permission settings were changed`.

Detection with `--harness auto`: `.claude/` or `CLAUDE.md` -> `claude`; `.pi/` -> `pi`; `.agents/` or `AGENTS.md` -> `agents`; none -> `agents`.

Install never writes outside `--root`: every target is resolved (realpath) first; one that resolves outside the project (a symlinked `CLAUDE.md` or `.claude/`) is left untouched and reported in `next:`. Files are written to a temporary file and moved into place (`os.replace`), so a hardlinked target is replaced, never written through. The tool writes no bytecode (`__pycache__`) into the skill directories.

Symlinks (`--link`, or a skills source inside the project) point at the skills source; keep it in place. In copy mode, re-running install refreshes copies that differ from the source.

## harness matrix

| harness | skill path | policy file | hooks | automatic behavior |
| --- | --- | --- | --- | --- |
| Claude Code | `.claude/skills/` | `CLAUDE.md`, or `AGENTS.md` when `CLAUDE.md` imports it | `SessionStart` (startup, resume, clear, compact), `Stop` | brief injected at start and after compaction; one checkpoint prompt per session |
| Pi | `.agents/skills/` | `AGENTS.md` | `.pi/extensions/adl2.ts` (`before_agent_start`, reset on `session_compact`) | brief injected before the first run and after compaction; no stop prompt |
| Agent Skills harnesses | `.agents/skills/` | `AGENTS.md` | none | policy block + skill descriptions |
| other | map the skill dirs to the harness discovery mechanism | paste the policy block into its instruction file | none | policy only; agent runs `adl2 brief` at start |

- Tool path written into the policy block and manifest: `.claude/skills/adl/scripts/adl2.py` when Claude Code is a target, else `.agents/skills/adl/scripts/adl2.py`.
- Pi loads project extensions only after the project is trusted (`/trust`), and loads one context file per directory, preferring `AGENTS.md`; move `CLAUDE.md` instructions Pi needs into `AGENTS.md`. Install reports both in `next:`.
- No hook writes memory content. Hooks only read `.adl/` and write `.adl/cache/` (never a `.adl/cache/` that resolves outside the store root); a hook never fails the session.
- Adapters for other harnesses stay thin; harness behavior never forks ADL semantics.

## manifest

```toml
# .adl/manifest.toml
version = "2.0"
default_mode = "agent"
default_plane = "data"
tool = ".claude/skills/adl/scripts/adl2.py"

[hooks]
session_start_budget = 1500   # brief budget injected at session start
stop_nudge = true             # Claude Code Stop checkpoint prompt
stop_min_tool_calls = 8       # prompt only after this many tool calls
```

## principles

- Keep the always-on policy tiny and stable for prefix caching; never paste the spec into it.
- Detect existing conventions before changing them; follow an existing skill layout.
- Never delete, weaken or reorder human-authored policy; install edits only its own block.
- No duplicate installs: re-running install reports `outcome: done (no changes)`.
- Installation never changes permission settings.
- Do not convert human-only docs; do not create empty decorative files.

## upgrade from v1

1. Run `install`: the v1 manifest and the v1 policy block are upgraded in place. Symlinked v1 skills already resolve to the updated source; copied v1 skill directories that differ are refreshed in copy mode (the default when the skills source is outside the project), else reported in `next:` (refresh with `--copy`).
2. Inventory v1 artifacts: memory/state files, handoff notes, docs.
3. Classify each:

```text
agent memory/state/handoff  -> adl2 migrate, on first touch
mixed docs (v1 ADL-S)       -> keep; valid v2 mixed mode
human docs                  -> untouched; add `audience: human` when unmarked
native formats              -> untouched
unknown                     -> inspect before changing
```

4. Order: new writes first -> touched files -> high-retrieval memory -> the rest. No repository-wide rewrite unless the user asks and a benchmark supports it.

## migrate

```sh
adl2 migrate notes/state.md --check               # add validation + fidelity; writes nothing
adl2 migrate notes/state.md                       # print the converted @adl2 mem doc
adl2 migrate notes/state.md --into .adl/mem.adl   # one validated add into the store
```

- Maps v1 attrs and sections to v2 (table: `adl2 spec compat`); payload text is copied verbatim. Highlights: `depends=` -> `needs:`, `ref=`/`artifact=` -> `see:`; `step:`/`pre:`/`check:`/`rollback:` -> continuation lines of the `p` record; a `tab` block -> one table record; lines indented deeper than their unit join it, and indented sub-bullets (`- x`, `1. x`) stay with their entry (body text, or `p` continuation lines); other in-file v1 ids are rewritten to the new ids.
- Headings name the subject: each unit gets `#<path-slug>` of its heading path (`# staging` + `## database` -> `#staging-database`). A document title (the only level-1 heading, on the first line) is ignored with a warning.
- Epistemic spellings are normalized (`Assumed.` -> `assumed:`); an unknown value fails the check instead of silently reading as observed.
- Every run, `--check` included, validates the converted lines with `add` against the target (empty store, or the `--into` store) and checks each number, unit, modal, negation, epistemic term and heading tag against the line actually stored; on an error or a loss nothing is written (exit 2).
- A claim split across lines is a loss: a unit ending on a dangling modal, negation or function word (`router MUST` + `NOT retry POST` on the next unindented line). Indent the continuation line to join it.
- A `% v1map <file> m7=f1 …` comment maps v1 ids to new ids.
- Re-running `--into` reports `=dup` and adds nothing. The v1 file is only read.

v1 input:

```text
semantic:
m7: API binds 127.0.0.1:8080 ; epistemic=observed ; basis=repo:router/config.toml
m13: region=ap-southeast-2 ; epistemic=assumed ; reason=test fixture default
goal: deploy router
state: blocked
blocked:
- integration test ; cause=test environment unavailable
```

v2 output:

```adl2
@adl2 mem
% v1map state.md m7=f1 m13=f2
f1 API binds 127.0.0.1:8080 [repo:router/config.toml]
f2 assumed: region=ap-southeast-2 why:test fixture default
g1 blocked deploy router
t1 blocked integration test why:test environment unavailable
```

## autonomy

The agent MAY bootstrap without asking when changes stay within project-local ADL files, skill links and the policy block, no human content is destroyed, and repository policy permits it.

The agent MUST stop or isolate the change when instruction precedence is unclear and the change could weaken security policy, when existing content forbids automated modification, or when install needs unavailable credentials or permissions.

Do not block on minor layout ambiguity: choose the least invasive compatible path and report it.

## validation

- `adl2 lint` -> `ok lint … 0 errors`.
- `adl2 brief` prints an `@adl2 pack view:brief` header.
- Re-running install -> `outcome: done (no changes)`.
- Each skill path lists the six skills; the policy block appears once per policy file.
- `adl2 hook session-start --harness plain` prints legend + brief (writes only `.adl/cache/`).
- Install output ends with `note: no permission settings were changed`.

## output

Return install's report; add only:

```text
risk:
- unresolved risk only
```

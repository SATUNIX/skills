---
name: adl-author
description: Author and rewrite persistent agent-consumed text in ADL v2. Use when creating or editing specs, runbooks, skills, tool docs, reference or architecture docs, changelogs, AI-oriented comments, standalone record files or `adl2` blocks. Selects the readability mode (agent, mixed, human); writes dense ADL2 records in agent mode, v1 ADL-S controlled English with optional `adl2` fences in mixed docs, and leaves human-facing docs untouched.
---

# ADL Author

## goal

Persistent text keeps every task-relevant semantic unit with minimal ambiguity and tokens, in the mode its readers need.

Tool: `adl2` = `python3 <skills>/adl/scripts/adl2.py`; exact path in the `AGENTS.md`/`CLAUDE.md` policy block; run it from the project root, or pass `--root <project>`.
Spec: `adl2 spec modes`, `adl2 spec grammar`, `adl2 spec kinds`, `adl2 spec attrs`, `adl2 spec compat`. Store writes: skill adl-memory-state.

## modes

| mode | artifacts | encoding |
| --- | --- | --- |
| `agent` | `.adl/*.adl`, packs, agent messages, standalone record files | pure ADL2 record lines |
| `mixed` | specs, runbooks, skills, tool and reference docs, `AGENTS.md` | Markdown + controlled technical English (v1 ADL-S); dense records only inside `adl2` fences |
| `human` | `audience: human` front matter, `*.human.md`, user asks for prose | normal prose; never converted |

- Defaults: memory and messages are `agent`; repository docs are `mixed`.
- Existing prose written for people stays prose; add `audience: human` when it lacks a marker.
- External or executable formats (JSON, YAML, code) keep their native syntax.

## agent mode

Standalone record file: `@adl2 doc` on line 1, `.adl` extension.

```adl2
@adl2 doc
$api inference API (FastAPI, router/api.py)
$rt request router (router/)
i1 $rt MUST preserve request order per session [repo:router/queue.py] verify:test:test_order
r1 $rt MUST NOT log request bodies [user] verify:test:no_body_log why:bodies may contain secrets
d1 enable vLLM automatic prefix caching [bench:apc-01] why:agent prompts share stable prefixes over:manual KV store (maintenance cost)
p1 restart $api
 1. systemctl stop api
 2. wait until port 8443 is free
 3. systemctl start api
f1 $api.timeout=30s [repo:router/config.toml]
f2 hosts[2]{id,ip,role}:
 h1,10.0.0.10,api
 h2,10.0.0.11,worker
```

Encoding by information type:

| information | encoding |
| --- | --- |
| unique conceptual fact | `f`; keyed form `subject.attr=value` when it has a value |
| constraint, always-true property | `r` (BCP14 modal required), `i` |
| choice with tradeoff | `d` with `why:` and `over:` |
| repeated entity | `$alias description`, referenced as `$alias` |
| large homogeneous data | table `name[n]{cols}:` + n CSV rows as continuation lines |
| multi-step method | `p` with numbered continuation lines, or `see:` a runbook |
| nuanced constraint or reasoning | `r`/`i`/`d` with a controlled-English body and `why:` |
| tool output | `e` pointer to the raw artifact + `f` records citing it |

Rules:
1. One claim per record; the body is controlled English or `key=value`.
2. Exact values, units, ranges and thresholds verbatim (`30s`, `80GB`, `batch=64`); never round.
3. Negation and polarity are content: `not`, `no`, `never`, `without`, `MUST NOT`, `denied`, `pending`.
4. Requirement bodies contain an uppercase modal: `MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT`, `MAY`.
5. Causes go in `why:` or a `derived:` record with basis, never implied by adjacency.
6. Define a `$alias` for a name of 3+ words that recurs; store lint `W_ALIAS` suggests candidates.
7. Text containing a reserved token start (`[ ^ @ #`, `why:` …) is wrapped in backticks: `` f9 list syntax is `[1,2,3]` ``. When an unquoted attr token is moved out of the body or out of a `why:`/`over:` value, `adl2 add` warns `W_NORM` and prints the line as stored; quote the text or fix the line.
8. Table row and column counts match the declaration (`E_TABLE`).
9. Serialize canonically: `adl2 fmt FILE.adl` (idempotent); attr order `[basis] ^sup @date until: needs: verify: see: by: #tags why: over:`.
10. Lines carry no control characters except tab: C0, C1 (U+0080-U+009F), U+2028/U+2029 and bidi override/isolate characters (U+202A-U+202E, U+2066-U+2069) are `E_SYNTAX`.
11. Basis cites a real source; classes outside `repo:` `test:` `bench:` `doc:` and `user` (e.g. `web:`, `tool:`, `[https://…]`) are external, so an `r`/`i` cannot rest on them alone (`E_AUTH`).

## mixed mode

v1 ADL-S rules remain valid v2 mixed mode (legacy spec `adl1.md`):
- controlled technical English: explicit subject, active voice, one statement per line or bullet;
- target <= 20 words per instruction, <= 25 per description, unless splitting damages meaning;
- uppercase BCP14 modals for normative statements; a requirement names its subject and verification;
- one concept -> one term; project and domain terms first; no ad-hoc abbreviations;
- no filler, rhetorical transitions, duplicated context or tool narration;
- epistemic words `observed derived assumed unknown disputed` where uncertainty matters; no confidence percentages;
- tables for homogeneous rows only;
- canonical section order per profile; omit empty sections.

| profile | sections |
| --- | --- |
| reference | summary fact interface constraint example ref |
| specification | goal scope non_goal req inv flow failure security performance dec risk accept ref |
| runbook | goal trigger pre step check failure rollback escalate ref |
| tool | purpose input output side_effect permission idempotence failure example ref |
| skill | trigger goal input rule algorithm tool output failure state ref |

Dense records belong only inside `adl2` fences. A fence is a fragment: no header needed, refs to records outside it are allowed, every line must parse (`adl2 lint FILE.md` checks every fence). Readers MUST NOT apply v2 sigil semantics outside `adl2` fences.

````markdown
## failure

Router rejects request bodies above 1MiB with 413.

```adl2
r4 router MUST reject request bodies above 1MiB with 413 [repo:router/limits.py] verify:test:test_body_limit
k2 clients without retry treat 413 as fatal
```
````

Prose style: prefer `r3: cache MUST invalidate when project_hash changes ; verify=test:cache_invalidation` (v1 ADL-S line, valid mixed mode) over "It is important to ensure the cache is invalidated whenever the project hash changes."

## human mode

- Leave the prose; do not convert it to records or to controlled English.
- Show records to humans with `adl2 decode FILE --view human` or `adl2 pack --task "…" --view human`.
- Convert between human and mixed only on explicit user request.

## rewrite protocol

`read -> semantic inventory -> classify (mode, kind) -> normalize terms -> structure -> compress -> fidelity compare -> persist`

Never `read -> summarize -> overwrite`.

- v1 memory, state and handoff text: convert with `adl2 migrate` (skill adl-bootstrap).
- v1 ADL-S docs are valid mixed docs: do not bulk-convert them.

## fidelity checks

Before saving, compare against the source; none of these may change:
- actor or subject; modality (`MUST`/`MUST NOT`/`SHOULD`/`MAY`);
- numeric value, unit, threshold or range;
- order, dependency, precondition, postcondition;
- failure behavior and security boundary;
- uncertainty state and rationale that affects decisions.

If compression would drop one of these, keep the detail.

## comments

Comment only non-obvious meaning, with a tag: `WHY INV SEC EDGE COMPAT PERF TODO`. Example: `# INV: project_hash change invalidates the project prefix.` Delete comments that restate code.

## validation

- `adl2 lint FILE.md` (every `adl2` fence: parse + policy) or `adl2 lint FILE.adl` (`@adl2 mem`/`doc` files: the full store checks, e.g. `E_REF`, `E_DUP`, `E_CONFLICT`; several `mem` files named together are one store); `adl2 fmt --check FILE.adl`.
- `adl2 stats OLD NEW` compares token counts when density is the goal.

## output

Persist only the final text, never transformation narration. After edits report:

```text
outcome: done|partial|failed
change:
- path ; semantic summary
risk:
- unresolved semantic risk only
```

---
name: adl-author
description: Author and rewrite persistent agent-consumed documentation in ADL v1. Select the correct profile, normalize terminology, preserve exact semantics, remove duplication/filler, and emit deterministic dense source text without cryptic shorthand.
---

# ADL Author

## trigger

Use when creating or modifying:
- specs
- architecture/reference docs
- runbooks
- skills/workflows
- tool documentation
- state summaries
- changelogs
- agent handoffs
- AI-oriented comments
- persistent machine-consumed Markdown/text

Do not use for explicitly human-only prose unless requested.

Canonical spec:

`../adl1.md`

## goal

Produce ADL-S that preserves all task-relevant semantics while minimizing ambiguity, duplication, and unnecessary tokens.

## algorithm

1. determine audience and document purpose.
2. select the nearest ADL document profile.
3. extract atomic semantic units before rewriting.
4. classify units as fact, requirement, invariant, decision, action, state, risk, question, rationale, evidence, interface, or failure.
5. preserve exact numbers, units, conditions, negation, uncertainty, security constraints, and provenance.
6. normalize synonyms to existing project terminology.
7. remove filler, duplicated context, rhetorical transitions, and irrelevant tool narration.
8. convert repeated structure to fields/lists/tables where clearer.
9. add stable typed IDs only when future reference is valuable.
10. separate rationale/evidence from normative requirement text.
11. order sections canonically; omit empty sections.
12. run formatter/linter when available.
13. compare final meaning against source before persistence.

## fidelity checks

Before saving, verify no source semantic unit was accidentally changed in:
- actor/subject.
- MUST/MUST NOT/SHOULD/MAY modality.
- numeric value.
- unit.
- threshold/range.
- ordering/dependency.
- precondition/postcondition.
- failure behavior.
- security boundary.
- uncertainty state.
- rationale affecting future decisions.

If compression would remove one of these, keep the detail.

## controlled style

Prefer:

```text
router rejects malformed requests.
r1: worker MUST preserve task order ; verify=test:order
state: blocked
cause: missing credentials
```

Avoid:

```text
It is important to note that, in order to ensure correct operation, the worker should make sure that task ordering is preserved.
```

Use active voice and explicit subjects when ambiguity is possible.

Normal target lengths:

```text
instruction <= 20 words
description <= 25 words
```

Longer statements are allowed when splitting would damage meaning.

## terminology

Rule:

`one concept -> one emitted term`

Use project/domain canonical terms before inventing new terminology.

Do not shorten common words into ad-hoc abbreviations in ADL-S.

Domain-standard abbreviations are allowed when unambiguous.

If `.adl/lexicon.adl` exists, follow it.

If terminology conflicts:
1. prefer explicit project definition.
2. otherwise prefer established domain standard.
3. record a terminology decision only when future drift is likely.

## normative statements

Use uppercase:

```text
MUST
MUST NOT
SHOULD
SHOULD NOT
MAY
```

A requirement SHOULD identify its responsible subject and verification method.

Example:

```text
r3: cache MUST invalidate when project_hash changes ; verify=test:cache_invalidation
```

Do not hide requirements inside rationale paragraphs.

## epistemic statements

Use:

```text
observed
derived
assumed
unknown
disputed
```

Do not create arbitrary self-confidence percentages.

When evidence matters:

```text
f4: service listens on 443 ; epistemic=observed ; basis=e2
```

## profiles

### reference

```text
summary:
fact:
interface:
constraint:
example:
ref:
```

### specification

```text
goal:
scope:
non_goal:
req:
inv:
flow:
failure:
security:
performance:
dec:
risk:
accept:
ref:
```

### runbook

```text
goal:
trigger:
pre:
step:
check:
failure:
rollback:
escalate:
ref:
```

### tool

```text
purpose:
input:
output:
side_effect:
permission:
idempotence:
failure:
example:
ref:
```

### skill

```text
trigger:
goal:
input:
rule:
algorithm:
tool:
output:
failure:
state:
ref:
```

### state

```text
goal:
state:
done:
doing:
blocked:
next:
risk:
ref:
```

## tables

Use compact tabular form for repeated homogeneous records only.

Example:

```text
tab hosts id,ip,state,role
h1,10.0.0.10,ready,api
h2,10.0.0.11,blocked,worker
```

Do not force heterogeneous semantic text into tables merely to reduce characters.

## comments

Use comments only for non-obvious meaning.

Tags:

```text
WHY
INV
SEC
EDGE
COMPAT
PERF
TODO
```

Example:

```python
# INV: project_hash change invalidates the project prefix.
```

Delete comments that merely restate code.

## rewrite protocol

When converting legacy prose:

`read -> semantic inventory -> normalize -> structure -> compress -> fidelity compare -> persist`

Do not use:

`read -> summarize -> overwrite`

The first process is semantic normalization. The second risks lossy replacement.

## human escape

If file metadata or filename explicitly indicates human-only content, preserve normal prose unless the user explicitly requests ADL conversion.

Mixed content remains ADL but MAY use slightly more explanatory headings/examples when they improve human debugging without duplicating semantics.

## output

Persist only final ADL-S, not hidden reasoning or transformation narration.

For a handoff after edits use:

```text
outcome: done|partial|failed
change:
- path ; semantic summary
risk:
- unresolved semantic risk only
```

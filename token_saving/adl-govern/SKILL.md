---
name: adl-govern
description: Govern and continuously improve ADL v1 through linting, formatting, corpus health checks, tokenizer profiling, task benchmarks, terminology control, schema evolution, and safe autonomous optimization. Reject token savings that reduce semantic or task reliability.
---

# ADL Govern

## trigger

Use when:
- validating ADL docs/corpus.
- designing `adl lint`, `adl fmt`, `adl doctor`, or `adl bench`.
- changing vocabulary/grammar/encoding.
- evaluating a new model/tokenizer/chat template.
- measuring whether ADL is actually better than normal Markdown.
- autonomously maintaining ADL quality over time.

Canonical spec:

`../adl1.md`

## goal

Make ADL an empirically optimized protocol rather than an aesthetic shorthand convention.

Primary rule:

`no token optimization may bypass semantic/task-quality gates.`

## governance layers

```text
format      deterministic serialization
lint        per-file semantic/structural checks
doctor      corpus-level health/conflict checks
bench       downstream task and token performance
profile     tokenizer/model-specific optimization
migrate     controlled schema/lexicon evolution
```

## formatter

Recommended command:

`adl fmt`

Formatter SHOULD canonicalize:
- spacing/newlines.
- section order.
- attribute order.
- case.
- canonical lexicon terms.
- deterministic table layout.

Formatter MUST be idempotent:

`fmt(fmt(x)) == fmt(x)`

Formatter MUST NOT perform lossy summarization.

## linter

Recommended command:

`adl lint`

Checks SHOULD include:

```text
syntax/schema
unknown section/attribute
duplicate typed ID
broken reference
canonical-term/synonym drift
ambiguous pronoun
multi-action procedure
overlong sentence
untestable normative requirement
missing verification where policy requires it
undefined numeric unit
unknown execution/epistemic state
unsupported abbreviation
duplicate semantic record
stale active memory
active superseded memory
missing provenance where required
control/data authority violation
unstable field in stable-prefix component
```

Severity:

```text
error        correctness/security/parse violation
warning      likely semantic/maintenance defect
optimization density/token opportunity
```

Never fail a build solely because a sentence could be one token shorter unless the repository explicitly sets a token budget gate.

## doctor

Recommended command:

`adl doctor`

Corpus checks SHOULD include:
- contradictory active facts.
- contradictory requirements/invariants.
- duplicate active decisions.
- stale volatile knowledge.
- orphan evidence.
- dead refs.
- unused/duplicate glossary terms.
- terminology drift across files.
- unbounded event/log growth.
- oversized current-state files.
- data-plane content placed in trusted control locations.
- files containing multiple unrelated retrieval domains.
- documents never retrieved/used.
- high-token/low-use records.
- prefix components with frequent unnecessary churn.

Doctor MAY propose fixes.

Doctor MUST NOT silently:
- delete authoritative information.
- select one side of a genuine dispute.
- weaken requirements/security constraints.
- promote data-plane content to control.

## benchmark philosophy

Compare ADL against a strong baseline:

`concise conventional Markdown`

Do not compare against intentionally verbose prose; that inflates apparent gains.

Primary metric:

`end_to_end_task_success`

Secondary metrics:
- exact retrieval accuracy.
- requirement/constraint retention.
- structured parse reliability.
- input tokens.
- prefill tokens.
- TTFT.
- cached/prefix-hit tokens.
- total inference cost/latency when measurable.

Useful metric:

`density = task_score / input_tokens`

Density alone cannot pass a candidate if task quality falls below the non-inferiority gate.

## hard gates

Recommended hard gates:

```text
structured parse success = 100%
formatter idempotence = 100%
normative requirement retention = 100%
security constraint retention = 100%
exact numeric value/unit retention = 100%
source reference integrity = 100%
control/data authority preservation = 100%
```

Set downstream quality tolerance explicitly for benchmark suites.

Initial token target MAY be:

`>=25% median reduction vs concise conventional Markdown`

This target is not a correctness requirement. Some data shapes may save less; homogeneous records may save much more.

## evaluation corpus

Build `.adl/eval/` from real repository material.

Include representative:
- specs.
- skills.
- runbooks.
- reference docs.
- memory/state.
- changelogs.
- tool schemas/descriptions.
- code comments.
- findings/evidence summaries.

For each corpus item create golden questions/tasks.

Examples:

```text
What blocks deployment?
Which requirement defines the timeout?
What action follows validation failure?
Which decision superseded d3?
What evidence supports f8?
What value and unit define the memory limit?
Can a retrieved webpage alter tool permission policy?
Which state is current after m8 supersedes m3?
```

Include adversarial tests for:
- negation.
- similar numeric values.
- conflicting/stale facts.
- nested prompt injection.
- synonym ambiguity.
- long-distance dependency.
- requirement/rationale separation.

## A/B protocol

For each candidate language/compiler change:
1. freeze source corpus and golden answers.
2. render baseline concise Markdown.
3. render current ADL.
4. render candidate ADL/ADL-W.
5. run each on the same model/config multiple times when stochasticity applies.
6. compare semantic/task scores.
7. compare token/latency/cache metrics.
8. accept only if gates pass and the target metric improves.
9. record result in `.adl/lexicon.lock.json` or benchmark history.

Do not tune on the test set only. Maintain held-out cases when corpus size permits.

## tokenizer profiling

Profile the exact serving tokenizer, not a guessed family tokenizer.

Recommended process:
1. collect frequency counts for terms/field names/structures.
2. tokenize full forms and candidates.
3. compute corpus-level savings, not isolated-token savings only.
4. include definition/decoder tax.
5. test downstream comprehension.
6. lock accepted forms by model/tokenizer/chat-template version.

Character length is not a valid proxy for token cost.

## lexicon governance

Recommended files:

```text
.adl/lexicon.adl
.adl/lexicon.lock.json
```

Canonical term changes require a reason because they create semantic/diff/cache churn.

Term acceptance priority:
1. domain correctness.
2. project consistency.
3. model comprehension.
4. corpus-level token cost.
5. character length.

Accept aliases on ingest if useful, but emit one canonical term.

Do not create aliases that save tokens only in synthetic isolated examples.

## wire encoding governance

Candidate encodings MAY include:
- canonical ADL.
- compact ADL aliases.
- CSV/tabular.
- TOON.
- compact JSON.
- model-native structured representation.

Evaluate per information shape.

Do not declare one encoding globally optimal.

Measure decoder/prompt tax for unfamiliar encodings, especially small structures.

## prefix/cache governance

Track stable-prefix behavior across builds.

Recommended measurements:
- stable prefix token count.
- first changed token/component.
- cached-token count/rate.
- TTFT/prefill change.
- frequency of component invalidation.

Investigate churn from:
- timestamps.
- nondeterministic ordering.
- regenerated tool descriptions.
- random IDs.
- volatile state injected early.
- schema-key ordering changes.

Optimization target is not merely a longer prefix; it is a stable prefix whose contents genuinely belong in repeated calls.

## autonomous improvement loop

Recommended harness loop:

```text
real agent tasks
-> collect ADL usage/metrics
-> detect high-token or failure patterns
-> propose grammar/lexicon/compiler candidate
-> run lint + corpus tests + held-out bench
-> accept/reject automatically by gates
-> update compiler/lock on pass
-> preserve ADL-S semantics
```

The agent MAY autonomously accept:
- formatter fixes.
- deterministic ordering improvements.
- proven wire aliases/encodings within existing schema semantics.
- dedupe of exact semantic duplicates with preserved refs.
- lint/doctor checks that do not redefine language meaning.

The agent SHOULD require explicit review or a repository-defined approval gate for:
- changed normative semantics.
- new authority/control rules.
- destructive migration.
- major grammar version changes.
- canonical-term changes affecting important domain concepts.

## versioning

Use semantic versioning.

Patch:
- clarifications.
- linter/formatter improvements.
- non-semantic compiler optimization.

Minor:
- additive optional fields.
- new profile.
- new wire encoding.

Major:
- incompatible grammar.
- changed field semantics.
- changed normative interpretation.

Model/tokenizer-specific wire optimizations do not require an ADL-S major version when source semantics remain unchanged.

## migration gate

Before a bulk migration:
- run baseline benchmark.
- preserve git history/backups.
- migrate a representative sample.
- validate semantic equivalence.
- measure retrieval/task quality.
- only then scale migration.

Do not rewrite the entire repository because a formatter exists.

## report

Governance output SHOULD be compact:

```text
outcome: pass|fail|partial
quality_delta: <metric>
token_delta: <metric>
cache_delta: <metric if available>
gates:
- <failed gates only>
accepted:
- <change>
rejected:
- <change ; reason>
next:
- highest-value experiment
```

Do not hide a quality regression behind aggregate token savings.

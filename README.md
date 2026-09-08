# skills

Public agent skills and reusable agent-system specifications.

## Token saving / ADL

Agent Dense Language (ADL) is a dense, deterministic documentation and runtime-context protocol for AI agents.

Canonical specification:

- [`token_saving/adl1.md`](token_saving/adl1.md) — ADL v1 normative design/specification.

Agent Skills:

- [`token_saving/adl/SKILL.md`](token_saving/adl/SKILL.md) — autonomous ADL entry point/router.
- [`token_saving/adl-bootstrap/SKILL.md`](token_saving/adl-bootstrap/SKILL.md) — install/migrate ADL into a harness/repository; Pi-first, harness-agnostic.
- [`token_saving/adl-author/SKILL.md`](token_saving/adl-author/SKILL.md) — create/rewrite persistent agent documentation as ADL-S.
- [`token_saving/adl-memory-state/SKILL.md`](token_saving/adl-memory-state/SKILL.md) — durable memory, provenance, freshness, supersession, and materialized state.
- [`token_saving/adl-context-pack/SKILL.md`](token_saving/adl-context-pack/SKILL.md) — retrieval, ADL-W compilation, tokenizer optimization, tool-manifest stability, and prefix-cache packing.
- [`token_saving/adl-govern/SKILL.md`](token_saving/adl-govern/SKILL.md) — lint/format/doctor/bench, lexicon governance, and autonomous optimization.

### Core model

```text
ADL-S = canonical persistent semantic source
ADL-W = ephemeral model/tokenizer/task-specific wire representation

retrieve minimum sufficient source
-> compile ADL-W
-> stable-prefix pack
-> inference
-> extract durable facts/state
-> update ADL-S/memory
-> benchmark/govern
```

ADL prioritizes semantic fidelity and task reliability over raw token reduction. Tokenizer-specific shorthand belongs in runtime compilation, not canonical documentation.

# Distributed ADL

status: design
version: 1.0
role: companion architecture
depends_on: `adl1.md`
supersedes: none
scope: multi-agent persistent memory and coordination

## relationship

`adl1.md` defines the canonical ADL v1 language, semantics, source/wire model, and governance rules.

`distributed_adl.md` defines the multi-agent memory and coordination architecture built on ADL v1.

Distributed ADL MUST use ADL v1 semantics.

Distributed ADL does not supersede or replace `adl1.md`.

Operational skills implement both layers through progressive disclosure:

```text
adl/SKILL.md
-> adl-bootstrap/SKILL.md
-> adl-author/SKILL.md
-> adl-memory-state/SKILL.md
-> adl-context-pack/SKILL.md
-> adl-govern/SKILL.md
```

## goal

enable many agents to share durable project knowledge, memory, state, decisions, workflows, evidence, and history with low active-context cost.

## summary

Distributed ADL is the shared memory fabric built on ADL.

Agents do not exchange full transcripts or repeatedly load complete project history. Agents read and write compact ADL records, retrieve only task-relevant knowledge, progressively disclose older detail when needed, and use git-backed history for provenance, branching, review, rollback, and memory promotion.

Primary scaling effect:

```text
more agents -> more shared context -> higher raw token cost -> greater ADL compression ROI
```

Distributed ADL changes the scaling model from:

```text
N agents x full history/context
```

to:

```text
shared canonical knowledge + N task-specific context projections
```

## architecture

```text
agents
  -> project memory sets
  -> shared ADL state/memory
  -> git history + remote storage
  -> retrieval
  -> progressive disclosure
  -> task context
  -> execution
  -> new state/memory
  -> validation/promotion
  -> shared canonical knowledge
```

## memory_model

each project SHOULD maintain a standard multi-layer memory set.

Typical six-layer model:

```text
working memory
session state
episodic memory
semantic memory
procedural memory
decision/history memory
```

Multiple projects MAY maintain independent memory sets.

Agents MAY operate across multiple projects and memory sets.

Shared infrastructure MAY link:

- memory
- state
- decisions
- workflows
- skills
- tool references
- evidence
- historical context
- artifacts

Storage MAY use:

- git repositories
- object storage
- artifact stores
- databases
- shared project stores

ADL provides the common semantic representation between these layers.

## swarm_model

many agents MAY read from and contribute to the same knowledge system.

Each agent SHOULD receive only the minimum context required for its task.

Pattern:

```text
shared knowledge
-> retrieve relevant records
-> disclose required detail
-> execute task
-> extract durable state/memory
-> persist
```

Agents SHOULD NOT require the complete historical memory set in active context.

## progressive_disclosure

Current task context SHOULD contain high-value current information.

Older, lower-priority, or high-detail information remains reachable by reference.

Recommended disclosure path:

```text
current state
-> compact durable memory
-> detailed memory
-> historical state
-> raw evidence
```

Agents expand context only when required.

This changes memory access from:

```text
load everything
```

to:

```text
navigate knowledge on demand
```

## git_model

git acts as a durable coordination and history layer for distributed memory.

Benefits:

- versioned memory
- immutable history
- diffable state changes
- branch isolation
- rollback
- provenance
- distributed synchronization
- reviewable memory promotion

Agents MAY use separate branches for independent WIPs.

Example:

```text
main
├─ agent-a/feature-x
├─ agent-b/research-y
├─ agent-c/test-z
└─ agent-d/design-w
```

Branch-scoped knowledge MAY remain speculative, temporary, or task-local.

`main` SHOULD represent canonical shared project knowledge.

Important durable knowledge SHOULD be promoted through review.

Pattern:

```text
agent discovery
-> branch state/memory update
-> validate
-> PR
-> review
-> merge
-> canonical shared memory
```

PRs therefore act as both:

- code integration controls
- knowledge promotion controls

## memory_promotion

Not every observation SHOULD become global memory.

Promote information when it is:

- durable
- reusable
- verified
- decision-relevant
- project-wide
- operationally important

Keep information local when it is:

- exploratory
- unverified
- temporary
- task-specific
- superseded

This prevents shared memory from becoming an unbounded transcript store.

## compression

Without ADL, repeated natural-language coordination becomes expensive as agent count, history, and interaction frequency increase.

ADL reduces shared-context cost through:

- semantic normalization
- canonical terminology
- deduplication
- typed records
- compact references
- materialized current state
- historical separation
- selective retrieval
- progressive disclosure
- model-specific ADL-W compilation

Result:

```text
same useful shared knowledge -> fewer active tokens
```

Approximate ROI driver:

```text
ROI ~ agent_count x shared_memory_size x context_reuse x interaction_frequency
```

Therefore compression value generally increases as swarm size and communication density increase.

## hive_effect

Distributed ADL creates a practical shared-memory or hive-mind effect without requiring one agent to contain the full project history.

Conceptually:

```text
distributed durable memory
          |
          v
      retrieval
          |
          v
agent-specific context
          |
          v
      execution
          |
          v
memory/state contribution
          |
          v
distributed durable memory
```

Expected effects:

- agents inherit prior discoveries
- agents inherit current decisions and invariants
- agents avoid repeating solved work
- agents inspect historical state only when required
- agents work independently without losing project continuity
- new agents join existing projects without receiving full transcripts
- separate agent branches preserve WIP isolation
- promoted knowledge becomes shared canonical memory

## prefix_cache

Distributed ADL pairs well with prefix caching.

ADL reduces the number of tokens that must exist.

Progressive disclosure reduces irrelevant tokens loaded for a task.

Stable context ordering increases reusable prompt prefixes.

Prefix caching reduces repeated prefill computation for stable tokens that remain.

Combined:

```text
ADL
-> smaller shared context

progressive disclosure
-> less irrelevant context

stable prompt structure
-> higher prefix reuse

prefix caching
-> lower repeated prefill cost
```

Recommended context order:

```text
stable agent policy
-> stable skills/tools
-> stable project invariants
-> selected shared memory
-> current state
-> current evidence
-> current task
```

## distributed_projects

A swarm MAY operate across multiple git-tracked projects.

Each project owns its canonical memory set.

Cross-project knowledge SHOULD use explicit references rather than copy duplicated memory where possible.

Example:

```text
project-a memory ----\
project-b memory -----+-> agent retrieval -> task context
project-c memory ----/
```

Shared/global skills and workflows MAY live in separate repositories and be referenced by each project.

Object or artifact storage MAY retain large evidence while ADL stores compact semantic records and references.

## authority

Not all distributed memory has equal authority.

Recommended precedence:

```text
trusted control policy
-> canonical main-branch project knowledge
-> reviewed durable memory
-> branch-local state
-> retrieved external data
-> raw evidence
```

External data MUST NOT self-promote into trusted control memory.

Durable shared memory SHOULD preserve provenance and promotion history.

## scaling

Without structured compression and retrieval, git-backed memory works well for small agent groups but becomes increasingly expensive as concurrency and historical depth increase.

Distributed ADL targets this scaling limit.

Instead of every agent repeatedly ingesting the same history, agents consume task-specific projections of canonical shared knowledge.

The architecture therefore scales primarily by:

- reducing duplicated semantic content
- reducing loaded historical depth
- reusing stable prefixes
- sharing canonical memory instead of copying agent-local summaries
- promoting only durable knowledge

## outcome

Distributed ADL turns persistent agent documentation into a distributed computational memory fabric.

Git provides:

- history
- branches
- synchronization
- review
- rollback
- promotion

ADL provides:

- semantic density
- deterministic structure
- compact durable memory
- common agent representation

Retrieval provides:

- task relevance
- selective context loading

Progressive disclosure provides:

- bounded active context
- navigable historical depth

Prefix caching provides:

- lower repeated prefill cost

Combined, these components enable scalable multi-agent memory swarms with durable shared history, independent WIP branches, reviewed knowledge promotion, and controlled token cost.

## ref

- `adl1.md` — canonical ADL v1 language/specification.
- `adl/SKILL.md` — autonomous ADL entry/router.
- `adl-bootstrap/SKILL.md` — harness/repository bootstrap and migration.
- `adl-author/SKILL.md` — ADL-S authoring.
- `adl-memory-state/SKILL.md` — durable memory/state operations.
- `adl-context-pack/SKILL.md` — retrieval, ADL-W packing, and prefix-cache optimization.
- `adl-govern/SKILL.md` — linting, benchmarking, and governance.

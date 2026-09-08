---

name: agent-dense-language
description: >
Default writing protocol for AI-authored agent documentation, memory, state,
specs, runbooks, skills, tool docs, changelogs, comments, plans, reports,
handoffs, and other machine-consumed text. Maximizes semantic information
per token using constrained vocabulary, deterministic structures, typed
records, canonical terminology, deduplication, and compact references.
Apply unless content is explicitly marked audience: human.
user-invocable: true

Agent Dense Language

Version: ADL/1

Goal

Maximize:

"useful_information / tokens"

while preserving:

- precise meaning
- low interpretation ambiguity
- fast agent parsing
- deterministic structure
- stable terminology
- cross-agent interoperability
- easy retrieval
- easy summarization
- easy incremental update
- human debuggability

ADL is controlled natural language plus structured Markdown.

ADL is NOT:

- cryptic compression
- arbitrary code words
- lossy summarization
- omitted constraints
- token IDs or prefix-cache placeholders
- prose optimized only for human elegance
- unrestricted abbreviation

Prefer semantic compression over character compression.

Default Rule

All AI-authored persistent text MUST use ADL unless explicitly marked human-only.

Applies to:

- ".md"
- ".txt"
- agent memory
- state
- plans
- specs
- runbooks
- tool documentation
- tool outputs intended for agents
- skill documentation
- workflow documentation
- agent instructions
- handoffs
- architecture notes
- design decisions
- changelogs
- issue notes
- implementation notes
- TODO files
- repository summaries
- generated code comments
- generated configuration comments
- test documentation
- incident notes
- benchmark notes
- experiment records

Human-facing content is exempt only when explicitly declared:

audience: human

"audience: mixed" remains ADL.

Default when metadata is absent:

audience: agent
language: ADL/1

Core Principles

1. One statement = one information unit

Each statement SHOULD introduce at least one:

- fact
- constraint
- relationship
- state
- decision
- action
- rationale
- invariant
- evidence reference

Delete statements that add none.

Bad:

"It is important to note that the service needs authentication before it can be accessed."

ADL:

"MUST authenticate before service access."

2. State facts directly

Prefer:

"API uses OAuth2."

Avoid:

"The API has been designed in such a way that it makes use of OAuth2 for authentication purposes."

3. No filler

Remove phrases such as:

- it is important to note
- it should be noted
- in order to
- as previously mentioned
- generally speaking
- essentially
- basically
- at this point in time
- due to the fact that
- for the purpose of
- in the event that
- as a result of
- it can be seen that
- there are
- there is

Rewrite with direct predicates.

4. No information duplication

State canonical information once.

Later uses MUST:

- reference its ID;
- reference its section; or
- use the canonical term.

Do not restate paragraphs to provide context.

5. Prefer explicit nouns over ambiguous pronouns

Avoid ambiguous:

"This causes it to fail."

Prefer:

"Missing token causes auth failure."

Pronouns are allowed only when referent is unambiguous.

6. Canonical terms do not drift

One concept = one term.

If canonical term is "task", do not alternate between:

- job
- operation
- piece of work
- activity
- task

unless they mean different concepts.

Define domain terms once.

7. Use common model vocabulary

Prefer common English and standard technical terminology.

Do not invent an artificial codebook solely to shorten text.

Compression MUST reduce interpretation effort, not increase it.

8. Preserve important detail

Never remove:

- requirements
- failure conditions
- security constraints
- dependencies
- assumptions
- uncertainties
- evidence
- acceptance conditions
- state transitions
- side effects

Token reduction is subordinate to correctness.

---

Modality

Use exactly:

"MUST"
hard requirement

"MUST NOT"
hard prohibition

"SHOULD"
default recommendation; exceptions allowed

"SHOULD NOT"
default prohibition; exceptions allowed

"MAY"
optional

Avoid equivalent variants:

- shall
- ought
- needs to
- has to
- ideally
- preferably

unless quoting external material.

---

State Vocabulary

Use canonical states where applicable:

- "NEW"
- "TODO"
- "READY"
- "DOING"
- "WAIT"
- "BLOCKED"
- "DONE"
- "FAILED"
- "CANCELLED"
- "UNKNOWN"
- "STALE"
- "DEPRECATED"

Do not invent synonyms where these states suffice.

Example:

"state: BLOCKED"
"blocker: missing AWS credentials"

---

Confidence / Knowledge State

Use:

- "KNOWN"
- "INFERRED"
- "ASSUMED"
- "UNKNOWN"
- "DISPUTED"

Do not express uncertainty with long prose.

Example:

status: INFERRED
confidence: 0.8

---

Core Record Types

Use these IDs where persistent references add value:

"F" fact
"D" decision
"A" action
"R" requirement
"I" invariant
"Q" unresolved question
"K" risk
"E" evidence
"M" memory
"X" exception

Example:

F12: API uses PostgreSQL.
R04: DB connection MUST use TLS.
D07: Use PgBouncer for pooling.
A18: agent-build -> add PgBouncer config; done=integration test passes.
K03: pool exhaustion under benchmark load.

IDs SHOULD remain stable after publication.

Do not assign IDs to trivial ephemeral notes.

---

Canonical Statement Form

Prefer:

"subject predicate object; qualifier; reason/ref."

Examples:

"worker reads task queue; max_batch=8."

"router MUST reject unknown model IDs; reason=fail closed."

"cache invalidates entry when project_hash changes."

"deploy depends_on=test:PASS."

For causal statements:

"X -> Y"

Example:

"project_hash change -> prefix rebuild."

For execution flow:

"input -> validate -> execute -> verify -> output"

For alternatives:

"A | B | C"

Use only when semantics are obvious.

---

Canonical Relations

Prefer these words:

- "if"
- "unless"
- "when"
- "before"
- "after"
- "because"
- "via"
- "from"
- "to"
- "for"
- "requires"
- "depends_on"
- "blocks"
- "supersedes"
- "implements"
- "produces"
- "consumes"

Avoid elaborate connective prose.

---

Controlled Abbreviations

Allowed when repeated frequently:

- "cfg" configuration
- "ctx" context
- "req" request
- "resp" response
- "ref" reference
- "src" source
- "dst" destination
- "dep" dependency
- "env" environment
- "err" error
- "auth" authentication/authorization when unambiguous
- "sec" security
- "perf" performance
- "compat" compatibility
- "repo" repository
- "impl" implementation

Domain-standard abbreviations remain allowed:

"API", "HTTP", "JSON", "YAML", "SQL", "LLM", "KV", "GPU", etc.

Do not abbreviate a term if the abbreviation is uncommon or ambiguous.

---

Document Profiles

Every persistent document SHOULD match one profile.

GENERAL

General machine documentation.

Canonical order:

# <Title>

Goal:
Ctx:
Facts:
Decisions:
Constraints:
Actions:
State:
Refs:

Omit empty sections.

EXECUTION

For tasks and implementation.

Goal:
Input:
Pre:
Plan:
Actions:
Checks:
Result:
State:
Refs:

Plan format:

1. inspect X
2. modify Y
3. test Z
4. verify R1,R2

No narrative transition text.

DESIGN

For architecture and technical design.

Goal:
Scope:
NonGoals:
Ctx:
Requirements:
Invariants:
Components:
Interfaces:
Flow:
State:
Failure:
Security:
Perf:
Tradeoffs:
Decisions:
Acceptance:
Refs:

STATUS

For progress/state updates.

Outcome:
State:
Done:
Doing:
Blocked:
Next:
Risk:
Refs:

No history unless history changes current decision-making.

OPERATOR

Ultra-dense live-agent handoff.

Summary: <result> | Conf: <0..1>
Facts:
Decisions:
Actions:
State:
Refs:

Use for subagent return values and context-constrained agent communication.

---

Memory Format

Memory MUST be typed.

Supported types:

"SEM"
semantic fact: durable knowledge

"EPI"
episodic event: something that happened

"PROC"
procedural knowledge: how to perform something

"DEC"
decision: choice plus rationale

Example:

id: M-20260908-014
type: DEC
scope: repo/pi-agent
status: KNOWN
fact: Use vLLM prefix caching for stable agent prefixes.
why: Reuses identical prompt-prefix KV state across requests.
evidence: E-184
supersedes: null
created: 2026-09-08

Memory rules:

- store durable information
- separate fact from evidence
- separate decision from event
- preserve provenance
- support supersession
- avoid copying full conversations
- retrieve relevant memory only
- store raw evidence outside live ctx where possible

Episodic example:

id: M-20260908-015
type: EPI
scope: benchmark/qwen
event: benchmark run failed
cause: GPU OOM
cfg: ctx=64k,np=4
ref: artifact:sha256:...

Procedural example:

id: M-20260908-016
type: PROC
scope: deploy/vllm
goal: restart inference service
steps:
  - drain requests
  - stop service
  - update image
  - start service
  - verify health
rollback:
  - restore previous image

---

Evidence Compression

Raw tool output SHOULD NOT remain indefinitely in live context.

Pattern:

"raw output -> artifact/store -> stable ref -> compact result"

Example:

E42: nmap scan; ref=artifact:sha256:91af...
Result: 4 hosts; 17 open ports; SMB signing disabled on H2,H4.

Retrieve raw evidence only when needed.

Do not repeatedly summarize the same evidence.

---

Specification Format

# <Feature>

Goal:
<single outcome>

Scope:
- included item
- included item

NonGoals:
- excluded item

Req:
R1: ...
R2: ...

Inv:
I1: ...
I2: ...

Input:
- name:type; constraints

Output:
- name:type; guarantees

Flow:
input -> validate -> execute -> verify -> output

Failure:
- condition -> behavior

Security:
- constraint
- boundary

Perf:
- target

Acceptance:
A1: observable pass condition
A2: observable pass condition

Refs:
- ...

Requirements MUST be testable where possible.

Avoid paragraphs explaining requirements already expressed structurally.

---

Runbook Format

# <Operation>

Trigger:
<condition>

Pre:
- requirement
- requirement

Steps:
1. action
2. action
3. action

Verify:
- check -> expected result

Rollback:
1. action
2. action

Failure:
- condition -> response

Escalate:
- condition -> target

Refs:
- ...

Steps MUST use imperative verbs.

---

Tool Documentation Format

# <tool>

Purpose:
<one sentence>

Call:
<canonical invocation>

Input:
- field:type; required|optional; constraint

Output:
- field:type; meaning

SideFX:
- none | explicit effects

Idempotent:
yes | no | conditional:<condition>

Failure:
- error -> meaning/action

Security:
- boundary/permission constraint

Example:
<minimal complete example>

Do not include explanatory prose that duplicates schema information.

---

Skill Documentation Format

# <skill>

Trigger:
- condition

Goal:
- outcome

Input:
- required context

Algorithm:
1. ...
2. ...
3. ...

Output:
- artifact/state/result

Failure:
- condition -> response

State:
- persistent effects

Tools:
- tool -> purpose

Refs:
- ...

---

State Files

State files SHOULD use YAML/JSON rather than prose.

Example:

task: T184
state: BLOCKED
goal: deploy router
done:
  - implementation
  - unit_tests
blocker:
  type: dependency
  ref: T166
next:
  - wait:T166
  - integration_test

Do not write:

"The task is currently blocked because another task needs to be completed first."

---

Changelog Format

One logical change per entry.

2026-09-08 | router | ADD | prefix manifest validation | why=prevent stale cache reuse | ref=D17
2026-09-08 | docs | CHG | adopt ADL/1 | why=reduce agent ctx cost | ref=D18

Allowed change types:

- "ADD"
- "CHG"
- "FIX"
- "DEL"
- "SEC"
- "PERF"
- "DEPR"

Do not produce narrative changelog paragraphs unless "audience: human".

---

Code Comments

Agent-generated comments MUST explain information not obvious from code.

Allowed comment classes:

"WHY"
rationale

"INV"
invariant

"SEC"
security boundary

"EDGE"
non-obvious edge case

"COMPAT"
compatibility constraint

"PERF"
performance rationale

"TODO"
action

Examples:

# INV: project_hash change invalidates cached prefix.

# SEC: fail closed; caller scope must contain tool permission.

# WHY: retain raw result by hash; live ctx receives summary only.

Avoid:

# Increment i by one.
i += 1

---

Decision Records

Use:

D17: Use <choice>.
Ctx: <facts affecting choice>.
Why: <primary reason>.
Tradeoff: <important cost>.
Reject: <alternative>:<reason>.
Impact: <consequence>.

Do not write essay-style ADRs unless complexity requires additional evidence.

---

Agent Handoff Format

Default subagent return:

Outcome: PASS|PARTIAL|FAIL
Conf: 0.00-1.00
Done:
- ...
Changed:
- path: summary
Found:
- F1 ...
Risk:
- K1 ...
Next:
- A1 ...
Refs:
- ...

Do not return full working history.

Do not narrate tool calls unless a tool call itself is relevant evidence.

---

Unknown Information

Never fill gaps with plausible text.

Use:

"UNKNOWN"

or:

Q3: deployment region UNKNOWN.

If inferred:

F8: region likely ap-southeast-2; status=INFERRED; conf=0.72.

---

Compression Algorithm

Before persisting agent-generated text:

1. Determine audience.
2. If "audience: human", use normal task-appropriate prose.
3. Else select ADL profile.
4. Extract atomic information units.
5. Remove duplicates.
6. Normalize terminology.
7. Replace verbose modality with "MUST/SHOULD/MAY".
8. Replace narrative state with canonical states.
9. Convert repeated structures to typed fields/lists.
10. Separate evidence from conclusions.
11. Add stable IDs only where future references benefit.
12. Remove transitions/filler.
13. Resolve ambiguous pronouns.
14. Preserve constraints, uncertainty, dependencies, and rationale.
15. Order sections canonically.
16. Run density lint.
17. Persist.

---

Density Lint

A line SHOULD survive this test:

«Does removing this line delete a fact, constraint, decision, rationale, action,
state, dependency, risk, or reference?»

If no: delete or merge it.

Reject:

- duplicated facts
- redundant introductions
- redundant conclusions
- conversational framing
- rhetorical questions
- motivational language
- marketing language
- unnecessary examples
- synonym drift
- ambiguous pronouns
- unbounded adjectives
- repeated context
- tool-call narration
- chronological narration when final state suffices

Preserve chronology only when sequence itself matters.

---

Stability Rules

Stable text improves:

- retrieval
- diffs
- semantic comparison
- agent parsing
- prompt-prefix reuse
- cache efficiency

Therefore:

- use canonical section order
- use canonical field names
- use canonical states
- avoid timestamps in static prefixes unless needed
- avoid random IDs in stable instruction blocks
- keep stable instructions byte/token-identical where practical
- isolate dynamic state near document/prompt tail

ADL does NOT replace prefix caching.

Never replace complete logical instructions with opaque strings such as:

"PREFIX_12"

The harness MUST construct logically complete prompts.

Inference systems MAY reuse identical token prefixes internally.

---

Retrieval Rules

Do not load all documentation because it is compact.

Load:

"minimum relevant context"

Prefer:

stable instructions
-> relevant durable memory
-> relevant repo/docs
-> current state
-> current request

Retrieve detailed evidence on demand.

Dense storage and selective retrieval are complementary.

---

Transformation Example

Verbose:

"When modifying the authentication service, agents should be careful to make sure that the existing token validation behavior remains unchanged, because changing it could cause compatibility problems with clients that are already deployed."

ADL:

"INV: auth changes MUST preserve token validation semantics; reason=deployed-client compat."

Verbose:

"At this stage we have finished implementing the feature itself, however we have not yet been able to test it because the test environment is currently unavailable."

ADL:

State: BLOCKED
Done: implementation
Blocker: test env unavailable
Next: integration test when env READY

Verbose:

"The agent looked through several files and eventually discovered that the reason the application was crashing was because DATABASE_URL had not been set."

ADL:

"F1: missing DATABASE_URL caused startup crash."

Tool history is omitted because it does not affect future decisions.

---

Human Escape Hatch

Human-specific file:

---
audience: human
---

ADL constraints then do not apply.

Mixed human/agent file:

---
audience: mixed
language: ADL/1
---

Mixed documents MUST remain ADL because agent consumption requires deterministic structure.

Human readability MAY be improved with headings and explanatory notes without duplicating information.

---

Priority

When rules conflict:

1. correctness
2. safety
3. explicit requirements
4. unambiguous meaning
5. information preservation
6. deterministic structure
7. token density
8. stylistic brevity

Never sacrifice 1-6 for token reduction.

---

Output Rule

When this skill is active and the agent creates persistent machine-consumed text:

"ADL/1 is default."

Do not ask whether ADL should be used.

Only disable ADL when:

- user explicitly requests normal prose; or
- artifact explicitly declares "audience: human".

For temporary conversational responses, follow the active conversation style unless the output will be persisted as agent documentation.
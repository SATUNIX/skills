# ADL v2 worked examples

One project throughout: an inference router (FastAPI inference API `$api` behind a request router `$rt`, vLLM, a staging cluster `$stg` and a production cluster `$prod`). Each workload is written in ADL v1 (`v1/`) and ADL v2 (`v2/`). Every `v2/` file is real `adl2.py` output; `make_examples.sh` regenerates the derived ones byte-for-byte.

## files

| workload | v1 | v2 | what it shows |
| --- | --- | --- | --- |
| memory | `v1/memory.md` | `v2/mem.adl` + `v2/hist.adl` | the same memory and state. `mem.adl` is the compacted snapshot, `hist.adl` holds superseded `f1` and closed `t1`. `e2e.sh` rebuilds both byte-for-byte with `adl2 add` + `compact`. |
| retrieval | (no tool: read the whole doc) | `v2/brief.adl`, `v2/pack.adl`, `v2/legend.txt` | `adl2 brief` (L1+L2), `adl2 pack --task "deploy to production"` (L3, 14 of 26 records), `adl2 legend` (L0, once per context) |
| state update | `v1/state_update.md` | `v2/state_update.adl` | one change: staging is back, `nvidia-smi` shows L4, the integration test is unblocked. v1 rewrites the state section (`## after`). v2 sends 4 delta lines: new `e`, a fact that supersedes the disputed `f5` (`^f5`), and `q1 -> done`, `t2 -> doing`, as a `msg:prog` |
| handoff | `v1/handoff.md` | `v2/handoff.done.adl`, `v2/handoff.ctx.adl` | worker w1 reports the result of t4 (retry with backoff). `done` is a delta against the shared store: provisional ids `v+1 e+1 f+1 t+1` and a `base:` hash over the referenced `t4 $api $rt`. `ctx` is the same result made self-contained (`msg new ctx --inline`) for a receiver without the store. |
| table | `v1/table.md` | `v2/table.adl` | 20-row GPU node inventory: v1 `tab` block vs v2 table record (`gpu_nodes[20]{…}:`); `ref/table.json` is a naive JSON list of the same rows |

Equivalence notes: `v1/memory.md` still lists the finished task `unit tests` in its state profile. v2 keeps it, and the superseded bind fact, in `hist.adl`. `v1/handoff.md` uses the v1 handoff profile (adl1.md `## handoff`) and does not restate context.

Validate (from this directory):

```sh
A=$(cd ../../adl/scripts && pwd)/adl2.py; E=$PWD
d=$(mktemp -d); mkdir "$d/.adl"; cp v2/mem.adl v2/hist.adl "$d/.adl/"
python3 $A lint --root "$d"                             # store: mem.adl + hist.adl together
python3 $A lint v2/brief.adl v2/pack.adl v2/state_update.adl v2/handoff.done.adl v2/handoff.ctx.adl v2/table.adl
python3 $A msg check v2/state_update.adl --root "$d"    # ok ... match
python3 $A msg check v2/handoff.done.adl --root "$d"    # ok ... match
(cd "$(mktemp -d)" && python3 $A msg check "$E/v2/handoff.ctx.adl")   # ok ... self-contained
```

`adl2 lint v2/mem.adl` on its own reports `E_REF` for `f1`, because `f1` lives in `hist.adl`. Lint the pair as a store.

## run

```sh
bash token_saving/examples/adl2/e2e.sh                  # fresh temp dir (kept for inspection)
bash token_saving/examples/adl2/e2e.sh /tmp/adl2-demo   # or an empty/absent dir
bash token_saving/examples/adl2/make_examples.sh        # regenerate derived v2/ files and ref/table.json
python3 -m unittest token_saving/adl/scripts/tests/test_examples.py
```

`e2e.sh` (bash, `set -euo pipefail`, `ADL2_TOKENIZER=est`, `--today 2026-11-03`) prints a transcript and asserts at each step. It exits non-zero at the first failed check and ends with `e2e: all 126 checks passed`. The steps:

1. install into a project with `.claude/` and an existing `CLAUDE.md`. A second install reports `outcome: done (no changes)`. The tool is at `.claude/skills/adl/scripts/adl2.py`.
2. capture memory with `add`: entities, keyed, derived and assumed facts, permission states, requirements, decisions with `why:`/`over:`, a goal, tasks and a question. A duplicate gives `f2=dup`. A keyed conflict exits 2 (`E_CONFLICT`) and is then resolved with `^f1`.
3. transitions (`ok t4> t2=noop`). The compacted snapshot equals `v2/mem.adl` + `v2/hist.adl`.
4. `brief`; `pack --task` (asserts `f2 $api.timeout=30s` and `r2` are included); a tight `--budget` (`% more:`); `get f11 --hist`; `find`.
5. `python3 <tool> hook session-start </dev/null`: header + legend + the same brief.
6. handoff: `msg new task --ref`, then the worker runs `msg check` (ok) and `msg open` (`% resolved`). The worker sends `msg:done` with provisional ids (identical to `v2/handoff.done.adl`). The main agent runs `msg apply` (`f+1=f12 t+1=t5`); a re-apply only reports `=dup`.
7. a receiver with an empty dir: the delta exits 3 with a `msg:need`; a `msg:ctx --inline` checks ok there.
8. a diverged branch (w2 allocated its own `f12`/`t5`) gets exit 3 `conflict:base` and a `msg:need`, answered with a `ctx`. An `@adl3` message is refused (exit 2, `E_VERSION`), and `apply` writes nothing.
9. `migrate` of a small v1 file: `--check` (fidelity 100%), then `--into .adl/mem.adl` (`% v1map`).
10. `compact`: `brief` and `pack` are byte-identical before and after; history and `msg check` still work.
11. `decode --view human` of the final store contains no `$`.
12. `lint` of the store and the messages passes.

`measure.py FILE[#SECTION]…` prints a Markdown token table: tiktoken `cl100k_base`/`o200k_base` when importable, each HF `tokenizer.json` in `ADL2_HF_TOKENIZERS` (colon-separated, needs `tokenizers`, counted without special tokens), and always `est` = ceil(chars/3.3), the tool's estimate. `FILE#after` counts only the body of the `## after` section; `-` reads stdin. It is stdlib-only when the optional packages are missing.

## tokens

Tokenizers used: tiktoken 0.14.0 `cl100k_base` and `o200k_base`; HuggingFace `tokenizers` 0.23.3 with the `tokenizer.json` of `Qwen/Qwen2.5-7B-Instruct` and `mistralai/Mistral-7B-Instruct-v0.3`; `est`. Claude's tokenizer was not available, so there are no Claude counts. Command (run from this directory; `$VENV` has tiktoken and tokenizers, `$TOK` holds the two tokenizer.json files):

```sh
ADL2_HF_TOKENIZERS=$TOK/Qwen_Qwen2.5-7B-Instruct.json:$TOK/mistralai_Mistral-7B-Instruct-v0.3.json \
  $VENV/bin/python measure.py v1/memory.md v2/mem.adl v2/brief.adl v2/pack.adl v2/legend.txt \
  'v1/state_update.md#before' 'v1/state_update.md#after' v2/state_update.adl v1/handoff.md \
  v2/handoff.done.adl v2/handoff.ctx.adl v1/table.md v2/table.adl ref/table.json
```

| file | chars | cl100k_base | o200k_base | Qwen_Qwen2.5-7B-Instruct | mistralai_Mistral-7B-Instruct-v0.3 | est |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| v1/memory.md | 2279 | 635 | 623 | 680 | 791 | 691 |
| v2/mem.adl | 1670 | 542 | 540 | 584 | 661 | 507 |
| v2/brief.adl | 1055 | 324 | 323 | 333 | 378 | 320 |
| v2/pack.adl | 896 | 263 | 262 | 273 | 312 | 272 |
| v2/legend.txt | 645 | 174 | 173 | 174 | 177 | 196 |
| v1/state_update.md#before | 479 | 119 | 118 | 121 | 150 | 146 |
| v1/state_update.md#after | 482 | 136 | 133 | 141 | 167 | 147 |
| v2/state_update.adl | 180 | 92 | 91 | 97 | 110 | 55 |
| v1/handoff.md | 435 | 133 | 132 | 157 | 173 | 132 |
| v2/handoff.done.adl | 336 | 125 | 123 | 142 | 157 | 102 |
| v2/handoff.ctx.adl | 597 | 203 | 201 | 220 | 250 | 181 |
| v1/table.md | 552 | 254 | 262 | 318 | 349 | 168 |
| v2/table.adl | 607 | 285 | 292 | 350 | 401 | 184 |
| ref/table.json | 2458 | 860 | 860 | 924 | 1069 | 745 |

The four lines that `msg apply v2/state_update.adl` appends to `mem.adl` (real ids, no message header), measured with `tail -n 4 .adl/mem.adl | measure.py -` after applying to a copy of the example store:

| file | chars | cl100k_base | o200k_base | Qwen_Qwen2.5-7B-Instruct | mistralai_Mistral-7B-Instruct-v0.3 | est |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| - | 126 | 65 | 65 | 70 | 78 | 39 |

Overheads, measured the same way (`head -1 FILE | measure.py -`, `sed 1d v1/table.md | measure.py -`, `sed 1,2d v2/table.adl | measure.py -`):

| input | chars | cl100k_base | o200k_base | Qwen_Qwen2.5-7B-Instruct | mistralai_Mistral-7B-Instruct-v0.3 | est |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `v2/handoff.done.adl` header line | 51 | 23 | 22 | 24 | 27 | 16 |
| `v2/state_update.adl` header line | 51 | 23 | 22 | 24 | 29 | 16 |
| `v1/table.md` 20 rows | 514 | 242 | 250 | 306 | 335 | 156 |
| `v2/table.adl` 20 rows (2-space indent) | 554 | 262 | 270 | 326 | 374 | 168 |

### per workload

Ratios below are computed from the tables above and listed in the order cl100k / o200k / Qwen2.5 / Mistral.

| workload | v1 | v2 | change |
| --- | --- | --- | --- |
| memory, full | `memory.md` 635 / 623 / 680 / 791 | `mem.adl` 542 / 540 / 584 / 661 | -15% / -13% / -14% / -16% |
| memory, session start | whole doc | `brief.adl` 324 / 323 / 333 / 378 | -49% / -48% / -51% / -52% |
| memory, one task | whole doc | `pack.adl` 263 / 262 / 273 / 312 | -59% / -58% / -60% / -61% |
| legend (one-time) | none | `legend.txt` 174 / 173 / 174 / 177 | +174…177 per context |
| state update | rewrite `#after` 136 / 133 / 141 / 167 | `state_update.adl` 92 / 91 / 97 / 110 | -32% / -32% / -31% / -34% |
| state update, appended lines only | same | 65 / 65 / 70 / 78 | -52% / -51% / -50% / -53% |
| handoff, shared store | `handoff.md` 133 / 132 / 157 / 173 | `handoff.done.adl` 125 / 123 / 142 / 157 | -6% / -7% / -10% / -9% |
| handoff, no shared store | same | `handoff.ctx.adl` 203 / 201 / 220 / 250 | +53% / +52% / +40% / +45% |
| table (20 rows) | `table.md` 254 / 262 / 318 / 349 | `table.adl` 285 / 292 / 350 / 401 | +12% / +11% / +10% / +15% (JSON: 860 / 860 / 924 / 1069) |

### where v2 does not save

- Legend overhead on a tiny store. Full `mem.adl` plus the legend is 716 / 713 / 758 / 838, which is 6-14% more than the v1 doc. The legend pays off only when it is amortized (cached prefix, the `adl` skill already loaded, many reads) or when `brief`/`pack` replace whole-file reads: brief + legend is -20…-30% and pack + legend is -30…-38%.
- `brief` and `pack` are projections, not full copies: the pack holds 14 of 26 active records. They save tokens by leaving records out, and those records stay reachable with `get`. They are not a lossless re-encoding.
- Handoff deltas are near parity with a v1 handoff that does not restate context (-6…-10%). The message header (`from: to: re: base:`, 22-27 tokens) takes up most of what v2 would otherwise save. What v2 adds here is verification: the `base:` hash, `msg:need` on mismatch, and idempotent `apply` with id remapping.
- `ctx` costs 55-63% more than the `done` delta, because it inlines `t4`, its `needs:` closure (`f2`, `r2`) and the aliases. Send it only to a receiver without the store.
- Tables: the v2 record is 10-15% larger than the v1 `tab` block. The 2-space continuation indent costs one token per row on cl100k, o200k and Qwen2.5 and about two on Mistral (+20 / +20 / +20 / +39 over 20 rows), and the `@adl2 mem` header plus `f1 gpu_nodes[20]{…}:` add more. Both formats are 2.6-3.4x smaller than naive JSON.
- The per-change state saving depends on state size. v1 rewrites the whole state section, which is small here (119 tokens before the change). The v2 delta stays the same size as the state grows.
- `est` (chars/3.3) is a budget heuristic, not a measurement. It undercounts sigil-dense v2 text (`state_update.adl`: est 55 vs 91-110 real) and CSV rows (`table.md`: 168 vs 254-349). It overcounts prose-like v1 text (`memory.md`: 691 vs 623-680 on three of the four tokenizers). Measure with the receiving model's tokenizer when a budget is tight.
- This is one small project, not a benchmark. Mistral counts highest everywhere, and the ratios are similar across the four tokenizers.

## interpretability

Results: see PR / filled after evaluation.

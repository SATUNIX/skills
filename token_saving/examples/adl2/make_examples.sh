#!/usr/bin/env bash
# Regenerate the derived v2 worked-example files with the real tool (deterministic).
#
# Inputs (committed): v2/mem.adl + v2/hist.adl (the example store; e2e.sh rebuilds it
# byte-for-byte from `adl2 add` commands), v1/table.md (source rows of the table example).
# Outputs: v2/{legend.txt,brief.adl,pack.adl,state_update.adl,handoff.done.adl,
# handoff.ctx.adl,table.adl} and ref/table.json.
#
# Usage: bash make_examples.sh [OUTDIR]   (default: this directory, i.e. overwrite in place)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="$HERE/../../adl/scripts/adl2.py"
OUT="${1:-$HERE}"
TODAY=2026-11-03
export ADL2_TOKENIZER=est PYTHONDONTWRITEBYTECODE=1
unset CLAUDE_PROJECT_DIR ADL2_AGENT || true

mkdir -p "$OUT/v2" "$OUT/ref"
OUT="$(cd "$OUT" && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/adl2-examples.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

# the example store, as a real .adl/ directory
mkdir -p "$TMP/store/.adl"
cp "$HERE/v2/mem.adl" "$HERE/v2/hist.adl" "$TMP/store/.adl/"
cd "$TMP/store"
adl2() { python3 "$TOOL" "$@" --today "$TODAY"; }

adl2 legend > "$OUT/v2/legend.txt"
adl2 brief > "$OUT/v2/brief.adl"
adl2 pack --task "deploy to production" > "$OUT/v2/pack.adl"

# state update: staging back, GPU confirmed L4 (same change as v1/state_update.md)
adl2 msg new prog --from w2 --to main --re t2 - > "$OUT/v2/state_update.adl" <<'EOF'
e+1 nvidia-smi on $stg nodes: 3x L4 @2026-11-03 see:.adl/ev/stg-gpu.txt
f+1 $stg.gpu=L4 [e+1] ^f5
q1 -> done see:e+1
t2 -> doing
EOF

# worker result for t4 (same content as v1/handoff.md): delta against the shared store ...
DONE_BODY='t4 -> done
v+1 router/client.py: retry idempotent requests 3x with exponential backoff base=200ms [repo:router/client.py] @2026-11-03
e+1 load test log @2026-11-03 see:.adl/ev/load-1103.txt
f+1 $api returns 503 above 200 rps [e+1]
t+1 ready add circuit breaker to $rt client needs:f+1'
printf '%s\n' "$DONE_BODY" | adl2 msg new done --from w1 --to main --re t4 - > "$OUT/v2/handoff.done.adl"
# ... and the self-contained variant for a receiver without the store
printf '%s\n' "$DONE_BODY" | adl2 msg new ctx --inline --from w1 --to main --re t4 - > "$OUT/v2/handoff.ctx.adl"

# table: the v1 `tab` rows as one v2 table record, written by `adl2 add` into an empty store
mkdir -p "$TMP/table"
cd "$TMP/table"
adl2 init > /dev/null
awk 'NR == 1 { name = $2; cols = $3; next } { rows[++n] = $0 }
     END { printf "f %s[%d]{%s}:\n", name, n, cols; for (i = 1; i <= n; i++) print "  " rows[i] }' \
    "$HERE/v1/table.md" | adl2 add - > /dev/null
cp .adl/mem.adl "$OUT/v2/table.adl"

# naive JSON (list of objects) of the same rows, for reference
python3 - "$HERE/v1/table.md" "$OUT/ref/table.json" <<'EOF'
import json, sys
lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
_, name, cols = lines[0].split()
keys = cols.split(",")
rows = [dict(zip(keys, l.split(","))) for l in lines[1:] if l]
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    fh.write(json.dumps({name: rows}, indent=2) + "\n")
EOF

echo "ok wrote v2/legend.txt v2/brief.adl v2/pack.adl v2/state_update.adl v2/handoff.done.adl v2/handoff.ctx.adl v2/table.adl ref/table.json under $OUT"

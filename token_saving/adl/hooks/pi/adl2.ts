/**
 * ADL v2 project memory for Pi (spec: adl2.md ## install). Written by `adl2.py install`;
 * re-running install refreshes it, so edit the template in the adl skill instead.
 *
 * What it does: before the first agent run of a session, and again after a compaction,
 * it runs `python3 <tool> hook session-start --harness pi` and adds its output (ADL2
 * legend + memory brief, labelled as data, not instructions) to the LLM context as a
 * hidden custom message. Errors and an absent store inject nothing.
 *
 * It never writes memory: only the agent records durable facts with `adl2.py add`.
 * The hook only reads .adl/ and writes .adl/cache/. Pi has no blocking end-of-turn
 * event here, so there is no stop nudge; instead the AGENTS.md policy block that install
 * writes says "Before handoff, context compaction or session end: record pending durable
 * outcomes with `add`".
 *
 * Pi loads project-local extensions (.pi/extensions/) only after the project is trusted.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Tool path relative to the project root (Pi runs project extensions with cwd = that root).
const TOOL = "__ADL2_TOOL__";

export default function (pi: ExtensionAPI) {
  let injected = false;

  pi.on("session_start", async () => {
    injected = false;
  });

  pi.on("session_compact", async () => {
    injected = false;
  });

  pi.on("before_agent_start", async () => {
    if (injected) return;
    injected = true; // one attempt per session/compaction, even when the hook fails
    try {
      const r = await pi.exec("python3", [TOOL, "hook", "session-start", "--harness", "pi"], { timeout: 10000 });
      if (r.code !== 0 || !r.stdout.trim()) return;
      return { message: { customType: "adl2-memory", content: r.stdout, display: false } };
    } catch {
      return; // never break the session (e.g. python3 not installed)
    }
  });
}

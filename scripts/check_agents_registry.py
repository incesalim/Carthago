#!/usr/bin/env python3
"""Guard: the /admin/agents registry stays in sync with the workflows it runs.

`web/app/lib/agents-registry.ts` hand-authors the agent roster. Each dispatchable
agent names a `workflowFile:` and declares the `inputs` its run form offers, and
those input names are forwarded verbatim to the GitHub dispatch API.

That is a silent-failure shape. GitHub rejects an unknown workflow input with a
422 at dispatch time — not at build, not in review — so a renamed or removed
input turns the admin Run button into an error nobody sees until they press it.
Worse, a REMOVED input just stops being sent and the workflow quietly applies
its own default, which looks like a successful run of something you did not ask
for.

So the invariant is checked both ways:

  * every `workflowFile:` in the registry points at a workflow that exists
  * every declared input name is a real `workflow_dispatch` input of that file

Run standalone (`python scripts/check_agents_registry.py`) — exits non-zero
naming the drift — or via pytest (tests/test_agents_registry.py). Stdlib only:
the CI python job installs no YAML library, so the workflow inputs are read with
an indentation-aware scan of the `workflow_dispatch:` block rather than a parser.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "web" / "app" / "lib" / "agents-registry.ts"
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# `workflowFile: "analyst-daily.yml"` — the registry is TS, not JSON, so a
# targeted regex beats pretending to parse it.
_WORKFLOW_FILE = re.compile(r'workflowFile:\s*"([^"]+)"')
# `name: "banks"` inside an inputs array entry. The registry uses `name:` only
# for input specs and for the agent's display name (`name: "Research analyst"`),
# so pair it with the neighbouring `type:` to keep display names out.
_INPUT_SPEC = re.compile(r'\{\s*(?:\.\.\.[A-Z_]+,\s*)?name:\s*"([a-z_]+)"[^}]*?type:\s*"(text|choice|boolean)"')
# Spread references such as `KIND_INPUT` / `{ ...PERIOD_INPUT, default: "..." }`.
_SPREAD = re.compile(r"(?:\.\.\.)?\b([A-Z][A-Z0-9_]*_INPUT)\b")
_CONST_INPUT = re.compile(
    r"const\s+([A-Z][A-Z0-9_]*_INPUT)\s*:\s*AgentInput\s*=\s*\{\s*name:\s*\"([a-z_]+)\"",
)


def _balanced(src: str, open_at: int) -> str:
    """Substring of the bracket/brace group starting at `open_at`, inclusive.

    String-aware so a `[` or `}` inside a label or regex pattern (and there are
    several — `"^\\d{4}Q[1-4]$"`) cannot end the group early. Splitting the
    registry on a bare `id:` regex instead is what made the first version of
    this gate report green while checking nothing: stage entries carry `id:`
    too, so every "agent block" ended before its `inputs:` array.
    """
    closing = {"[": "]", "{": "}", "(": ")"}[src[open_at]]
    depth = 0
    i = open_at
    quote: str | None = None
    while i < len(src):
        ch = src[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0 and ch == closing:
                return src[open_at : i + 1]
        i += 1
    raise ValueError(f"unbalanced group opened at {open_at}")


def _agent_blocks(src: str) -> list[tuple[str, str]]:
    """Split the AGENTS array into (agent id, source block) pairs."""
    start = src.find("AGENTS: AgentDef[] = [")
    if start < 0:
        return []
    # NOT `index("[", start)` — the type annotation `AgentDef[]` carries a pair
    # of brackets before the array's own, and scanning from there balances on
    # the wrong group.
    array = _balanced(src, src.index("= [", start) + 2)
    blocks: list[tuple[str, str]] = []
    i = 0
    while i < len(array):
        ch = array[i]
        if ch == "{":
            block = _balanced(array, i)
            m = re.search(r'\bid:\s*"([a-z0-9-]+)"', block)
            if m:
                blocks.append((m.group(1), block))
            i += len(block)
            continue
        i += 1
    return blocks


def registry_agents() -> dict[str, tuple[str, set[str]]]:
    """{agent id: (workflow file, declared input names)} for dispatchable agents."""
    src = REGISTRY.read_text(encoding="utf-8")
    shared = {name: input_name for name, input_name in _CONST_INPUT.findall(src)}

    agents: dict[str, tuple[str, set[str]]] = {}
    for agent_id, block in _agent_blocks(src):
        wf = _WORKFLOW_FILE.search(block)
        if not wf:
            continue  # Worker-resident agent — nothing to dispatch, nothing to check.
        # Only the `inputs:` array declares dispatch inputs; take the balanced
        # array so a later field can't be mistaken for one.
        inputs_at = block.find("inputs: [")
        inputs_src = _balanced(block, block.index("[", inputs_at)) if inputs_at >= 0 else ""
        names = {m.group(1) for m in _INPUT_SPEC.finditer(inputs_src)}
        names |= {shared[c] for c in _SPREAD.findall(inputs_src) if c in shared}
        agents[agent_id] = (wf.group(1), names)
    return agents


def workflow_inputs(path: Path) -> set[str] | None:
    """Input names under `workflow_dispatch:` → `inputs:`, or None if the
    workflow takes no dispatch inputs at all."""
    lines = path.read_text(encoding="utf-8").splitlines()
    in_dispatch = False
    dispatch_indent = 0
    in_inputs = False
    inputs_indent = 0
    names: set[str] = set()

    for raw in lines:
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if stripped.startswith("workflow_dispatch:"):
            in_dispatch, dispatch_indent, in_inputs = True, indent, False
            continue
        if in_dispatch and indent <= dispatch_indent and not stripped.startswith("workflow_dispatch:"):
            # Left the workflow_dispatch block (e.g. on to `schedule:` or `jobs:`).
            in_dispatch = in_inputs = False
            continue
        if in_dispatch and stripped.startswith("inputs:"):
            in_inputs, inputs_indent = True, indent
            continue
        if in_inputs:
            if indent <= inputs_indent:
                in_inputs = False
                continue
            # An input name is the only key at exactly inputs_indent + 2.
            if indent == inputs_indent + 2 and stripped.endswith(":"):
                names.add(stripped[:-1].strip())
    return names or None


def main() -> int:
    if not REGISTRY.exists():
        print(f"FAIL: registry not found: {REGISTRY}", file=sys.stderr)
        return 1

    problems: list[str] = []
    agents = registry_agents()
    if not agents:
        problems.append(
            "no dispatchable agents parsed out of agents-registry.ts — the regexes above "
            "have drifted from the file's shape"
        )

    for agent_id, (wf_name, declared) in sorted(agents.items()):
        wf_path = WORKFLOW_DIR / wf_name
        if not wf_path.exists():
            problems.append(f"{agent_id}: workflowFile '{wf_name}' does not exist in .github/workflows/")
            continue
        actual = workflow_inputs(wf_path)
        if actual is None:
            if declared:
                problems.append(
                    f"{agent_id}: declares inputs {sorted(declared)} but {wf_name} takes no "
                    f"workflow_dispatch inputs"
                )
            continue
        unknown = sorted(declared - actual)
        if unknown:
            problems.append(
                f"{agent_id}: input(s) {unknown} are not workflow_dispatch inputs of {wf_name} "
                f"(it accepts {sorted(actual)}) — a dispatch would 422"
            )

    if problems:
        print("Agent registry is out of sync with .github/workflows/:\n", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print(
            "\nFix web/app/lib/agents-registry.ts (or the workflow) so the two agree.",
            file=sys.stderr,
        )
        return 1

    checked = sum(len(d) for _, d in agents.values())
    print(f"OK: {len(agents)} dispatchable agent(s), {checked} declared input(s) all exist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

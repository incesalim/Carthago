"""The /admin/agents registry must stay in sync with the workflows it dispatches.

Thin pytest wrapper around scripts/check_agents_registry.py so drift fails CI as
well as a standalone run — plus the negative tests that keep the gate honest.
The first version of this check reported "OK: 3 dispatchable agent(s), 0 declared
input(s)" — green while parsing nothing, because stage entries carry an `id:`
too and every agent block ended before its `inputs:` array. A gate that cannot
fail is worse than no gate, so its ability to fail is tested here.
"""

from check_agents_registry import main, registry_agents, workflow_inputs


def test_registry_parses_real_agents_and_inputs():
    agents = registry_agents()
    assert agents, "no dispatchable agents parsed — the registry regexes have drifted"
    # Every dispatchable agent must declare at least one input; a zero here is
    # exactly the vacuous-pass shape this gate exists to prevent.
    for agent_id, (workflow, inputs) in agents.items():
        assert workflow.endswith(".yml"), f"{agent_id}: {workflow} is not a workflow file"
        assert inputs, f"{agent_id}: parsed zero inputs — check the parser, not the registry"


def test_shared_input_constants_are_resolved():
    """KIND_INPUT / PERIOD_INPUT are shared consts, referenced by spread. If the
    resolver breaks they vanish silently and the gate stops checking them."""
    agents = registry_agents()
    research = agents["analyst-research"][1]
    assert {"banks", "period", "kind", "scout_only"} == research


def test_workflow_input_scan_reads_dispatch_inputs():
    from check_agents_registry import WORKFLOW_DIR

    found = workflow_inputs(WORKFLOW_DIR / "analyst-research.yml")
    assert found == {"banks", "period", "kind", "scout_only"}


def test_gate_passes_on_the_current_tree():
    assert main() == 0


def test_gate_fails_when_an_input_is_not_a_real_workflow_input(monkeypatch):
    """Rename a dispatch input in the workflow and the gate must catch it —
    GitHub answers an unknown input with a 422 only at dispatch time."""
    import check_agents_registry as mod

    def fake_inputs(path):
        real = workflow_inputs(path)
        if real and path.name == "analyst-research.yml":
            return (real - {"scout_only"}) | {"scout_only_renamed"}
        return real

    monkeypatch.setattr(mod, "workflow_inputs", fake_inputs)
    assert mod.main() == 1


def test_gate_fails_when_the_workflow_file_is_missing(monkeypatch, tmp_path):
    import check_agents_registry as mod

    monkeypatch.setattr(mod, "WORKFLOW_DIR", tmp_path)
    assert mod.main() == 1

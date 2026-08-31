"""A unit-repair preview cannot publish data or send alerts."""
from pathlib import Path


def test_every_external_mutation_is_excluded_from_the_refresh_preview():
    source = (Path(__file__).resolve().parents[1] /
              ".github/workflows/refresh-audit.yml").read_text(encoding="utf-8")
    steps = source.split("\n      - name: ")[1:]
    mutating = [step for step in steps if any(token in step for token in (
        "--alert", "scripts/notify.py", "scripts/push_to_d1.py", "upload_file(",
    ))]
    assert len(mutating) == 7
    for step in mutating:
        condition = next(line.strip() for line in step.splitlines() if line.strip().startswith("if:"))
        assert "!inputs.dry_run" in condition, step.splitlines()[0]
    scope = next(step for step in steps if step.startswith("Validate dry-run scope"))
    assert '"$SKIP_SCRAPE" == true' in scope
    assert '"$BANK" =~ ^[A-Z0-9]+$' in scope
    assert '"$PERIOD" =~ ^[0-9]{4}Q[1-4]$' in scope

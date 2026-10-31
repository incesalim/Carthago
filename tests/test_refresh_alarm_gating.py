"""The dispatch path must stay green when the systemic alarm fires.

2026-10-31: two scoped dispatches re-raised the alarm after their work had
already persisted — each produced a spurious ❌ Telegram alert beside its own
🆕 message, and (before the corpus gate was widened the same day) silently
dropped its document-corpus build. The re-raise is now scheduled runs only:
on a manual dispatch the operator scoped the targets themselves, the alarm
ratio is measured over just that scoped batch (4 blocked hosts in 7 targets
read as a 57% fleet-wide break), and the `::warning` already carries the news.

Pinned here, against the real workflow text:
  1. the alarm re-raise step fires only on `schedule` events;
  2. the sync step still records `systemic=true` and logs the warning on
     every path — the observability moved, it did not disappear;
  3. the notify step fires on `extracted` as well as `new`, so the R2-rescue
     path for runner-blocked hosts (extract-only dispatch, new=0) is not
     Telegram-silent (it was: 4 partitions landed unnoticed, 2026-10-31).

Verified live the same evening by the BURGAN/SKBNK drill: four unresolvable
targets, alarm raised, job green, warning present, nothing written.
"""
from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / '.github' / 'workflows' / 'refresh-audit.yml'


def _steps() -> dict[str, str]:
    source = WORKFLOW.read_text(encoding='utf-8')
    steps = source.split('\n      - name: ')[1:]
    out = {}
    for step in steps:
        name = step.split('\n', 1)[0].strip()
        out[name] = step
    return out


def test_alarm_reraise_is_schedule_only():
    step = _steps()['Fail the job if the sync raised a systemic alarm']
    condition = next(line.strip() for line in step.splitlines()
                     if line.strip().startswith('if:'))
    assert 'steps.sync.outputs.systemic == \'true\'' in condition
    assert "github.event_name == 'schedule'" in condition


def test_sync_step_still_records_the_alarm_on_every_path():
    """The rc==8 branch must stay unconditional — dispatch keeps the warning."""
    source = WORKFLOW.read_text(encoding='utf-8')
    sync = source.split('\n      - name: Sync audit reports', 1)[1]
    sync = sync.split('\n      - name: ', 1)[0]
    assert 'echo "systemic=true" >> "$GITHUB_OUTPUT"' in sync
    assert '::warning::sync raised a systemic-failure alarm' in sync
    # A real crash (any code ≠ 8) still fails the step immediately.
    assert re.search(r'elif \[ "\$rc" -ne 0 \]; then', sync)


def test_notify_fires_on_extractions_too():
    step = _steps()['Notify on newly acquired reports']
    condition = next(line.strip() for line in step.splitlines()
                     if line.strip().startswith('if:'))
    assert "steps.sync.outputs.new != '0'" in condition
    assert "steps.sync.outputs.extracted != '0'" in condition
    assert '!inputs.dry_run' in condition

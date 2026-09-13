"""The automatic corpus publisher must not escape a refresh preview."""

from pathlib import Path

import pytest
import yaml


WORKFLOWS = Path(__file__).resolve().parents[1] / '.github' / 'workflows'


def test_refresh_publication_signal_is_explicit_and_input_controlled():
    refresh = yaml.safe_load((WORKFLOWS / 'refresh-audit.yml').read_text(encoding='utf-8'))
    assert refresh['run-name'] == (
        "${{ inputs.dry_run && 'Refresh audit reports (preview)' || "
        "'Refresh audit reports (publish)' }}"
    )


@pytest.mark.parametrize('event,name,title,conclusion,repository,expected', [
    ('workflow_run', 'Refresh audit reports', 'Refresh audit reports (preview)', 'success', 'own', False),
    ('workflow_run', 'Refresh audit reports', 'Refresh audit reports', 'success', 'own', False),
    ('workflow_run', 'Refresh audit reports', '', 'success', 'own', False),
    ('workflow_run', 'Refresh audit reports', 'Refresh audit reports (publish)', 'success', 'own', True),
    ('workflow_run', 'Refresh audit reports', 'Refresh audit reports (publish)', 'failure', 'own', False),
    ('workflow_run', 'Refresh audit reports', 'Refresh audit reports (publish)', 'cancelled', 'own', False),
    ('workflow_run', 'Refresh audit reports', 'Refresh audit reports (publish)', 'success', 'fork', False),
    ('workflow_run', 'Acquire audit reports', 'Acquire audit reports', 'success', 'own', True),
    ('workflow_run', 'Acquire audit reports', 'Acquire audit reports', 'failure', 'own', False),
    ('workflow_dispatch', '', '', '', '', True),
])
def test_capture_job_gate(event, name, title, conclusion, repository, expected):
    workflow = yaml.safe_load((WORKFLOWS / 'build-document-corpus.yml').read_text(encoding='utf-8'))
    expression = workflow['jobs']['capture']['if']
    # Evaluate the workflow's small boolean predicate, rather than a duplicate
    # policy function. Unknown syntax fails; there are no external calls here.
    values = {
        'github.event_name': event,
        'github.event.workflow_run.head_repository.full_name': repository,
        'github.repository': 'own',
        'github.event.workflow_run.name': name,
        'github.event.workflow_run.display_title': title,
        'github.event.workflow_run.conclusion': conclusion,
    }
    for field, value in values.items():
        expression = expression.replace(field, repr(value))
    expression = expression.replace('always()', 'True').replace('cancelled()', 'False')
    expression = expression.replace('&&', ' and ').replace('||', ' or ').replace('!', ' not ')
    expression = ' '.join(expression.split())
    assert eval(expression, {'__builtins__': {}}, {}) is expected

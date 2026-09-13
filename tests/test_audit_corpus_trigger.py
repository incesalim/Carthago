"""The automatic corpus publisher must not escape a refresh preview."""

from pathlib import Path
import re

import pytest


WORKFLOWS = Path(__file__).resolve().parents[1] / '.github' / 'workflows'


def test_refresh_publication_signal_is_explicit_and_input_controlled():
    refresh = (WORKFLOWS / 'refresh-audit.yml').read_text(encoding='utf-8')
    assert re.search(r'^run-name: (.+)$', refresh, re.MULTILINE)[1] == (
        "${{ inputs.dry_run && 'Refresh audit reports (preview)' || "
        "'Refresh audit reports (publish)' }}"
    )


@pytest.mark.parametrize('event,workflow_file,title,conclusion,repository,expected', [
    ('workflow_run', 'refresh-audit.yml', 'Refresh audit reports (preview)', 'success', 'own', False),
    ('workflow_run', 'refresh-audit.yml', 'Refresh audit reports', 'success', 'own', False),
    ('workflow_run', 'refresh-audit.yml', '', 'success', 'own', False),
    ('workflow_run', 'refresh-audit.yml', 'Refresh audit reports (publish)', 'success', 'own', True),
    ('workflow_run', 'refresh-audit.yml', 'Refresh audit reports (publish)', 'failure', 'own', False),
    ('workflow_run', 'refresh-audit.yml', 'Refresh audit reports (publish)', 'cancelled', 'own', False),
    ('workflow_run', 'refresh-audit.yml', 'Refresh audit reports (publish)', 'success', 'fork', False),
    ('workflow_run', 'acquire-audit.yml', 'Acquire audit reports', 'success', 'own', True),
    ('workflow_run', 'acquire-audit.yml', 'Acquire audit reports', 'failure', 'own', False),
    ('workflow_run', 'unrelated.yml', 'Refresh audit reports (publish)', 'success', 'own', False),
    ('workflow_dispatch', '', '', '', '', True),
])
def test_capture_job_gate(event, workflow_file, title, conclusion, repository, expected):
    workflow = (WORKFLOWS / 'build-document-corpus.yml').read_text(encoding='utf-8')
    capture = workflow.split('\n  capture:\n', 1)[1]
    expression = re.search(r'^    if: >-\n((?:      .+\n)+)', capture, re.MULTILINE)[1]
    # Evaluate the workflow's small boolean predicate, rather than a duplicate
    # policy function. Unknown syntax fails; there are no external calls here.
    values = {
        'github.event_name': event,
        'github.event.workflow_run.head_repository.full_name': repository,
        'github.repository': 'own',
        # GitHub's real run payload sets name to the dynamic run-name too.
        # Identify the upstream workflow by its stable path, not its run title.
        'github.event.workflow_run.name': title,
        'github.event.workflow_run.path': f'.github/workflows/{workflow_file}',
        'github.event.workflow_run.display_title': title,
        'github.event.workflow_run.conclusion': conclusion,
    }
    for field, value in values.items():
        expression = expression.replace(field, repr(value))
    expression = expression.replace('always()', 'True').replace('cancelled()', 'False')
    expression = expression.replace('&&', ' and ').replace('||', ' or ').replace('!', ' not ')
    expression = ' '.join(expression.split())
    assert eval(expression, {'__builtins__': {}}, {}) is expected

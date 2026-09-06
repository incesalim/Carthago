from types import SimpleNamespace

import pytest

from src.audit_reports.document_acquisition import fetch_source


@pytest.mark.parametrize(('url', 'bundle'), [
    ('https://www.icbc.com.tr/report.pdf', True),
    ('https://icbc.com.tr/report.pdf', True),
    ('https://www.bddk.org.tr/BdrUyg/report.zip', True),
    ('https://www.bddk.gov.tr/report.zip', True),
    ('https://another-bank.example/report.pdf', False),
    ('https://www.icbc.com.tr.other.example/report.pdf', False),
    ('https://other.example/report.pdf?url=www.icbc.com.tr', False),
])
def test_missing_intermediate_uses_verified_chain_on_exact_hosts_only(monkeypatch, url, bundle):
    monkeypatch.setattr('src.scrapers._http.bddk_verify', lambda: '/verified/intermediate-and-roots.pem')
    calls = []

    def get(requested, **kwargs):
        calls.append((requested, kwargs))
        return SimpleNamespace(content=b'%PDF-source', url=requested,
                               headers={'Content-Type': 'application/pdf'}, raise_for_status=lambda: None)

    monkeypatch.setattr('requests.get', get)
    body, response = fetch_source(url)
    assert body == b'%PDF-source'
    assert calls[0][0] == url
    assert calls[0][1]['verify'] == ('/verified/intermediate-and-roots.pem' if bundle else True)
    assert response['tls_verification'] == ('certifi_with_globalsign_intermediate' if bundle else 'default_ca_bundle')


def test_chain_failure_is_not_retried_without_verification(monkeypatch):
    from requests.exceptions import SSLError
    monkeypatch.setattr('src.scrapers._http.bddk_verify', lambda: '/verified/intermediate-and-roots.pem')
    calls = []

    def fail(*args, **kwargs):
        calls.append(kwargs)
        raise SSLError('certificate verify failed')

    monkeypatch.setattr('requests.get', fail)
    with pytest.raises(SSLError):
        fetch_source('https://www.icbc.com.tr/report.pdf')
    assert len(calls) == 1 and calls[0]['verify'] == '/verified/intermediate-and-roots.pem'

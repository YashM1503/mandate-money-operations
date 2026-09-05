import os

from mandate.api import ROOT, allowed_hosts
from mandate.env import masked
from mandate.money_operations_narrative import try_model_compose


def test_allowed_hosts_keeps_loopback_for_healthchecks(monkeypatch):
    monkeypatch.setenv('MANDATE_ALLOWED_HOSTS', 'demo.example.com')
    for key in ('RENDER_EXTERNAL_HOSTNAME', 'RAILWAY_PUBLIC_DOMAIN', 'WEBSITE_HOSTNAME', 'FLY_APP_NAME'):
        monkeypatch.delenv(key, raising=False)
    hosts = allowed_hosts()
    assert hosts[0] == 'demo.example.com'
    assert '127.0.0.1' in hosts
    assert 'localhost' in hosts


def test_allowed_hosts_star_disables_allowlist(monkeypatch):
    monkeypatch.setenv('MANDATE_ALLOWED_HOSTS', '*')
    assert allowed_hosts() == ['*']


def test_allowed_hosts_appends_platform_hostnames(monkeypatch):
    monkeypatch.setenv('MANDATE_ALLOWED_HOSTS', 'localhost')
    monkeypatch.setenv('RENDER_EXTERNAL_HOSTNAME', 'mandate.onrender.com')
    monkeypatch.setenv('RAILWAY_PUBLIC_DOMAIN', 'mandate.up.railway.app')
    monkeypatch.setenv('FLY_APP_NAME', 'mandate-money')
    monkeypatch.delenv('WEBSITE_HOSTNAME', raising=False)
    hosts = allowed_hosts()
    assert 'mandate.onrender.com' in hosts
    assert 'mandate.up.railway.app' in hosts
    assert 'mandate-money.fly.dev' in hosts


def test_masked_env_never_prints_secret(monkeypatch):
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'sk-live-should-not-leak')
    label = masked('ELEVENLABS_API_KEY')
    assert label.startswith('set (')
    assert 'sk-live' not in label


def test_try_model_compose_stays_off_without_egress(monkeypatch):
    monkeypatch.delenv('MANDATE_ALLOW_SYNTHETIC_EGRESS', raising=False)
    monkeypatch.setenv('MANDATE_MODEL_URL', 'https://example.invalid/v1/chat/completions')
    monkeypatch.setenv('MANDATE_MODEL_KEY', 'not-a-real-key')
    monkeypatch.setenv('MANDATE_MODEL_NAME', 'demo')
    assert try_model_compose({'claims': []}) is None


def test_standalone_demo_html_matches_workspace():
    workspace = ROOT / 'static' / 'money-operations.html'
    demo = ROOT / 'demo.html'
    assert demo.is_file()
    assert demo.read_bytes() == workspace.read_bytes()
    text = demo.read_text()
    assert 'STANDALONE' in text
    assert 'Open Megan’s close' in text
    assert 'file:' in text

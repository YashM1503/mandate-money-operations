import os

from mandate.api import allowed_hosts


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

from fastapi.testclient import TestClient
from app.main import app
from app import db

client = TestClient(app)


def test_liveness():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_busca_nome_parametrizada(monkeypatch):
    calls = []
    def fake_read(statement, **params):
        calls.append((statement, params))
        return [{'asn': 15169, 'nome_encontrado': 'Google LLC'}]
    monkeypatch.setattr(db, 'read', fake_read)
    response = client.get('/ases/busca', params={'nome': 'Google'})
    assert response.status_code == 200
    assert response.json()['resultados'][0]['asn'] == 15169
    assert calls[0][1]['nome'] == 'google'
    assert 'Google' not in calls[0][0]   # não concatena entrada na consulta Cypher


def test_as_nao_encontrado(monkeypatch):
    monkeypatch.setattr(db, 'read', lambda *_args, **_kwargs: [])
    assert client.get('/ases/999999').status_code == 404


def test_cidr_invalido():
    assert client.get('/prefixos', params={'cidr': 'abc'}).status_code == 422


def test_as_responde_tags_e_fontes(monkeypatch):
    def fake_read(statement, **params):
        if 'RETURN a.asn AS asn LIMIT 1' in statement:
            return [{'asn': 2497}]
        if 'CATEGORIZED' in statement:
            return [{'tag': 'ISP', 'fonte': 'bgptools.tags'}]
        return []
    monkeypatch.setattr(db, 'read', fake_read)
    response = client.get('/ases/2497')
    assert response.status_code == 200
    assert response.json()['tags'][0]['fonte'] == 'bgptools.tags'

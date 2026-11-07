from fastapi.testclient import TestClient
from app.main import app
from app import db

client = TestClient(app)


def test_ixps_retorna_pais_e_fonte(monkeypatch):
    calls = []
    def fake_read(query, **params):
        calls.append((query, params))
        return [{'ixp': 'IX.br São Paulo', 'pais': 'BR', 'fontes_membro': ['peeringdb.ix'], 'fontes_pais': ['peeringdb.ix']}]
    monkeypatch.setattr(db, 'read', fake_read)
    response = client.get('/ases/15169/ixps', params={'pais': 'br', 'limite': 5})
    assert response.status_code == 200
    assert response.json()['ixps'][0]['pais'] == 'BR'
    assert 'MEMBER_OF' in calls[0][0]
    assert calls[0][1]['pais'] == 'BR'


def test_siblings_parametrizado(monkeypatch):
    calls = []
    def fake_read(query, **params):
        calls.append((query, params))
        return [{'asn': 13949, 'fontes': ['caida.as2org']}]
    monkeypatch.setattr(db, 'read', fake_read)
    response = client.get('/ases/15169/siblings')
    assert response.status_code == 200
    assert response.json()['siblings'][0]['asn'] == 13949
    assert 'SIBLING_OF' in calls[0][0]
    assert calls[0][1]['asn'] == 15169


def test_top_dominios_as_tld_nao_e_pais(monkeypatch):
    calls = []
    def fake_read(query, **params):
        calls.append((query, params))
        return [{'dominio': 'exemplo.com.br', 'ranking': 'Tranco', 'posicao': 500, 'prefixos': ['8.8.8.0/24'], 'ips': ['8.8.8.8']}]
    monkeypatch.setattr(db, 'read', fake_read)
    response = client.get('/ases/15169/top-dominios', params={'tld': 'br', 'ranking_max': 1000})
    assert response.status_code == 200
    assert response.json()['dominios'][0]['dominio'] == 'exemplo.com.br'
    assert calls[0][1]['sufixo'] == '.br'
    assert 'RESOLVES_TO' in calls[0][0]
    assert 'ORIGINATE' in calls[0][0]


def test_prefixo_valido(monkeypatch):
    calls = []
    def fake_read(query, **params):
        calls.append(params)
        return []
    monkeypatch.setattr(db, 'read', fake_read)
    resp = client.get('/prefixos/top-dominios', params={'cidr': '8.8.8.0/24'})
    assert resp.status_code == 200
    assert calls[0]['prefixo'] == '8.8.8.0/24'
    assert client.get('/prefixos/top-dominios', params={'cidr': '8.8.8.1/24'}).status_code == 422


def test_relacoes_usa_tipo_dinamico_so_para_leitura(monkeypatch):
    calls=[]
    def fake_read(query, **params):
        calls.append((query,params))
        return [{'relacao': 'SIBLING_OF', 'tipo_vizinho': ['AS'], 'fonte': 'caida.as2org', 'ocorrencias': 2}]
    monkeypatch.setattr(db, 'read', fake_read)
    resp=client.get('/ases/15169/relacoes')
    assert resp.status_code == 200
    assert 'SIBLING_OF' == resp.json()['relacoes'][0]['relacao']
    assert calls[0][1]['asn']==15169


def test_validacao_dos_parametros():
    assert client.get('/ases/0/ixps').status_code == 422
    assert client.get('/ases/15169/ixps', params={'pais':'BRA'}).status_code == 422
    assert client.get('/ases/15169/top-dominios', params={'tld':'br*'}).status_code == 422
    assert client.get('/ases/15169/siblings', params={'limite':201}).status_code == 422

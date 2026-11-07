from fastapi.testclient import TestClient
from app.main import app
from app import db

client = TestClient(app)


def mock_read(query, **params):
    if 'RETURN a.asn AS asn LIMIT 1' in query:
        return [{'asn': params['asn']}]
    if 'WITH a, collect(DISTINCT n.name)' in query:
        return [
            {'asn': 15169, 'nomes_coincidentes': ['Google LLC']},
            {'asn': 6432, 'nomes_coincidentes': ['GOOGLE-FIBER']},
            {'asn': 13949, 'nomes_coincidentes': ['Google LLC']},
        ][:params['limite']]
    if 'n.name AS nome' in query:
        return [{'nome': 'Google LLC', 'fonte': 'ripe.as_names'}]
    if 't.label AS tag' in query:
        return [{'tag': 'Content', 'fonte': 'bgptools.tags'}]
    if 'c.country_code AS pais' in query and 'c:Country' in query and 'ix:' not in query:
        return [{'pais': 'US', 'fonte': 'nro.delegated_stats'}]
    if 'o.name AS organizacao' in query:
        return [{'organizacao': 'Google LLC', 'fonte': 'caida.as2org'}]
    if 'm:MEMBER_OF' in query:
        return [{'ixp': 'Test IX', 'pais': 'BR', 'fontes_membro': ['peeringdb'], 'fontes_pais': []}]
    if 'r:SIBLING_OF' in query:
        return [{'asn': 13949, 'fontes': ['caida.as2org']}]
    if 'p:BGPPrefix' in query:
        return [{'prefixo': '8.8.8.0/24', 'fonte': 'bgpkit.pfx2asn'}]
    if 'dns:RESOLVES_TO' in query:
        return [{'dominio': 'example.com', 'ranking': 'Tranco', 'posicao': 50, 'prefixos': [], 'ips': []}]
    return []


def test_perfil_por_asn_agrupa_secoes(monkeypatch):
    monkeypatch.setattr(db, 'read', mock_read)
    response = client.get('/ases/15169/perfil')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['asn'] == 15169
    assert data['tags'][0]['tag'] == 'Content'
    assert data['ixps'][0]['pais'] == 'BR'
    assert data['siblings'][0]['asn'] == 13949
    assert data['prefixos'][0]['prefixo'] == '8.8.8.0/24'
    assert data['top_dominios'][0]['dominio'] == 'example.com'
    assert data['perfil_parcial'] is False


def test_pesquisa_nome_distintos_com_limite(monkeypatch):
    monkeypatch.setattr(db, 'read', mock_read)
    response = client.get('/perfil', params={'nome': 'Google', 'limite_ases': 2, 'incluir_dominios': 'false'})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['quantidade_ases'] == 2
    assert data['mais_ases_correspondentes'] is True
    assert [a['asn'] for a in data['resultados']] == [15169, 6432]
    assert data['resultados'][0]['dominios_consultados'] is False
    assert data['resultados'][0]['top_dominios'] == []


def test_falha_de_dominios_mantem_outras_secoes(monkeypatch):
    def mock_with_domain_error(query, **params):
        if 'dns:RESOLVES_TO' in query:
            raise TimeoutError('Tempo limite')
        return mock_read(query, **params)
    monkeypatch.setattr(db, 'read', mock_with_domain_error)
    response = client.get('/ases/15169/perfil')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['perfil_parcial'] is True
    assert data['top_dominios'] == []
    assert data['erros_secoes'][0]['secao'] == 'top_dominios'
    assert data['tags'][0]['tag'] == 'Content'


def test_validacao_perfil(monkeypatch):
    monkeypatch.setattr(db, 'read', mock_read)
    assert client.get('/perfil').status_code == 422
    assert client.get('/perfil?asn=15169&nome=Google').status_code == 422
    assert client.get('/ases/0/perfil').status_code == 422
    assert client.get('/perfil?nome=G').status_code == 422
    assert client.get('/ases/15169/perfil?pais_ixp=BRA').status_code == 422
    assert client.get('/ases/15169/perfil?limite_dominios=200').status_code == 422

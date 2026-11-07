from fastapi.testclient import TestClient
from app import db
from app.main import app

client = TestClient(app)


def fake_read(statement, **params):
    if 'RETURN DISTINCT a.asn AS asn ORDER BY asn LIMIT $limite' in statement:
        return [{'asn': 15169}, {'asn': 6432}, {'asn': 13949}][:params['limite']]
    if 'RETURN a.asn AS asn LIMIT 1' in statement:
        return [{'asn': params['asn']}]
    if 'n.name AS nome' in statement:
        return [{'nome': 'Google LLC', 'fonte': 'ripe.as_names'}]
    if 't.label AS tag' in statement:
        return [{'tag': 'Content', 'fonte': 'bgptools.tags'}]
    if 'm:MEMBER_OF' in statement:
        return [{'ixp': 'IXP de teste', 'pais': 'BR', 'fontes_membro': [], 'fontes_pais': []}]
    if 'r:SIBLING_OF' in statement:
        return [{'asn': 999, 'fontes': ['caida.as2org']}]
    return []


def test_cada_seletor_retorna_perfil(monkeypatch):
    monkeypatch.setattr(db, 'read', fake_read)
    for selector in ['asn=15169', 'nome=Google', 'prefixo=8.8.8.0%2F24', 'pais=br', 'tag=Content']:
        res = client.get(f'/consulta?{selector}&incluir_dominios=false&limite_ases=1')
        assert res.status_code == 200, (selector, res.text)
        data = res.json()
        assert data['quantidade_ases'] == 1
        assert data['resultados'][0]['asn'] == 15169
        assert data['resultados'][0]['ixps'][0]['pais'] == 'BR'
        assert data['resultados'][0]['limites_por_secao']['top_dominios'] == 0


def test_busca_limitada_assinala_mais_resultados(monkeypatch):
    monkeypatch.setattr(db, 'read', fake_read)
    data = client.get('/consulta?nome=Google&limite_ases=2&incluir_dominios=false').json()
    assert data['quantidade_ases'] == 2
    assert data['mais_ases_correspondentes'] is True
    assert data['resultados'][0]['tags'][0]['tag'] == 'Content'


def test_rejeita_seletor_duplo_ou_vazio():
    assert client.get('/consulta').status_code == 422
    assert client.get('/consulta?asn=15169&nome=Google').status_code == 422
    assert client.get('/consulta?prefixo=abc').status_code == 422
    assert client.get('/consulta?pais=BRA').status_code == 422
    assert client.get('/consulta?tag=%20%20').status_code == 422
    assert client.get('/consulta?asn=0').status_code == 422


def test_parametros_cypher_sao_separados_do_texto(monkeypatch):
    calls = []
    def spy(statement, **params):
        calls.append((statement, params))
        return fake_read(statement, **params)
    monkeypatch.setattr(db, 'read', spy)
    response = client.get('/consulta', params={'nome': 'Google', 'incluir_dominios': 'false'})
    assert response.status_code == 200
    assert 'Google' not in calls[0][0]
    assert calls[0][1]['valor'] == 'google'


def test_falha_parcial_preserva_demais_secoes(monkeypatch):
    def err(statement, **params):
        if 'r:SIBLING_OF' in statement:
            raise TimeoutError('simulado')
        return fake_read(statement, **params)
    monkeypatch.setattr(db, 'read', err)
    r = client.get('/consulta?asn=15169&incluir_dominios=false')
    assert r.status_code == 200
    p = r.json()['resultados'][0]
    assert p['perfil_parcial'] is True
    assert p['erros_secoes'][0]['secao'] == 'siblings'
    assert p['ixps']

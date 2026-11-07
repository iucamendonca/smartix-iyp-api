"""REST API to query an independently managed local Internet Yellow Pages."""
import logging
from typing import Literal

from fastapi import FastAPI, HTTPException, Query

from . import db

logger = logging.getLogger(__name__)
app = FastAPI(
    title="SmartIX IYP API",
    description="Consultas somente leitura ao Internet Yellow Pages local (Neo4j).",
    version="0.4.0",
)


def safe_read(statement: str, **parameters) -> list[dict]:
    try:
        return db.read(statement, **parameters)
    except Exception:
        logger.exception("Erro ao consultar IYP")
        raise HTTPException(status_code=503, detail="Banco IYP indisponível ou consulta excedeu o tempo limite")


@app.get("/health", tags=["Infraestrutura"])
def health():
    """Liveness: informa que o processo da API está funcionando."""
    return {"status": "ok", "servico": "smartix-iyp-api"}


@app.get("/health/ready", tags=["Infraestrutura"])
def ready():
    """Readiness: verifica também a conexão com o Neo4j."""
    safe_read("RETURN 1 AS ok")
    return {"status": "ready", "neo4j": "conectado"}


@app.get("/ases/busca", tags=["ASes"])
def buscar_ases(
    nome: str = Query(min_length=2, max_length=80, description="Parte do nome de um AS"),
    limite: int = Query(default=10, ge=1, le=50),
    modo: Literal["parcial", "exato"] = "parcial",
):
    """Busca ASes por nome. Parcial é insensível a caixa, mas pode exigir varredura."""
    if modo == "exato":
        query = """
            MATCH (n:Name {name: $nome})-[:NAME]-(a:AS)
            RETURN DISTINCT a.asn AS asn, n.name AS nome_encontrado
            ORDER BY asn LIMIT $limite
        """
        parametros = {"nome": nome.strip(), "limite": limite}
    else:
        query = """
            MATCH (n:Name)
            WHERE toLower(n.name) CONTAINS $nome
            MATCH (n)-[:NAME]-(a:AS)
            RETURN DISTINCT a.asn AS asn, n.name AS nome_encontrado
            ORDER BY asn LIMIT $limite
        """
        parametros = {"nome": nome.strip().lower(), "limite": limite}
    if not nome.strip():
        raise HTTPException(status_code=422, detail="Nome não pode ser vazio")
    results = safe_read(query, **parametros)
    return {"consulta": nome, "modo": modo, "quantidade": len(results), "resultados": results,
            "observacao": "Nomes são provenientes de múltiplas fontes e podem ser ambíguos."}


@app.get("/ases/{asn}", tags=["ASes"])
def detalhes_as(asn: int):
    """Consulta por ASN, incluindo nomes, tags, países e operadores disponíveis."""
    if asn < 1 or asn > 4294967295:
        raise HTTPException(status_code=422, detail="ASN fora do intervalo permitido")
    found = safe_read("MATCH (a:AS {asn:$asn}) RETURN a.asn AS asn LIMIT 1", asn=asn)
    if not found:
        raise HTTPException(status_code=404, detail="ASN não encontrado no dump IYP")

    nomes = safe_read("""
        MATCH (a:AS {asn:$asn})-[r:NAME]-(n:Name)
        RETURN DISTINCT n.name AS nome, r.reference_name AS fonte
        ORDER BY nome LIMIT 50
    """, asn=asn)
    tags = safe_read("""
        MATCH (a:AS {asn:$asn})-[r:CATEGORIZED]-(t:Tag)
        RETURN DISTINCT t.label AS tag, r.reference_name AS fonte
        ORDER BY tag LIMIT 100
    """, asn=asn)
    paises = safe_read("""
        MATCH (a:AS {asn:$asn})-[r:COUNTRY]-(c:Country)
        RETURN DISTINCT c.country_code AS pais, r.reference_name AS fonte
        ORDER BY pais LIMIT 20
    """, asn=asn)
    organizacoes = safe_read("""
        MATCH (a:AS {asn:$asn})-[r:MANAGED_BY]-(o:Organization)
        RETURN DISTINCT o.name AS organizacao, r.reference_name AS fonte
        ORDER BY organizacao LIMIT 30
    """, asn=asn)
    return {"asn": asn, "nomes": nomes, "tags": tags, "paises": paises,
            "organizacoes": organizacoes,
            "observacao": "Campos vazios significam dados não disponíveis nas fontes deste dump, não ausência da característica."}


@app.get("/prefixos", tags=["Prefixos"])
def consultar_prefixo(
    cidr: str = Query(min_length=3, max_length=50, description="Prefixo na notação CIDR"),
    limite: int = Query(default=50, ge=1, le=100),
):
    """Retorna ASes que originam o prefixo exatamente informado."""
    from ipaddress import ip_network
    try:
        prefixo = str(ip_network(cidr, strict=True))
    except ValueError:
        raise HTTPException(status_code=422, detail="CIDR inválido. Ex.: 8.8.8.0/24")
    records = safe_read("""
        MATCH (a:AS)-[r:ORIGINATE]-(p:Prefix {prefix:$prefixo})
        RETURN DISTINCT a.asn AS asn, r.reference_name AS fonte
        ORDER BY asn LIMIT $limite
    """, prefixo=prefixo, limite=limite)
    return {"prefixo": prefixo, "quantidade": len(records), "origens": records}


@app.get("/paises/{codigo}/ases", tags=["Países"])
def ases_por_pais(codigo: str, limite: int = Query(default=20, ge=1, le=100)):
    """ASes vinculados ao país nas fontes IYP; não implica localização física."""
    if len(codigo) != 2 or not codigo.isascii() or not codigo.isalpha():
        raise HTTPException(status_code=422, detail="Informe código ISO-3166 alfa-2. Ex.: BR")
    records = safe_read("""
        MATCH (c:Country {country_code: $pais})-[r:COUNTRY]-(a:AS)
        RETURN DISTINCT a.asn AS asn, r.reference_name AS fonte
        ORDER BY asn LIMIT $limite
    """, pais=codigo.upper(), limite=limite)
    return {"pais": codigo.upper(), "quantidade": len(records), "ases": records,
            "observacao": "O vínculo COUNTRY depende da fonte e não é necessariamente geolocalização."}


# ---- Consultas avançadas sobre o grafo IYP ----


def _asn_valido(asn: int) -> None:
    if not 1 <= asn <= 4294967295:
        raise HTTPException(status_code=422, detail="ASN fora do intervalo permitido")


def _prefixo_valido(cidr: str) -> str:
    from ipaddress import ip_network

    try:
        return str(ip_network(cidr, strict=True))
    except ValueError:
        raise HTTPException(status_code=422, detail="CIDR inválido. Ex.: 8.8.8.0/24")


def _codigo_pais(pais: str | None) -> str | None:
    if pais is None:
        return None
    pais = pais.strip().upper()
    if len(pais) != 2 or not pais.isascii() or not pais.isalpha():
        raise HTTPException(status_code=422, detail="Informe país ISO-3166 alfa-2, como BR")
    return pais


def _sufixo_dominio(tld: str | None) -> str | None:
    """Filtro por sufixo de DNS, sem qualquer alegação de localização geográfica."""
    if tld is None:
        return None
    tld = tld.strip().lower().lstrip('.')
    if not 2 <= len(tld) <= 15 or not tld.isascii() or not tld.replace('.', '').isalnum():
        raise HTTPException(status_code=422, detail="TLD inválido. Exemplos: br, com.br, jp")
    return '.' + tld


@app.get('/ases/{asn}/ixps', tags=['Relações do grafo'])
def ixps_do_as(
    asn: int,
    limite: int = Query(default=50, ge=1, le=200),
    pais: str | None = Query(default=None, description='Código ISO alfa-2 do país do IXP; não do AS'),
):
    """IXPs dos quais o AS é membro, segundo as fontes disponíveis no dump."""
    _asn_valido(asn)
    pais = _codigo_pais(pais)
    items = safe_read("""
        MATCH (a:AS {asn:$asn})-[m:MEMBER_OF]->(ix:IXP)
        OPTIONAL MATCH (ix)-[cr:COUNTRY]-(c:Country)
        WITH ix, m, cr, c
        WHERE $pais IS NULL OR c.country_code = $pais
        RETURN ix.name AS ixp, c.country_code AS pais,
               collect(DISTINCT m.reference_name) AS fontes_membro,
               collect(DISTINCT cr.reference_name) AS fontes_pais
        ORDER BY ixp, pais
        LIMIT $limite
    """, asn=asn, pais=pais, limite=limite)
    return {'asn': asn, 'pais_filtro': pais, 'quantidade': len(items), 'ixps': items,
            'observacao': 'País refere-se ao IXP, não à sede ou presença física do AS. Membros dependem das fontes consultadas.'}


@app.get('/ases/{asn}/siblings', tags=['Relações do grafo'])
def siblings_do_as(asn: int, limite: int = Query(default=50, ge=1, le=200)):
    """ASes ligados diretamente por SIBLING_OF; não infere siblings apenas pelo nome."""
    _asn_valido(asn)
    items = safe_read("""
        MATCH (a:AS {asn:$asn})-[r:SIBLING_OF]-(s:AS)
        WHERE s.asn <> $asn
        RETURN s.asn AS asn, collect(DISTINCT r.reference_name) AS fontes
        ORDER BY asn
        LIMIT $limite
    """, asn=asn, limite=limite)
    return {'asn': asn, 'quantidade': len(items), 'siblings': items,
            'observacao': 'Siblings refletem a classificação da fonte; não necessariamente prova definitiva de propriedade comum.'}


@app.get('/ases/{asn}/top-dominios', tags=['Relações do grafo'])
def top_dominios_do_as(
    asn: int,
    limite: int = Query(default=10, ge=1, le=50),
    ranking_max: int = Query(default=10000, ge=1, le=1000000),
    tld: str | None = Query(default=None, description='Sufixo DNS opcional, como br, com.br ou jp; NÃO indica país de hospedagem'),
):
    """Domínios ranqueados que resolveram para IPs em prefixos originados pelo AS."""
    _asn_valido(asn)
    sufixo = _sufixo_dominio(tld)
    items = safe_read("""
        MATCH (:AS {asn:$asn})-[orig:ORIGINATE]->(p:Prefix)
        WHERE orig.reference_name = 'bgpkit.pfx2asn'
        MATCH (ip:IP)-[:PART_OF]->(p)
        MATCH (h:HostName)-[dns:RESOLVES_TO]->(ip)
        WHERE dns.reference_name STARTS WITH 'openintel.'
        MATCH (h)-[dom:PART_OF]->(d:DomainName)
        MATCH (d)-[r:RANK]->(ranking:Ranking)
        WHERE r.rank <= $ranking_max
          AND ($sufixo IS NULL OR toLower(d.name) ENDS WITH $sufixo)
          AND d.name = h.name
          AND dom.reference_name = dns.reference_name
        RETURN d.name AS dominio, ranking.name AS ranking,
               min(r.rank) AS posicao,
               collect(DISTINCT p.prefix)[0..5] AS prefixos,
               collect(DISTINCT ip.ip)[0..5] AS ips,
               collect(DISTINCT dns.reference_name) AS fontes_dns,
               collect(DISTINCT orig.reference_name) AS fontes_origem
        ORDER BY posicao ASC, dominio ASC
        LIMIT $limite
    """, asn=asn, limite=limite, ranking_max=ranking_max, sufixo=sufixo)
    return {'asn': asn, 'quantidade': len(items), 'ranking_max': ranking_max,
            'tld': tld, 'dominios': items,
            'observacao': 'São domínios de rankings que resolveram para IPs em prefixos anunciados pelo AS no snapshot. TLD não é geolocalização; posição depende do ranking.'}


@app.get('/prefixos/top-dominios', tags=['Relações do grafo'])
def top_dominios_do_prefixo(
    cidr: str = Query(description='Prefixo BGP exato, ex.: 8.8.8.0/24'),
    limite: int = Query(default=10, ge=1, le=50),
    ranking_max: int = Query(default=10000, ge=1, le=1000000),
    tld: str | None = Query(default=None, description='Sufixo DNS opcional; não é país geográfico'),
):
    """Domínios de rankings resolvidos para IPs pertencentes ao prefixo BGP exato."""
    prefixo = _prefixo_valido(cidr)
    sufixo = _sufixo_dominio(tld)
    items = safe_read("""
        MATCH (p:BGPPrefix {prefix:$prefixo})<-[:PART_OF]-(ip:IP)
        MATCH (h:HostName)-[dns:RESOLVES_TO]->(ip)
        WHERE dns.reference_name STARTS WITH 'openintel.'
        MATCH (h)-[dom:PART_OF]->(d:DomainName)
        MATCH (d)-[r:RANK]->(ranking:Ranking)
        WHERE r.rank <= $ranking_max
          AND ($sufixo IS NULL OR toLower(d.name) ENDS WITH $sufixo)
          AND d.name = h.name
          AND dom.reference_name = dns.reference_name
        RETURN d.name AS dominio, ranking.name AS ranking,
               min(r.rank) AS posicao,
               collect(DISTINCT ip.ip)[0..5] AS ips,
               collect(DISTINCT dns.reference_name) AS fontes_dns
        ORDER BY posicao ASC, dominio ASC
        LIMIT $limite
    """, prefixo=prefixo, limite=limite, ranking_max=ranking_max, sufixo=sufixo)
    return {'prefixo': prefixo, 'quantidade': len(items), 'ranking_max': ranking_max,
            'tld': tld, 'dominios': items,
            'observacao': 'Relação derivada de DNS, ranking e prefixo BGP. Pode haver múltiplos IPs e múltiplos rankings por domínio.'}


@app.get('/ases/{asn}/relacoes', tags=['Relações do grafo'])
def tipos_de_relacoes_do_as(asn: int, limite: int = Query(default=30, ge=1, le=100)):
    """Descobre os tipos de conexões diretas existentes para um AS no dump carregado."""
    _asn_valido(asn)
    items = safe_read("""
        MATCH (a:AS {asn:$asn})-[r]-(vizinho)
        RETURN type(r) AS relacao, labels(vizinho) AS tipo_vizinho,
               r.reference_name AS fonte, count(*) AS ocorrencias
        ORDER BY ocorrencias DESC
        LIMIT $limite
    """, asn=asn, limite=limite)
    return {'asn': asn, 'quantidade': len(items), 'relacoes': items}


# ---- Perfil integrado: uma chamada REST, consultas Cypher pequenas ----


def _perfil_as(
    asn: int,
    limite_ixps: int,
    limite_siblings: int,
    limite_prefixos: int,
    limite_dominios: int,
    ranking_max: int,
    pais_ixp: str | None,
    tld: str | None,
    incluir_dominios: bool,
) -> dict:
    """Agrupa os dados de um ASN; falha de uma seção não descarta as demais."""
    _asn_valido(asn)

    # A existência do AS é fundamental: 404 é propagado, não vira perfil vazio.
    # Os campos fundamentais (nomes, tags, países e organizações) reaproveitam
    # o endpoint v0.1, que preserva a procedência de cada relação.
    basicos = detalhes_as(asn)
    erros: list[dict] = []

    def secao(nome: str, func):
        try:
            return func()
        except HTTPException as exc:
            if exc.status_code != 503:
                raise
            erros.append({
                "secao": nome,
                "motivo": "Consulta indisponível ou excedeu o tempo limite",
            })
            return []

    ixps = secao("ixps", lambda: ixps_do_as(
        asn=asn, limite=limite_ixps, pais=pais_ixp,
    )["ixps"])
    siblings = secao("siblings", lambda: siblings_do_as(
        asn=asn, limite=limite_siblings,
    )["siblings"])
    prefixos = secao("prefixos", lambda: safe_read("""
        MATCH (:AS {asn:$asn})-[r:ORIGINATE]->(p:BGPPrefix)
        RETURN DISTINCT p.prefix AS prefixo, r.reference_name AS fonte
        ORDER BY prefixo
        LIMIT $limite
    """, asn=asn, limite=limite_prefixos))

    if incluir_dominios:
        dominios = secao("top_dominios", lambda: top_dominios_do_as(
            asn=asn,
            limite=limite_dominios,
            ranking_max=ranking_max,
            tld=tld,
        )["dominios"])
    else:
        dominios = []

    return {
        "asn": asn,
        "nomes": basicos["nomes"],
        "tags": basicos["tags"],
        "paises": basicos["paises"],
        "organizacoes": basicos["organizacoes"],
        "ixps": ixps,
        "siblings": siblings,
        "prefixos": prefixos,
        "top_dominios": dominios,
        "dominios_consultados": incluir_dominios,
        "limites_por_secao": {
            "ixps": limite_ixps,
            "siblings": limite_siblings,
            "prefixos": limite_prefixos,
            "top_dominios": limite_dominios if incluir_dominios else 0,
            "ranking_max": ranking_max,
        },
        "filtros": {"pais_ixp": pais_ixp, "tld": tld},
        "perfil_parcial": bool(erros),
        "erros_secoes": erros,
        "observacoes": [
            "Listas têm limites por seção e não representam necessariamente todos os registros do IYP.",
            "País do AS, país de IXP e sufixo de domínio são conceitos diferentes.",
            "Domínios dependem de rankings, resolução DNS e origem BGP observados no dump; não são exaustivos.",
            "Sem resultados não prova inexistência: pode ser ausência da informação nas fontes do dump.",
        ],
    }


@app.get("/ases/{asn}/perfil", tags=["Perfil completo"])
def perfil_por_asn(
    asn: int,
    limite_ixps: int = Query(default=20, ge=1, le=100),
    limite_siblings: int = Query(default=20, ge=1, le=100),
    limite_prefixos: int = Query(default=50, ge=1, le=200),
    limite_dominios: int = Query(default=5, ge=1, le=20),
    ranking_max: int = Query(default=1000, ge=1, le=1000000),
    pais_ixp: str | None = Query(default=None, description="País do IXP, ex.: BR"),
    tld: str | None = Query(default=None, description="Sufixo de domínio, ex.: br (não indica localização)"),
    incluir_dominios: bool = Query(default=True, description="Se false, pula a consulta potencialmente pesada"),
):
    """Perfil integrado por ASN. Uma chamada HTTP, várias consultas de leitura."""
    pais_ixp = _codigo_pais(pais_ixp)
    _sufixo_dominio(tld)  # valida antes de acessar o banco
    return _perfil_as(asn, limite_ixps, limite_siblings, limite_prefixos,
                      limite_dominios, ranking_max, pais_ixp, tld, incluir_dominios)


@app.get("/perfil", tags=["Perfil completo"])
def perfil_por_asn_ou_nome(
    asn: int | None = Query(default=None, description="Informe ASN OU nome"),
    nome: str | None = Query(default=None, min_length=2, max_length=80, description="Informe ASN OU nome"),
    limite_ases: int = Query(default=2, ge=1, le=3),
    limite_ixps: int = Query(default=20, ge=1, le=100),
    limite_siblings: int = Query(default=20, ge=1, le=100),
    limite_prefixos: int = Query(default=50, ge=1, le=200),
    limite_dominios: int = Query(default=5, ge=1, le=20),
    ranking_max: int = Query(default=1000, ge=1, le=1000000),
    pais_ixp: str | None = Query(default=None, description="País dos IXPs"),
    tld: str | None = Query(default=None, description="Sufixo DNS, não geolocalização"),
    incluir_dominios: bool = Query(default=True),
):
    """Pesquisa por ASN ou nome, retornando perfis integrados para ASNs distintos."""
    if (asn is None) == (nome is None):
        raise HTTPException(status_code=422, detail="Informe exatamente um dos parâmetros: asn ou nome")
    pais_ixp = _codigo_pais(pais_ixp)
    _sufixo_dominio(tld)
    if asn is not None:
        _asn_valido(asn)
        candidatos = [{"asn": asn, "nomes_coincidentes": []}]
        mais_resultados = False
    else:
        assert nome is not None
        nome = nome.strip()
        if len(nome) < 2:
            raise HTTPException(status_code=422, detail="Nome deve ter no mínimo dois caracteres")
        candidatos = safe_read("""
            MATCH (n:Name)
            WHERE toLower(n.name) CONTAINS $nome
            MATCH (n)-[:NAME]-(a:AS)
            WITH a, collect(DISTINCT n.name)[0..5] AS nomes_coincidentes
            RETURN a.asn AS asn, nomes_coincidentes
            ORDER BY asn
            LIMIT $limite
        """, nome=nome.lower(), limite=limite_ases + 1)
        mais_resultados = len(candidatos) > limite_ases
        candidatos = candidatos[:limite_ases]
        if not candidatos:
            raise HTTPException(status_code=404, detail="Nenhum ASN encontrado para este nome")

    resultados = []
    for candidato in candidatos:
        perfil = _perfil_as(
            candidato["asn"], limite_ixps, limite_siblings,
            limite_prefixos, limite_dominios, ranking_max, pais_ixp,
            tld, incluir_dominios,
        )
        if nome is not None:
            perfil["nomes_coincidentes"] = candidato["nomes_coincidentes"]
        resultados.append(perfil)

    return {
        "consulta": {"asn": asn, "nome": nome},
        "quantidade_ases": len(resultados),
        "mais_ases_correspondentes": mais_resultados,
        "resultados": resultados,
        "observacao": "Busca por nome pode ser ambígua e lenta; resultados são ASNs distintos, ordenados numericamente, não por relevância.",
    }


@app.get("/consulta", tags=["Perfil completo"])
def consulta_unificada(
    asn: int | None = Query(default=None, description="ASN exato"),
    nome: str | None = Query(default=None, min_length=2, max_length=80, description="Nome parcial do AS"),
    prefixo: str | None = Query(default=None, min_length=3, max_length=50, description="Prefixo BGP exato em CIDR"),
    pais: str | None = Query(default=None, description="País diretamente associado ao AS (ISO alfa-2)"),
    tag: str | None = Query(default=None, min_length=1, max_length=100, description="Tag exata, sensível a maiúsculas/minúsculas"),
    limite_ases: int = Query(default=2, ge=1, le=3),
    limite_ixps: int = Query(default=20, ge=1, le=100),
    limite_siblings: int = Query(default=20, ge=1, le=100),
    limite_prefixos: int = Query(default=50, ge=1, le=200),
    limite_dominios: int = Query(default=5, ge=1, le=20),
    ranking_max: int = Query(default=1000, ge=1, le=1000000),
    pais_ixp: str | None = Query(default=None, description="Filtro independente: país do IXP"),
    tld: str | None = Query(default=None, description="Filtro independente: sufixo DNS, não geolocalização"),
    incluir_dominios: bool = Query(default=True),
):
    """Uma chamada HTTP que resolve ASNs por critério e agrega um perfil por AS.

    Exatamente um seletor é exigido; pais_ixp/tld são filtros das seções,
    não seletores adicionais. Resultado limitado e não necessariamente exaustivo.
    """
    seletores = {"asn": asn, "nome": nome, "prefixo": prefixo, "pais": pais, "tag": tag}
    preenchidos = [chave for chave, valor in seletores.items() if valor is not None]
    if len(preenchidos) != 1:
        raise HTTPException(status_code=422, detail="Informe exatamente um: asn, nome, prefixo, pais ou tag")

    pais_ixp = _codigo_pais(pais_ixp)
    _sufixo_dominio(tld)
    chave = preenchidos[0]
    valor = seletores[chave]
    if chave == "asn":
        _asn_valido(asn)
        candidatos = [{"asn": asn}]
        encontrados_adicionais = False
    else:
        if chave == "nome":
            valor = nome.strip()
            if len(valor) < 2:
                raise HTTPException(status_code=422, detail="Nome deve conter pelo menos dois caracteres")
            statement = """
                MATCH (n:Name) WHERE toLower(n.name) CONTAINS $valor
                MATCH (n)-[:NAME]-(a:AS)
                RETURN DISTINCT a.asn AS asn ORDER BY asn LIMIT $limite
            """
            valor = valor.lower()
        elif chave == "prefixo":
            valor = _prefixo_valido(prefixo)
            statement = """
                MATCH (:BGPPrefix {prefix:$valor})<-[:ORIGINATE]-(a:AS)
                RETURN DISTINCT a.asn AS asn ORDER BY asn LIMIT $limite
            """
        elif chave == "pais":
            valor = _codigo_pais(pais)
            statement = """
                MATCH (a:AS)-[:COUNTRY]-(c:Country {country_code:$valor})
                RETURN DISTINCT a.asn AS asn ORDER BY asn LIMIT $limite
            """
        else:  # tag
            valor = tag.strip()
            if not valor:
                raise HTTPException(status_code=422, detail="Tag não pode ser vazia")
            statement = """
                MATCH (a:AS)-[:CATEGORIZED]->(t:Tag {label:$valor})
                RETURN DISTINCT a.asn AS asn ORDER BY asn LIMIT $limite
            """
        candidatos = safe_read(statement, valor=valor, limite=limite_ases + 1)
        encontrados_adicionais = len(candidatos) > limite_ases
        candidatos = candidatos[:limite_ases]

    perfis = []
    for candidato in candidatos:
        perfis.append(_perfil_as(
            candidato["asn"], limite_ixps, limite_siblings,
            limite_prefixos, limite_dominios, ranking_max,
            pais_ixp, tld, incluir_dominios,
        ))

    return {
        "consulta": {chave: valor},
        "quantidade_ases": len(perfis),
        "mais_ases_correspondentes": encontrados_adicionais,
        "resultados": perfis,
        "observacoes": [
            "A busca por nome é parcial e não ordena por relevância.",
            "A busca por tag é exata e sensível a caixa; prefixo exige correspondência CIDR exata.",
            "O país do seletor se refere a COUNTRY ligado diretamente ao AS; pais_ixp filtra IXPs.",
            "Resultados por ASN e por seção são limitados e não demonstram ausência global de dados.",
        ],
    }

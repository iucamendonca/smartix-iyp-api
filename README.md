# SmartIX IYP API — consulta integrada (v0.4)

API REST de **leitura** sobre uma instância local do [Internet Yellow Pages (IYP)](https://github.com/InternetHealthReport/internet-yellow-pages). Recebe um critério de pesquisa, encontra ASNs e reúne suas informações em **uma resposta HTTP**, com consultas Cypher parametrizadas e separadas para cada seção.

> **Status de validação (07/11/2026):** os 20 testes unitários da v0.4 passaram, com driver Neo4j simulado. No CachyOS do autor, o `GET /health/ready` respondeu 200 e a consulta integrada por ASN com `incluir_dominios=false` retornou dados. A consulta com `incluir_dominios=true` respondeu **`perfil_parcial=true`**, com timeout/indisponibilidade na seção `top_dominios`. Diagnósticos diretos no Neo4j confirmaram prefixos de AS15169 e domínios ranqueados, mas **não confirmaram a cadeia DNS → IP → prefixo → AS nem validaram a consulta completa de top domains**. Portanto, esta versão é **candidata para entrega acadêmica com essa limitação declarada**, não uma implementação totalmente validada de top domains.

## Arquitetura

```text
Cliente HTTP (curl/Swagger)
       | GET /consulta?asn=15169
       v
[ API FastAPI / Docker ] -- Bolt/Cypher --> [ IYP Neo4j / Docker ]
       |
       +-- identificação/nome, tags, país do AS, organizações
       +-- IXPs (e país dos IXPs), siblings, prefixos BGP
       +-- top domains (ranking + DNS + IP + prefixo + origem BGP)
       |
       v
 JSON: um perfil por ASN, fontes e erros parciais por seção
```

O `compose.yaml` inicia dois serviços permanentes (`api` e `iyp`). Um perfil opcional `setup` permite executar o container **temporário** de restauração `iyp-loader` quando necessário. Em operação normal, ele não permanece em execução.

## API

Documentação OpenAPI interativa: **http://127.0.0.1:8000/docs**.

**Consulta integrada** — exatamente um critério principal por requisição:

```bash
curl -sS 'http://127.0.0.1:8000/consulta?asn=15169&incluir_dominios=false'
curl -sS 'http://127.0.0.1:8000/consulta?nome=Google&limite_ases=2&incluir_dominios=false'
curl -sS 'http://127.0.0.1:8000/consulta?prefixo=8.8.8.0%2F24&incluir_dominios=false'
curl -sS 'http://127.0.0.1:8000/consulta?pais=BR&limite_ases=2&incluir_dominios=false'
curl -sS 'http://127.0.0.1:8000/consulta?tag=Content&limite_ases=2&incluir_dominios=false'
```

`asn`, `nome`, `prefixo`, `pais` e `tag` são **seletores alternativos** — não combinar na mesma chamada. `pais_ixp=BR` é filtro dos IXPs de perfis selecionados por outro critério; `tld=br` é filtro de sufixo DNS, **não** de localização nem ranking brasileiro. A busca por tag exige correspondência exata, incluindo capitalização. O prefixo exige CIDR exato. A busca por nome é parcial, pode ser lenta e não ordena por relevância.

**Exemplo de resposta resumida, apenas para ilustrar o formato:**

```json
{
  "consulta": {"asn": 15169},
  "quantidade_ases": 1,
  "mais_ases_correspondentes": false,
  "resultados": [{
    "asn": 15169,
    "nomes": [], "tags": [], "paises": [], "organizacoes": [],
    "ixps": [], "siblings": [], "prefixos": [], "top_dominios": [],
    "dominios_consultados": false,
    "limites_por_secao": {"ixps": 20, "siblings": 20, "prefixos": 50, "top_dominios": 0, "ranking_max": 1000},
    "filtros": {"pais_ixp": null, "tld": null},
    "perfil_parcial": false, "erros_secoes": [], "observacoes": []
  }],
  "observacoes": []
}
```

A resposta real preenche as listas quando o IYP contém registros e inclui fontes no nível dos itens. `perfil_parcial: true` indica falha em pelo menos uma seção opcional (por exemplo, timeout dos domínios). **Uma lista vazia não prova ausência real de IXPs, irmãos ou domínios.** O limite de ASNs encontrados é 3 por chamada, e as listas internas também são limitadas.

### Endpoints auxiliares

- `GET /health`, `GET /health/ready`: liveness e conexão com o Neo4j.
- `GET /ases/busca?nome=Google`, `GET /ases/{asn}`: nomes, atributos básicos e tags.
- `GET /ases/{asn}/perfil`, `GET /perfil?nome=Google`: perfil por ASN e consulta de compatibilidade da v0.3.
- `GET /ases/{asn}/ixps`, `/siblings`, `/top-dominios`, `/relacoes`: inspeção por seção.
- `GET /prefixos?cidr=...`, `/prefixos/top-dominios?cidr=...`, `/paises/{codigo}/ases`: consultas específicas.

## Executar em Linux com Docker Compose

**Primeira instalação:** requer Docker, Compose, Python 3 e curl, além de espaço para o dump e a base expandida. Confira a documentação do IYP para os requisitos atuais. Na pasta do projeto:

```bash
./scripts/iniciar.sh
# Na primeira execução, o script descobre, baixa e restaura o dump: operação grande.
```

**Se o banco já foi restaurado:** use apenas:

```bash
docker compose up -d --build --no-deps api
curl -i http://127.0.0.1:8000/health/ready
```

O `docker compose` publica portas só em `127.0.0.1` por padrão, isto é, **não publica o banco diretamente na Internet**. Para um servidor da universidade, configure firewall, controles de acesso, TLS/reverse proxy e restrições antes de expor a API. O Neo4j local está sem autenticação; nunca exponha Bolt/Browser publicamente neste modo.

### Diagnóstico do banco **real**

```bash
./scripts/diagnostico_neo4j.sh   # tipologia e exemplos das relações, com LIMIT
./scripts/testar_api.sh          # valida leitura real da API e perfis sem domínios
```

Teste dos domínios separado (pode ser custoso):

```bash
curl --max-time 90 -sS 'http://127.0.0.1:8000/consulta?asn=15169&limite_dominios=3&ranking_max=1000'
```

**Resultado real observado:** na consulta com `asn=15169&incluir_dominios=true&limite_dominios=5&ranking_max=1000`, o campo `top_dominios` veio vazio e `perfil_parcial=true`, com erro na seção `top_dominios` por limite de tempo/indisponibilidade. Isso **não** significa que o AS não tenha domínios. O timeout de 20 s do Neo4j é distinto do timeout do cliente curl. Não amplie indiscriminadamente `limite_dominios`, `ranking_max` nem o timeout; o percurso pode gerar muitos resultados intermediários. Consulte `ENTREGA-E-LIMITACOES.md` para o plano de verificação e otimização.

### Atualização periódica do dump

O script `scripts/atualizar.sh` consulta o arquivo oficial, prepara a restauração separada e tenta preservar o banco antigo para rollback. Ele pode exigir **espaço para duas bases** durante a atualização e causa uma janela de indisponibilidade na troca. Instalação opcional de timer no host via `scripts/instalar_timer.sh` (revise-o antes de habilitar). Não são mantidos dumps ou credenciais no Git.

## Testes unitários e CI

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r api/requirements-dev.txt
cd api && PYTHONPATH=. python -m pytest -q
```

O workflow `.github/workflows/tests.yml` executa esses testes em push/pull request. Os testes **simulam** o driver e **não substituem** testes com Neo4j real. `docker compose config` deve ser validado no computador com Docker instalado.

## Limitações e definições

- **País do AS**: relacionamento `COUNTRY` direto; país de registro e geolocalização podem diferir conforme a fonte.
- **País do IXP**: país do ponto de troca, não do AS pesquisado.
- **Domínio .br**: sufixo DNS, não geolocalização, origem empresarial ou popularidade no Brasil.
- **Top domains**: associação derivada de ranking, DNS, IP e origem BGP em um snapshot; não implica hospedagem física exclusiva nem propriedade do domínio pelo AS. A consulta é potencialmente custosa.
- **Siblings**: resultado de `SIBLING_OF` conforme a fonte; organização comum não é inferida pelo texto do nome.
- **Fontes**: relações trazem `reference_name` quando fornecido pelo IYP; a procedência das informações influencia a interpretação.
- **Atualidade**: os dados refletem a data do dump, não o estado em tempo real.
- **Proteção de recursos**: até três ASNs por requisição, limites por seção, timeout configurável. Falhas nos dados básicos podem provocar 503 geral, enquanto falhas em seções opcionais preservam o perfil parcial.

**Fontes oficiais:** [documentação de nós](https://github.com/InternetHealthReport/internet-yellow-pages/blob/main/documentation/node-types.md), [relacionamentos](https://github.com/InternetHealthReport/internet-yellow-pages/blob/main/documentation/relationship-types.md), [galeria Cypher](https://github.com/InternetHealthReport/internet-yellow-pages/blob/main/documentation/gallery.md) e [repositório IYP](https://github.com/InternetHealthReport/internet-yellow-pages).

## Organização do repositório

```text
api/app/main.py               # endpoints e orquestração
api/app/db.py                 # driver Neo4j de leitura
api/tests/                   # testes unitários sem banco
api/Dockerfile               # container API
compose.yaml                 # API, IYP e loader temporário via profile
scripts/                     # download, restauração, diagnóstico, atualização
.github/workflows/tests.yml # CI
```

Este repositório contém **código e scripts**, não o banco de dados ou dumps do IYP. A infraestrutura e os dados do IYP original são de terceiros e devem ser atribuídos às suas respectivas fontes.

## Publicação no GitHub

Criar repositório **vazio** chamado `smartix-iyp-api`, separado de `iyp-neo4j-topology`. Os dados do Neo4j e os dumps não vão ao Git. Antes de `git add`, confira com `git status --short` e `git check-ignore storage/data/arquivo-exemplo` a proteção oferecida pelo `.gitignore`. Não execute `docker compose down -v` para publicar o projeto.

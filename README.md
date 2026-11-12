# SmartIX IYP API

API REST para consultar dados do [Internet Yellow Pages (IYP)](https://github.com/InternetHealthReport/internet-yellow-pages) em uma instância local do Neo4j.

A ideia do projeto é oferecer uma forma mais simples de consultar ASes sem precisar escrever Cypher a cada pesquisa. A API recebe um identificador (ASN, nome, prefixo, país ou tag), encontra os ASNs relacionados e reúne as informações disponíveis em um JSON. O desenvolvimento faz parte do trabalho de integração com o SmartIX.

## O que a API consulta

O endpoint principal é `GET /consulta`. É necessário informar **um** destes parâmetros por vez:

| Parâmetro | Exemplo | Como funciona |
| --- | --- | --- |
| `asn` | `15169` | Procura um AS específico |
| `nome` | `Google` | Busca parcial nos nomes associados a ASes |
| `prefixo` | `8.8.8.0/24` | Procura ASes que originam o prefixo exato |
| `pais` | `BR` | Filtra pelo país associado diretamente ao AS nas fontes do IYP |
| `tag` | `Content` | Busca por uma tag com correspondência exata |

Cada perfil pode trazer nomes, tags, organizações, países, IXPs, siblings, prefixos BGP e domínios ranqueados. Os resultados vêm acompanhados das fontes quando o IYP fornece essa informação.

Alguns exemplos que usamos nos testes:

```bash
curl -sS 'http://127.0.0.1:8000/consulta?asn=15169&incluir_dominios=false'
curl -sS 'http://127.0.0.1:8000/consulta?nome=Google&limite_ases=2&incluir_dominios=false'
curl -sS 'http://127.0.0.1:8000/consulta?prefixo=8.8.8.0%2F24&limite_ases=1&incluir_dominios=false'
curl -sS 'http://127.0.0.1:8000/consulta?pais=BR&limite_ases=1&incluir_dominios=false'
curl -sS 'http://127.0.0.1:8000/consulta?tag=Content&limite_ases=1&incluir_dominios=false'
```

O parâmetro `incluir_dominios=false` deixa de executar a seção mais pesada do perfil. Outras opções, como `limite_prefixos`, `limite_ixps` e `limite_siblings`, controlam o tamanho da resposta. Todas as opções e rotas auxiliares estão documentadas no [Swagger](http://127.0.0.1:8000/docs) quando a API está rodando localmente.

## Organização do projeto

```text
Cliente HTTP / Swagger
         |
         v
  FastAPI (container api)
         |
     Bolt / Cypher
         |
  Neo4j (container iyp)
```

O `compose.yaml` define **dois serviços permanentes**: `api` e `iyp`. Existe também o `iyp-loader`, usado somente no perfil `setup` para a restauração do dump. O banco não faz parte do repositório Git.

Arquivos principais:

- `api/app/main.py` — rotas e agregação das consultas.
- `api/app/db.py` — conexão e execução de Cypher em modo de leitura.
- `api/tests/` — testes unitários com respostas simuladas do Neo4j.
- `compose.yaml` — configuração dos containers.
- `scripts/` — download/restauração, diagnóstico e testes locais.

## Executando com Docker

Requisitos: Docker e Docker Compose. Os scripts de preparação também usam Python 3, Bash e curl. Uma instalação completa do IYP exige bastante espaço em disco; o dump utilizado nos testes locais é de **01/11/2026**.

**Se você já possui o banco restaurado**, mantenha seus dados fora da pasta do código. No arquivo `.env`, configure `IYP_DATA_DIR` com o **caminho absoluto** para o diretório `data` do Neo4j. Antes de iniciar, confira o volume com `docker compose config`.

```bash
cp .env.example .env
# Edite .env: IYP_DATA_DIR=/caminho/absoluto/para/iyp-dados/data
docker compose config
docker compose up -d --build
docker compose ps
curl -i http://127.0.0.1:8000/health/ready
```

O retorno esperado de `/health/ready` é HTTP 200 e `{"status":"ready","neo4j":"conectado"}`. Se o Neo4j ainda estiver inicializando, tente novamente após verificar os logs.

Para preparar **uma nova instalação**, existe `bash scripts/iniciar.sh`, que localiza o dump, faz o download e realiza a restauração. Essa etapa é pesada e deve ser feita somente após conferir o espaço disponível e o destino dos dados.

O Neo4j está configurado sem autenticação e as portas são publicadas somente em `127.0.0.1`. **Não exponha essa configuração diretamente à Internet.**

## Testes realizados

Em 12/11/2026, depois de recuperar a base local e reiniciar os containers, foram repetidas consultas reais por ASN, nome, prefixo, país e tag. Todas retornaram ASNs e `perfil_parcial=false` com a seção de domínios desabilitada. Exemplos observados:

| Consulta | ASN(s) retornado(s) |
| --- | --- |
| `asn=15169` | 15169 |
| `nome=Google&limite_ases=2` | 6432, 13949 |
| `prefixo=8.8.8.0/24` | 15169 |
| `pais=BR&limite_ases=1` | 1251 |
| `tag=Content&limite_ases=1` | 42 |

Também foram visualizados no Neo4j Browser relacionamentos `NAME`, `CATEGORIZED`, `MEMBER_OF` e `ORIGINATE` do AS15169.

Para repetir os testes rápidos com o banco real:

```bash
bash scripts/testar_api.sh
bash scripts/diagnostico_neo4j.sh
```

Separadamente, o [GitHub Actions](https://github.com/iucamendonca/smartix-iyp-api/actions) executa os testes unitários com `pytest` a cada push e pull request. São testes com dados simulados: **não substituem** os testes de integração acima.

## Limitações conhecidas

- **Busca por nome:** vários ASNs podem ter nomes parecidos ou associados à mesma empresa. A correspondência é parcial, não ordena por relevância e pode ser lenta em uma base grande. Um nome parecido não comprova que dois ASes são siblings.
- **País:** o país ligado ao AS não é necessariamente sua localização física. O país de um IXP e um domínio terminado em `.br` são informações distintas.
- **Cobertura:** os dados dependem das fontes e da data do dump. Listas são limitadas; uma lista vazia não prova que a relação não existe.
- **Top domains:** os rankings e as relações DNS foram encontrados no Neo4j, mas a consulta completa por ASN ainda apresentou timeout. Quando ocorre falha em uma seção opcional, a API marca `perfil_parcial=true` e informa o problema em `erros_secoes`.
- **Atualização do dump:** a rotina de troca de bancos e rollback ainda precisa ser revisada e testada antes de habilitar o agendamento automático. Não execute `scripts/atualizar.sh` em uma base importante sem essa revisão.

As evidências dos testes e as pendências estão detalhadas em [ENTREGA-E-LIMITACOES.md](ENTREGA-E-LIMITACOES.md).

## Referências

- [Internet Yellow Pages — repositório oficial](https://github.com/InternetHealthReport/internet-yellow-pages)
- [Tipos de nós](https://github.com/InternetHealthReport/internet-yellow-pages/blob/main/documentation/node-types.md)
- [Tipos de relacionamentos](https://github.com/InternetHealthReport/internet-yellow-pages/blob/main/documentation/relationship-types.md)
- [Exemplos de consultas Cypher](https://github.com/InternetHealthReport/internet-yellow-pages/blob/main/documentation/gallery.md)

# Validação e limitações — SmartIX IYP API v0.4

Registro das verificações feitas no ambiente local (CachyOS) e das partes que ainda exigem trabalho. Última atualização deste documento: **12/11/2026**.

## O que foi testado

**Infraestrutura:** dois containers em execução (`api` e `iyp`). O endpoint `GET /health/ready` respondeu HTTP 200 e confirmou a conexão com o Neo4j. A base foi recuperada de um diretório apagado anteriormente e está separada da pasta de código.

**Consulta unificada (Neo4j real):** em 12/11, com `incluir_dominios=false`, foram executadas pesquisas por ASN 15169, nome Google, prefixo 8.8.8.0/24, país BR e tag Content. Todas retornaram resultados e nenhuma reportou erro parcial. Os exemplos registrados foram:

| Filtro | Resultado |
| --- | --- |
| ASN 15169 | AS15169 |
| Nome Google (limite 2) | AS6432 e AS13949 |
| Prefixo 8.8.8.0/24 | AS15169 |
| País BR (limite 1) | AS1251 |
| Tag Content (limite 1) | AS42 |

**Grafo:** o Neo4j Browser exibiu, para AS15169, relações de nomes e tags, presença em IXPs e prefixos anunciados. Em testes anteriores, a fonte `bgpkit.pfx2asn` apresentou 1.461 prefixos distintos associados ao AS15169. Para `google.com` foram observados vínculos com rankings, HostName e resoluções DNS em fontes OpenINTEL.

**Testes automatizados:** 20 testes unitários passaram no GitHub Actions, cobrindo respostas da API e falhas simuladas. O Neo4j é simulado nesses testes; por isso, eles não avaliam desempenho nem cobertura do dump real.

## O que ainda falta

### Consulta de top domains

A chamada `/consulta?asn=15169&incluir_dominios=true&limite_dominios=5&ranking_max=1000` retornou `perfil_parcial=true` e erro na seção `top_dominios` devido a timeout/indisponibilidade. Confirmamos isoladamente rankings, associações HostName–DomainName e resoluções DNS. **A cadeia completa domínio → IP → prefixo → AS ainda precisa ser validada e otimizada.** Não devemos interpretar `top_dominios: []` após erro como ausência de domínios.

O `EXPLAIN` no Neo4j mostrou início por índice de ASN (`NodeUniqueIndexSeek`), seguido de expansões por relações. As cardinalidades exibidas eram estimativas, não contagens reais; ainda não foi testada uma implementação mais rápida.

### Atualização automática

`scripts/atualizar.sh` ainda não foi validado em uma instalação isolada com rollback. O procedimento precisa considerar montagem de volumes e recriação de containers, especialmente quando `IYP_DATA_DIR` aponta para um diretório externo. **Não habilitar `scripts/instalar_timer.sh` até concluir a revisão.**

### Ambiente externo

A aplicação local usa Neo4j sem autenticação, com portas ligadas a `127.0.0.1`. Para colocar no servidor da universidade, é necessário rever acesso, firewall, autenticação e publicação da API. A restauração e a atualização dos dumps devem ser testadas nesse ambiente.

## Evidências para demonstração

- `docker compose ps`: os dois serviços permanentes.
- `curl -i http://127.0.0.1:8000/health/ready`: estado da API e conexão com o banco.
- `bash scripts/testar_api.sh`: consultas reais por ASN e nome.
- Swagger em `http://127.0.0.1:8000/docs`: execução do endpoint `GET /consulta`.
- Neo4j Browser em `http://127.0.0.1:7474/browser/`: nós e arestas de AS15169.
- [GitHub Actions](https://github.com/iucamendonca/smartix-iyp-api/actions): testes unitários.

Observação: `perfil_parcial=false` só atesta que as seções **executadas** não reportaram erro. Quando `incluir_dominios=false`, isso não valida a busca de domínios.

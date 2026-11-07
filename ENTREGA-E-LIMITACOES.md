# Entrega acadêmica — evidências, limitações e próximos testes

Data de revisão: 07/11/2026. Versão: SmartIX IYP API 0.4.0 (candidata à entrega).

## Confirmado

- Infraestrutura Docker com serviços `api` e `iyp`, e container de restauração temporário (`profile: setup`).
- FastAPI `GET /health/ready` respondeu HTTP 200 conectado ao Neo4j no CachyOS.
- Consultas por ASN, nomes e perfil sem domínios foram observadas funcionando na instância local.
- No Neo4j, consulta `(:AS {asn:15169})-[:ORIGINATE]->(:BGPPrefix)` encontrou 1461 prefixos distintos da fonte `bgpkit.pfx2asn` (fotografia da consulta de 07/11/2026), além de outras fontes.
- Consulta `(:Ranking)<-[r:RANK]-(d:DomainName)` com `r.rank<=1000` encontrou `google.com` e `amazonaws.com` em rankings diferentes.
- 20 testes unitários com mock do driver Neo4j passaram neste ambiente. NÃO são testes de integração com a instância real.

## Pendente (não declarar como pronto)

- **Top domains por ASN**: timeout da consulta `/consulta?asn=15169&incluir_dominios=true&limite_dominios=5&ranking_max=1000`. A API retornou `perfil_parcial=true` e informou a seção que falhou. Os dados de ranking e de prefixos existem, mas isso não prova que o caminho conjunto até o ASN seja percorrível ou eficiente.
- Medir plano de execução de top domains (`EXPLAIN` antes de `PROFILE`) e considerar começar pelo ranking, restringir fonte DNS e limitar candidatos **com indicação explícita de amostragem**. Nenhuma otimização foi validada ainda.
- Executar testes de integração da busca por `pais`, `tag` e `prefixo` no dump real; validar se nomes de relação e filtros refletem o IYP de 01/11/2026.
- Testar restaurar/atualizar dump em servidor isolado e avaliar incompatibilidades possíveis entre imagens Neo4j e neo4j-admin. Não presumir que atualizações automáticas estejam prontas para produção.
- Validar `docker compose config` e documentação Swagger no host Linux.

## Interpretação correta

Uma resposta HTTP 200 com `perfil_parcial=true` **não é resultado completo**. `top_dominios: []` com erro não comprova ausência de sites. O país ligado ao AS, país do IXP e domínio terminado em `.br` são conceitos distintos. `SIBLING_OF` depende da fonte. Nomes podem ser ambíguos; prefixos e rankings são snapshots, não dados em tempo real.

## Verificações antes do push

```bash
# Na raiz do projeto; nunca apagar a base carregada
python3 -m compileall -q api/app
cd api && PYTHONPATH=. python3 -m pytest -q && cd ..
docker compose config --quiet
docker compose ps
curl -i http://127.0.0.1:8000/health/ready
curl -sS 'http://127.0.0.1:8000/consulta?asn=15169&incluir_dominios=false' | python3 -m json.tool
# Opcional e mais pesado (pode retornar resposta parcial):
curl -sS --max-time 90 'http://127.0.0.1:8000/consulta?asn=15169&incluir_dominios=true&limite_dominios=3&ranking_max=1000' | python3 -m json.tool
```

Publicar apenas o código, scripts, Dockerfile, Compose e documentação. **Jamais publicar `/storage/`, `.env`, dumps, backups de código ou credenciais**. O `.gitignore` dessa versão protege esses caminhos se forem gerenciados dentro do repositório. Se o banco estiver em volume externo, verifique o caminho separadamente.

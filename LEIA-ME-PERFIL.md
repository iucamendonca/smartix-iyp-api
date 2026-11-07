# SmartIX IYP API v0.3 — Perfil integrado de ASN ou nome

Esta atualização substitui **somente `api/app/main.py`** e acrescenta `api/tests/test_perfil.py`. Ela contém todos os endpoints da versão 0.2 mais a consulta integrada. **Não altere `compose.yaml`, `storage/`, `.env` ou os scripts de backup/restauração. Não baixe o IYP novamente.**

## Instalação no CachyOS

No terminal, entre na pasta `smartix-iyp-api` (a que contém `compose.yaml`):

```bash
cp api/app/main.py api/app/main.py.bak
unzip -o ~/Downloads/smartix-iyp-api-perfil-v0.3.zip
# Confira o compose antes de iniciar
docker compose up -d --build --no-deps api
curl -i http://127.0.0.1:8000/health/ready
```

Confira no Swagger em http://127.0.0.1:8000/docs.

## Endpoints novos

- `GET /ases/15169/perfil`: perfil integrado de ASN específico.
- `GET /perfil?asn=15169`: mesmo tipo de perfil, em uma lista de resultados.
- `GET /perfil?nome=Google`: busca ASNs *distintos* por nome (máximo 3 perfis por requisição). A busca é parcial e sem garantia de ranking por relevância.

Exemplos:

```bash
curl -sS 'http://127.0.0.1:8000/ases/15169/perfil?limite_dominios=5&ranking_max=1000' | python3 -m json.tool
curl -sS 'http://127.0.0.1:8000/perfil?nome=Google&limite_ases=2&incluir_dominios=false' | python3 -m json.tool
curl -sS 'http://127.0.0.1:8000/ases/15169/perfil?pais_ixp=BR&tld=br' | python3 -m json.tool
```

Os campos do perfil são: `asn`, `nomes`, `tags`, `paises`, `organizacoes`, `ixps`, `siblings`, `prefixos`, `top_dominios`, `dominios_consultados`, `perfil_parcial`, `erros_secoes`, `observacoes`.

- `pais_ixp=BR` filtra **país do IXP**, não país do AS.
- `tld=br` filtra sufixo do **domínio**, não localização geográfica nem popularidade no Brasil.
- `incluir_dominios=false` pula a parte mais pesada, útil para testar os demais campos.
- `ranking_max=1000` e `limite_dominios=5` são os padrões de segurança para o grafo grande.
- Para resposta de nome, `mais_ases_correspondentes=true` avisa que o limite não cobriu todos os ASNs encontrados.

## Como funciona

É **uma requisição HTTP** por perfil, mas o backend faz diversas consultas Cypher parametrizadas separadas, cada uma retornando só o necessário. Os limites por seção são intencionais; a resposta **não é exaustiva**. Erros 503 em IXPs, siblings, prefixos ou domínios são reportados em `erros_secoes`, com `perfil_parcial=true`, sem descartar as seções bem-sucedidas. Um erro na leitura dos dados básicos ainda interrompe a requisição. Não existe cache nesta versão; perfis de vários ASNs ou domínios podem consumir recursos e demorar.

**Importante:** o sucesso dos testes unitários não comprova que todas as relações existem no dump instalado. Um array vazio pode significar ausência de dados na fonte, não ausência real da propriedade.

## Verificação dos testes (ambiente de desenvolvimento com dependências instaladas)

```bash
cd api
PYTHONPATH=. python3 -m pytest -q
```

Foram executados 15 testes com dados simulados no ambiente de preparação. Ainda não houve teste end-to-end contra o banco Neo4j do usuário.

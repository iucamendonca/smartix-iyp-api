# Verificação da versão 0.4 antes da entrega

O projeto é uma API de leitura que utiliza dois serviços permanentes no Docker Compose: `api` (FastAPI) e `iyp` (Neo4j). O serviço `iyp-loader` existe somente no perfil `setup` para restaurações. Não publique o banco, dumps ou `.env` no GitHub.

## 1. Aplicar somente o novo backend sem mexer no banco

Na pasta **atual** `smartix-iyp-api` (que já contém um dump restaurado), faça backup de `api/app/main.py` e extraia o pacote incremental. Depois:

```bash
docker compose config --quiet
docker compose up -d --build --no-deps api
curl -fsS http://127.0.0.1:8000/health/ready
```

Não execute `scripts/iniciar.sh` outra vez nesta fase: ele poderia preparar uma carga se a configuração apontar para outro diretório.

## 2. Diagnosticar o Neo4j real (somente leitura)

```bash
bash scripts/diagnostico_neo4j.sh
bash scripts/testar_api.sh
```

A consulta principal também aceita prefixo, país e tag; exemplos no README. Teste os top domains separadamente e com limites pequenos:

```bash
curl -sS --max-time 90 'http://127.0.0.1:8000/consulta?asn=15169&limite_dominios=3&ranking_max=1000' | python3 -m json.tool
```

Inspecione `perfil_parcial`, `erros_secoes` e as fontes retornadas. Resultado vazio não comprova que uma relação não existe; pode faltar na fonte/na amostra.

## 3. Testes e segurança

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r api/requirements-dev.txt
(cd api && PYTHONPATH=. python -m pytest -q)
docker compose ps
```

Verifique se `docker compose ps` mostra apenas a API e o Neo4j em execução, e portas em `127.0.0.1`. Confira `git status --short` e `git ls-files` antes de publicar. `.env`, `*.dump` e `storage/data` não devem constar no repositório.

## 4. Publicar em um repositório **novo**, após passar na validação real

Crie um repositório **vazio** no GitHub chamado `smartix-iyp-api` (sem README, licença ou .gitignore gerados pelo site). Em uma **cópia separada** desta pasta contendo o código, mas **não os dados**, execute:

```bash
git init
git add .
git status --short
git commit -m 'feat: consulta integrada ao IYP por ASN, nome, prefixo, país e tag'
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/smartix-iyp-api.git
git push -u origin main
```

O código é publicado; o dump permanece local. Os testes de integração com o Neo4j real devem ser registrados no relatório antes de afirmar que todo o comportamento foi validado.

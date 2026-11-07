#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

command -v docker >/dev/null || { echo 'Docker não encontrado' >&2; exit 1; }
command -v curl >/dev/null || { echo 'curl não encontrado' >&2; exit 1; }
docker compose version >/dev/null
mkdir -p storage/{data,dumps,plugins}
if [[ ! -f .env ]]; then
  printf 'LOCAL_UID=%s\nLOCAL_GID=%s\nAPI_PORT=8000\n' "$(id -u)" "$(id -g)" > .env
fi

if [[ ! -d storage/data/databases/neo4j ]]; then
  echo 'Banco ainda não existe. A carga recente requer aproximadamente 200 GiB ou mais.'
  FREE_BYTES="$(df -B1 --output=avail storage | tail -1 | tr -d ' ')"
  MIN_FREE_BYTES=$(( 220 * 1024 * 1024 * 1024 ))
  if (( FREE_BYTES < MIN_FREE_BYTES )); then
    echo 'Espaço livre inferior a 220 GiB; download automático cancelado para evitar falta de espaço.' >&2
    echo 'Use um servidor com mais espaço ou ajuste a estratégia para um dump menor.' >&2
    df -h storage >&2
    exit 1
  fi
  echo 'Buscando dump oficial e restaurando...'
  python3 scripts/latest_dump.py --download
  docker compose --profile setup run --rm iyp-loader
  if [[ ! -d storage/data/databases/neo4j ]]; then
    echo 'Restauração incompleta: banco não encontrado.' >&2
    exit 1
  fi
  python3 scripts/latest_dump.py --date > storage/active-date.txt
fi

docker compose up -d --build
printf '\nAPI: http://127.0.0.1:8000/docs (ajuste se alterar API_PORT)\n'
printf 'Neo4j: http://127.0.0.1:7474\n'
printf 'O /health/ready só ficará pronto após o Neo4j concluir a inicialização.\n'

#!/usr/bin/env bash
# Atualização conservadora: prepara novo dump e banco à parte, troca com rollback.
# Executar no host (systemd timer ou manualmente), não dentro do banco de dados.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p storage
exec 9>storage/.update.lock
flock -n 9 || { echo 'Outra atualização já está em curso'; exit 0; }

if [[ ! -f .env ]]; then
  echo 'Execute scripts/iniciar.sh primeiro (arquivo .env ausente)' >&2
  exit 1
fi

NEW="$(python3 scripts/latest_dump.py --date)"
OLD="$(cat storage/active-date.txt 2>/dev/null || true)"
if [[ "$NEW" == "$OLD" ]]; then
  echo "Banco já usa o dump mais recente ($NEW)."
  exit 0
fi
if [[ ! -d storage/data/databases/neo4j ]]; then
  echo 'Banco local não foi inicializado; execute scripts/iniciar.sh primeiro.' >&2
  exit 1
fi

# Duas bases coexistem durante a preparação; requer espaço livre abundante.
OLD_BYTES="$(du -sb storage/data | cut -f1)"
FREE_BYTES="$(df -B1 --output=avail storage | tail -1 | tr -d ' ')"
MIN_BYTES="$(( OLD_BYTES + OLD_BYTES / 3 + 22 * 1024 * 1024 * 1024 ))"
if (( FREE_BYTES < MIN_BYTES )); then
  echo 'Espaço livre insuficiente para atualização segura sem apagar o banco atual.' >&2
  echo "Livre: $FREE_BYTES bytes; mínimo estimado: $MIN_BYTES bytes" >&2
  exit 1
fi

python3 scripts/latest_dump.py --download
if [[ -d storage/data-next/databases/neo4j ]]; then
  echo 'storage/data-next contém restauração anterior. Inspecione-a antes de continuar.' >&2
  exit 1
fi
mkdir -p storage/data-next
IYP_DATA_DIR=./storage/data-next docker compose --profile setup run --rm iyp-loader
if [[ ! -d storage/data-next/databases/neo4j ]]; then
  echo 'Novo banco não foi criado; banco original permanece disponível.' >&2
  exit 1
fi

# A troca pode causar alguns minutos de indisponibilidade; API devolve 503 nesse período.
BACKUP="storage/data-backup-${OLD:-desconhecido}"
if [[ -e "$BACKUP" ]]; then
  echo "Backup anterior ($BACKUP) já existe; recuso sobrescrever." >&2
  exit 1
fi

echo 'Trocando bancos (o anterior será preservado para rollback).'
docker compose stop iyp
mv storage/data "$BACKUP"
mv storage/data-next storage/data

ready() {
  for _ in $(seq 1 60); do
    if docker compose exec -T iyp cypher-shell -a bolt://localhost:7687 'RETURN 1;' >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  return 1
}

if docker compose up -d iyp && ready; then
  printf '%s\n' "$NEW" > storage/active-date.txt
  echo "IYP atualizado para $NEW. Banco anterior preservado: $BACKUP"
else
  echo 'Falha ao iniciar banco novo. Tentando rollback...' >&2
  docker compose stop iyp || true
  mv storage/data "storage/data-failed-$NEW"
  mv "$BACKUP" storage/data
  docker compose up -d iyp
  if ! ready; then
    echo 'ATENÇÃO: Rollback não passou no healthcheck; verificar docker compose logs iyp.' >&2
    exit 1
  fi
  echo 'Rollback concluído. O banco antigo foi preservado.' >&2
  exit 1
fi

#!/usr/bin/env bash
# Smoke tests reais contra a API e o Neo4j local; não validam os valores específicos.
set -Eeuo pipefail
API_BASE="${API_BASE:-http://127.0.0.1:8000}"

check() {
  local path="$1"
  echo "Testando $path"
  curl -fsS --max-time 90 "${API_BASE}${path}" | python3 -c '
import json,sys
v=json.load(sys.stdin)
if "resultados" in v:
    print("ASNs retornados:",[x["asn"] for x in v["resultados"]])
    print("Seções parciais:",[(x["asn"],x["erros_secoes"]) for x in v["resultados"] if x["perfil_parcial"]])
else:
    print("Status:", v.get("status", "sem status"))
'
}

check '/health/ready'
check '/consulta?asn=15169&incluir_dominios=false'
check '/consulta?nome=Google&limite_ases=2&incluir_dominios=false'
# Top domains intencionalmente fora do teste rápido: podem atingir timeout.

#!/usr/bin/env bash
# Diagnóstico do grafo real. Operações somente leitura, LIMIT pequeno.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

query() {
  printf '\n=== %s ===\n' "$1"
  docker compose exec -T iyp cypher-shell -a bolt://localhost:7687 "$2"
}

query 'Banco respondendo' 'RETURN 1 AS conectado;'
query 'Labels relevantes disponíveis' "CALL db.labels() YIELD label WHERE label IN ['AS','Name','Tag','Organization','Country','IXP','BGPPrefix','DomainName','Ranking'] RETURN label ORDER BY label;"
query 'AS15169 presente' 'MATCH (a:AS {asn:15169}) RETURN a.asn AS asn LIMIT 1;'
query 'Nomes e fontes do AS15169' 'MATCH (a:AS {asn:15169})-[r:NAME]-(n:Name) RETURN n.name AS nome, r.reference_name AS fonte LIMIT 5;'
query 'Tags do AS15169' 'MATCH (a:AS {asn:15169})-[r:CATEGORIZED]-(t:Tag) RETURN t.label AS tag, r.reference_name AS fonte LIMIT 5;'
query 'Siblings do AS15169' 'MATCH (a:AS {asn:15169})-[r:SIBLING_OF]-(b:AS) RETURN b.asn AS sibling, r.reference_name AS fonte LIMIT 5;'
query 'IXPs do AS15169' 'MATCH (a:AS {asn:15169})-[r:MEMBER_OF]->(ix:IXP) RETURN ix.name AS ixp, r.reference_name AS fonte LIMIT 5;'
query 'Prefixos BGP do AS15169' 'MATCH (a:AS {asn:15169})-[r:ORIGINATE]->(p:BGPPrefix) RETURN p.prefix AS prefixo, r.reference_name AS fonte LIMIT 5;'
query 'Vínculos COUNTRY para AS15169' 'MATCH (a:AS {asn:15169})-[r:COUNTRY]-(c:Country) RETURN c.country_code AS pais, r.reference_name AS fonte LIMIT 5;'
echo
printf 'Fim do diagnóstico. Resultados vazios indicam ausência de relações para o AS amostrado, NÃO ausência da relação em toda a base.\n'

#!/bin/sh
set -eu

case "${1:-all}" in
  all) variants="complete cinehub matchhub" ;;
  complete|cinehub|matchhub) variants="$1" ;;
  *) printf '%s\n' 'Uso: variants_up.sh [complete|cinehub|matchhub]' >&2; exit 1 ;;
esac

if [ ! -e .env ]; then
  cp -n .env.example .env
  printf '%s\n' 'Arquivo .env criado a partir de .env.example para uso local.'
fi
uv run --locked python scripts/products_local.py

# Limites por variante; não incluem VM nem build.
export DB_MEMORY_LIMIT=160m IDENTITY_MEMORY_LIMIT=256m API_MEMORY_LIMIT=128m GATEWAY_MEMORY_LIMIT=32m FRONTEND_MEMORY_LIMIT=32m
# Não utilizar credenciais de APIs externas neste modo.
export TMDB_API_TOKEN= IGDB_CLIENT_ID= IGDB_CLIENT_SECRET= FOOTBALL_DATA_API_TOKEN= MUSICBRAINZ_USER_AGENT= OMDB_API_KEY=

for variant in $variants; do
  case "$variant" in
    complete) FRONTEND_PORT=5174; GATEWAY_PORT=8180; IDENTITY_PORT=8101; CATALOG_PORT=8102; REVIEWS_PORT=8103; RECOMMENDATIONS_PORT=8104 ;;
    cinehub) FRONTEND_PORT=5175; GATEWAY_PORT=8280; IDENTITY_PORT=8201; CATALOG_PORT=8202; REVIEWS_PORT=8203; RECOMMENDATIONS_PORT=8204 ;;
    matchhub) FRONTEND_PORT=5176; GATEWAY_PORT=8380; IDENTITY_PORT=8301; CATALOG_PORT=8302; REVIEWS_PORT=8303; RECOMMENDATIONS_PORT=8304 ;;
  esac
  PRODUCT_DIR="./generated/variants/$variant"
  export FRONTEND_PORT GATEWAY_PORT IDENTITY_PORT CATALOG_PORT REVIEWS_PORT RECOMMENDATIONS_PORT PRODUCT_DIR
  printf '\nIniciando %s...\n' "$variant"
  docker compose -p "reviewhub-$variant" up --build --detach --wait --wait-timeout 180
  docker compose -p "reviewhub-$variant" run --rm --no-deps -T catalog python -m services.catalog.seed
done
printf '\n%s\n' 'Variantes disponíveis:'
for variant in $variants; do
  case "$variant" in
    complete) printf '%s\n' '  ReviewHub Complete: http://localhost:5174' '  Música (Complete):  http://localhost:5174/catalogo?domain=music_albums' '  APIs: http://localhost:8101/docs, http://localhost:8102/docs, http://localhost:8103/docs, http://localhost:8104/docs' ;;
    cinehub) printf '%s\n' '  CineHub:            http://localhost:5175' '  APIs: http://localhost:8201/docs, http://localhost:8202/docs, http://localhost:8203/docs, http://localhost:8204/docs' ;;
    matchhub) printf '%s\n' '  MatchHub:           http://localhost:5176' '  APIs: http://localhost:8301/docs, http://localhost:8302/docs, http://localhost:8303/docs, http://localhost:8304/docs' ;;
  esac
done

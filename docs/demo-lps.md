# Roteiro de demonstração — Linha de Produto de Software

## Preparação

Siga o [checklist](checklist-apresentacao.md). O backend deve ficar ao lado do frontend. Configure `.env` e gere o manifesto antes de iniciar os serviços.

1. Mostre o modelo, as dependências e a matriz em [arquitetura.md](arquitetura.md). Features obrigatórias incluem identidade, catálogo, reviews, notas e ao menos um domínio. `social_feed` exige `user_follows`; as features especializadas dependem dos respectivos domínios.
2. Execute `uv run reviewhub validate products/cinehub.yaml`, `uv run reviewhub validate products/matchhub.yaml` e `uv run reviewhub validate products/complete.yaml`.
3. Para erro explicativo, copie uma configuração para um arquivo temporário, adicione `social_feed` sem `user_follows` e execute `uv run reviewhub validate CAMINHO`. O comando deve falhar antes da implantação. O teste `test_invalid_feature_dependency` demonstra essa regra sem editar os YAMLs originais.
4. Derive CineHub com `uv run reviewhub derive products/cinehub.yaml`. Inicie a aplicação conforme o README e rode o seed. Mostre filmes e séries, comentários, spoilers e listas; o feed e partidas não estão disponíveis.
5. Derive MatchHub com `uv run reviewhub derive products/matchhub.yaml`, reinicie os serviços e rode o seed. Recarregue a página: o catálogo mostra partidas e placar, mas não filmes nem listas. O backend rejeita `GET /api/v1/contents?domain=movies` e endpoints de listas e feed para usuário autenticado.
6. Derive Complete com `uv run reviewhub derive products/complete.yaml`, reinicie e rode o seed. Mostre os cinco domínios, listas, curtidas, seguidores e feed com duas contas. A troca não apaga dados do volume.
7. Mostre os testes: `uv run pytest -q tests/test_framework.py`, `uv run python scripts/postgres_smoke.py` e os Playwright documentados no README. Os testes locais de navegador utilizam gateway de teste que encaminha HTTP aos serviços reais; não comprovam o proxy Nginx/Compose.

A derivação escreve `generated/product.json`; o arquivo é comum ao frontend e aos serviços e é determinístico. Não use a existência do manifesto como prova isolada: apresente também os testes de bloqueio e os comportamentos observados.

# Checklist para apresentação

- [ ] Ter Python 3.12+, uv, Node 20.19+, npm e Docker Desktop com Compose. No macOS, abra o Docker Desktop e aguarde o daemon; confirme com `docker version` e `docker compose version`.
- [ ] Manter `reviewhub-backend` e `reviewhub-frontend` lado a lado. No backend: `uv sync`, `cp .env.example .env` se ainda não existir, e definir `JWT_SECRET` para o ambiente de demonstração.
- [ ] Derivar o produto: `uv run reviewhub validate products/cinehub.yaml` e `uv run reviewhub derive products/cinehub.yaml`.
- [ ] Executar `docker compose config`, `docker compose up --build -d`, `docker compose ps` e `docker compose logs --tail=100` e confirmar todos os healthchecks. O Compose não foi executado no ambiente de desenvolvimento desta entrega.
- [ ] Popular conteúdo fictício: `docker compose exec catalog python -m services.catalog.seed`. Repetir o seed não duplica os exemplos.
- [ ] Abrir `http://localhost:5173`, os Swagger em `http://localhost:8001/docs`, `:8002/docs`, `:8003/docs` e conferir cadastro, catálogo e review.
- [ ] Confirmar persistência: cadastrar usuário e review, executar `docker compose restart`, aguardar healthchecks e conferir os mesmos dados. Não remova volumes para este teste.
- [ ] Rodar backend: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`. No frontend: `npm ci`, `npm run test`, `npm run lint`, `npm run build` e `npm audit`.
- [ ] Rodar navegador contra Compose: `npx playwright install chromium` no frontend e, com Complete derivado e seed disponível, `E2E_PRODUCT=complete npm run test:e2e`. O teste cria contas e dados reais no ambiente apontado; use um ambiente de testes isolado. Para as outras variantes, derive e rode o seed antes de usar `E2E_PRODUCT=cinehub` ou `E2E_PRODUCT=matchhub`.
- [ ] Alternativamente, com PostgreSQL local e `initdb`, `pg_ctl`, `psql` no PATH, execute no backend `uv run python scripts/e2e_local.py complete`, depois `cinehub` e `matchhub`. Esses comandos criam clusters temporários descartáveis e usam um proxy de teste para encaminhar chamadas aos serviços reais.
- [ ] Revisar os roteiros [Reuso](demo-reuso.md) e [LPS](demo-lps.md), e ter uma configuração inválida em arquivo temporário para demonstrar a mensagem de erro.

As credenciais e o Compose são de desenvolvimento. Os testes E2E no Compose alteram dados e não devem ser apontados para produção. A inicialização do banco ocorre apenas em volumes PostgreSQL novos. Bancos de versões sem histórico Alembic exigem backup e avaliação prévia; não apague volumes automaticamente.

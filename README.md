# ReviewHub Backend

ReviewHub é uma família de aplicações de avaliações para Reuso de Software e Linha de Produto de Software (LPS). Identity, Catalog e Reviews são processos FastAPI separados, cada um dono de seu banco PostgreSQL e suas migrations Alembic; Recommendations é um quarto serviço, sem banco, que calcula sugestões a partir do histórico do usuário. O núcleo `reviewhub_core` fornece contratos de domínio, políticas, descoberta de plugins e validação da configuração. [Arquitetura, modelo de features e evidências acadêmicas](docs/arquitetura.md).

## Iniciar uma aplicação

Mantenha `reviewhub-backend` e `reviewhub-frontend` lado a lado. Instale [mise](https://mise.jdx.dev/getting-started.html), Docker com Compose e inicie o mecanismo Docker (por exemplo, Colima). Na raiz do backend, escolha a aplicação que deseja iniciar:

```sh
mise run app:complete   # ReviewHub Complete: http://localhost:5174
mise run app:cinehub    # CineHub: http://localhost:5175
mise run app:matchhub   # MatchHub: http://localhost:5176
```

Cada comando prepara `.env` apenas se estiver ausente, gera a configuração local sem APIs externas, constrói as imagens, inicia a aplicação escolhida e popula seu catálogo. O endereço e os links das APIs são exibidos ao final. Música fica no Complete: http://localhost:5174/catalogo?domain=music_albums.

Para encerrar a aplicação escolhida sem apagar seus dados:

```sh
mise run app:complete:down
mise run app:cinehub:down
mise run app:matchhub:down
```

Esses comandos atuam somente na variante indicada: iniciar uma não encerra outras que já estejam rodando. Cada variante tem seu próprio banco persistente; contas, reviews e listas não são compartilhadas. O catálogo local contém dados reais e exemplos fictícios, sem áudio ou imagens. Veja [origem e licença dos dados](docs/dataset-local.md). As buscas por APIs externas ficam desativadas nesse modo. O primeiro build pode precisar de internet para baixar imagens e dependências.

Os limites por aplicação somam 736 MiB para os containers, incluindo 256 MiB para o serviço de identidade. São limites iniciais, não medições nem garantia de uso dentro de 2 GiB: VM, sistema e build consomem memória adicional. Use `docker stats` para acompanhar o uso; rodar mais de uma aplicação aumenta o consumo. O modo Compose anterior usa a porta 5173 e permanece independente.

## Desenvolvimento com mise

Instale o [mise](https://mise.jdx.dev/getting-started.html) e mantenha `reviewhub-backend` e `reviewhub-frontend` lado a lado. O arquivo `mise.toml` fixa Python 3.12.16 e uv 0.13.6. Na raiz do backend:

```sh
mise trust                # somente se o mise solicitar confiança no arquivo
mise install
mise run setup            # uv sync --locked; cria .env apenas se não existir
mise run lps:cinehub      # escolha também lps:matchhub ou lps:complete
mise run start            # serviços nativos; requer PostgreSQL local configurado
```

Inicie o frontend em outro terminal com `mise run start` na pasta `reviewhub-frontend` e abra `http://localhost:5173`. O gateway atende em `http://localhost:8080`; Swagger: identidade `http://localhost:8001/docs`, catálogo `http://localhost:8002/docs`, reviews `http://localhost:8003/docs`, recomendações `http://localhost:8004/docs`. O Compose usa `../reviewhub-frontend`. O seed é idempotente e contém exemplos fictícios. O setup não exige Docker nem credenciais externas.

```sh
mise run start            # serviços e gateway nativos, com recarregamento
mise run dev              # Compose em primeiro plano, com build
mise run docker:up        # Compose em segundo plano, com build
mise run docker:logs      # acompanha logs
mise run docker:down      # encerra sem remover volumes
mise run db:migrate       # aplica migrations nos três serviços em execução
mise run test
mise run lint
mise run format
mise run check            # lint, verificação de formato e testes
mise tasks ls
```

O modo nativo inicia Identity em `127.0.0.1:8001`, Catalog em `:8002`, Reviews em `:8003`, Recommendations em `:8004` e o gateway de desenvolvimento em `:8080`. Todos exibem logs no terminal e são encerrados com Ctrl+C. Os serviços aplicam migrations na inicialização; o comando não executa seed. O gateway reutiliza `scripts/e2e_gateway.py` e é destinado apenas ao desenvolvimento local.

Antes de iniciar, disponibilize PostgreSQL local com três bancos e credenciais separadas. Os padrões são os mesmos de `infra/init.sql`, no host `127.0.0.1:5432`: bancos `identity`, `catalog` e `reviews`, com usuários `identity_service`, `catalog_service` e `reviews_service`. Para provisionar uma instância **nova** de desenvolvimento, um administrador pode executar `psql -U SEU_ADMIN -d postgres -v ON_ERROR_STOP=1 -f infra/init.sql`; o script cria roles e bancos e não é idempotente. Em uma instância existente, configure os bancos e permissões apropriados sem sobrescrever dados.

Para usar outros bancos, informe `IDENTITY_DATABASE_URL`, `CATALOG_DATABASE_URL` e `REVIEWS_DATABASE_URL` no `.env` ou no ambiente, por exemplo `postgresql+psycopg://usuario:senha@127.0.0.1:5432/identity`. Valores exportados no shell têm prioridade sobre `.env`; use aspas para valores com espaços. Configure também `JWT_SECRET` (ao menos 32 caracteres). O manifesto vem de `generated/product.json`, ou do caminho em `PRODUCT_CONFIG`. Os serviços se comunicam pelas URLs locais padrão; `IDENTITY_URL`, `CATALOG_URL` e `REVIEWS_URL` permitem substituí-las quando necessário. Não versionar senhas reais.

O modo Docker requer Docker com Compose: `mise run docker:up` inicia PostgreSQL, três APIs, gateway e frontend React compilado servido por Nginx em http://localhost:5173. `mise run dev` executa o mesmo ambiente em primeiro plano. O navegador usa URLs relativas; o Nginx do frontend encaminha `/api/` e `/product.json` ao gateway em `http://gateway`. O modo nativo não depende de Docker.

Os limites de memória dos containers somam 1.536 MiB: PostgreSQL 384 MiB, cada API 320 MiB, gateway 64 MiB e frontend 128 MiB. Cada API usa um worker; PostgreSQL usa `shared_buffers=64MB` e até 60 conexões. São limites iniciais, não uma medição nem garantia de execução em 2 GiB: Docker/VM, sistema operacional, cache, swap e o build têm consumo adicional. O build pode exigir mais memória que a execução. Monitore com `docker stats` durante a carga representativa, e confira falhas por falta de memória com `docker inspect` e os logs. Em Docker Desktop, confira também o consumo e limite da VM. Não use esses valores como configuração de produção sem testes.

O `.env` fornece `JWT_SECRET`, `CORS_ORIGINS` e credenciais opcionais dos provedores; as URLs de banco e credenciais de desenvolvimento estão no Compose e em `infra/init.sql`. O volume `pgdata` preserva os dados entre reinícios e `docker:down` não o remove. Após derivar um produto, reinicie os serviços para carregar o manifesto. As portas 5173, 8080 e 8001–8004 devem estar disponíveis. Não exponha essa configuração de desenvolvimento à internet.

As tasks Docker e de banco requerem Docker e os serviços devidos disponíveis; `db:migrate` e `db:seed` operam nos containers já iniciados. As migrations também são aplicadas pelos serviços na inicialização. Não remova volumes para migrar. **Bancos criados pela versão anterior com `create_all` não possuem histórico Alembic:** faça backup e avalie cuidadosamente a equivalência do esquema antes de registrar uma linha de base. O script PostgreSQL do Compose provisiona bancos e usuários somente em volume novo.

Para testes E2E pelo frontend, consulte a seção de mise do README correspondente. Para testes com PostgreSQL local temporário sem Docker, veja abaixo.

## Provedores externos

A busca local funciona sem credenciais. Para habilitar busca e importação de obras reais, configure os provedores no `.env`; a seleção depende do produto da LPS. Veja [arquitetura, credenciais, limites e termos](docs/provedores.md). Conteúdos importados recebem IDs locais estáveis e podem ser avaliados ou adicionados às listas.

## Produtos

```sh
mise run lps:validate products/cinehub.yaml
mise run lps:derive products/cinehub.yaml
# Atalhos para os produtos incluídos:
mise run lps:cinehub
mise run lps:matchhub
mise run lps:complete
mise run docker:up
mise run db:seed
```

Com `OMDB_API_KEY` no `.env`, `mise run db:seed:omdb` adiciona cerca de 100 filmes reais com pôster e sinopse ao CineHub ou ao Complete. Veja [provedores](docs/provedores.md#catálogo-de-filmes-via-omdb).
Com `FOOTBALL_DATA_API_TOKEN`, `mise run db:seed:football` adiciona as partidas reais da Copa do Mundo 2026 e do Brasileirão ao MatchHub ou ao Complete. Veja [provedores](docs/provedores.md#partidas-via-football-dataorg).
Com `MUSICBRAINZ_USER_AGENT`, `mise run db:seed:music` adiciona cerca de 100 álbuns reais com capa e faixas ao Complete. Veja [provedores](docs/provedores.md#álbuns-via-musicbrainz).
Com `IGDB_CLIENT_ID` e `IGDB_CLIENT_SECRET`, `mise run db:seed:games` adiciona cerca de 100 games reais com capa ao Complete. Veja [provedores](docs/provedores.md#games-via-igdb).

O arquivo `generated/product.json` é determinístico. Os serviços o leem e o gateway o entrega à interface; ao trocar o produto, reinicie a aplicação e recarregue a página. A troca não remove dados. Uma configuração inválida é rejeitada pelo configurador e na inicialização dos serviços. Filmes não aparecem em MatchHub; o backend bloqueia operações para domínios e features desabilitados. O frontend só apresenta controles de features ativas.

## Testes e qualidade

```sh
mise run check
# Teste HTTP com PostgreSQL local temporário (initdb, pg_ctl e psql no PATH):
uv run python scripts/postgres_smoke.py
```

O teste PostgreSQL cria um cluster descartável, executa migrations, inicia três processos e testa usuários, reviews, interações e troca de produto. A maioria dos testes Pytest usa SQLite isolado; o teste acima usa PostgreSQL real. O Playwright também pode executar o fluxo completo com PostgreSQL e serviços reais sem Docker: instale dependências do frontend com `npm ci` e o navegador com `npx playwright install chromium`; em seguida rode `uv run python scripts/e2e_local.py complete` (ou `cinehub`, `matchhub`). O proxy local desse teste é separado do Nginx do Compose.

## Organização e contratos

- `reviewhub_core/`: contratos, estratégias, políticas, plugins e modelo de features.
- `products/`: configurações YAML dos produtos.
- `services/identity`, `services/catalog`, `services/reviews`: APIs, persistência e migrations por serviço.
- `tests/`, `scripts/postgres_smoke.py`: testes unitários e integração.
- `infra/`, `compose.yaml`: gateway e infraestrutura.

A API usa prefixo `/api/v1`. Identidade expõe `/auth/register`, `/auth/login`, `/users`, seguidores e contagens; catálogo expõe `/domains`, `/contents` e `/external`; reviews expõe `/reviews`, `/reviews/stats`, `/reviews/stats/batch`, comentários, curtidas e `/feed`. Consultas de reviews usam `GET /reviews?author_id=...&content_id=...`, com paginação. O feed exige JWT e consulta seguidores via HTTP ao serviço de identidade; criação de review consulta catálogo via HTTP. Chamadas entre serviços usam timeout de três segundos.

JWT HS256 tem expiração de duas horas e é validado localmente por cada serviço com o mesmo `JWT_SECRET`. Configure `CORS_ORIGINS` como lista de origens separadas por vírgula. O arquivo `.env.example` e as credenciais PostgreSQL em `infra/init.sql` são **apenas para desenvolvimento**. Cada serviço recebe credenciais de seu próprio banco. Cadastro de conteúdo exige autenticação; ainda não há papéis administrativos.

## Limitações

- O Docker Compose e o gateway Nginx não foram executados neste ambiente. O fluxo de navegador foi executado contra serviços e PostgreSQL reais por um proxy de teste.
- A política `domain_specific_rating`, opcional, está implementada para futebol; nenhuma configuração padrão a habilita. O plugin de futebol exige nota maior que zero quando selecionada. As demais seguem a política genérica de 0 a 5 em meios pontos.
- A tela de perfil e as listas de reviews exibem a primeira página; a média e a quantidade por conteúdo são agregadas no backend.
- Interface armazena JWT no `localStorage`, adequado somente ao escopo acadêmico; há risco de exposição por XSS. Não há revogação antecipada de tokens, recuperação de senha, rate limiting ou autorização administrativa.
- O endurecimento para produção e a execução do E2E na CI ainda estão pendentes.
- Os diretórios não foram inicializados como Git por restrição explícita da sessão. Se desejar, inicialize manualmente com `git init reviewhub-backend` e `git init reviewhub-frontend`, a partir da pasta que os contém.

Se uma página não carregar, confira o manifesto gerado, `.env`, logs e healthchecks do Compose. Ao trocar o produto, rode novamente o seed para incluir exemplos dos novos domínios.

Roteiros acadêmicos: [Reuso](docs/demo-reuso.md), [LPS](docs/demo-lps.md) e [checklist para apresentação](docs/checklist-apresentacao.md).

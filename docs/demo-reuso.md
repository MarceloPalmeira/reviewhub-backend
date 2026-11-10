# Roteiro de demonstração — Reuso de Software

## Preparação

Siga o [checklist](checklist-apresentacao.md). Execute `uv run pytest -q tests/test_framework.py` no backend e registre a saída. Os exemplos são fictícios.

1. Apresente `reviewhub_core/plugins.py`: `DomainPlugin`, `ContentSchema`, `RatingStrategy`, `ReviewPolicy` e `FeatureRegistry`. O framework representa os contratos e políticas compartilhados; as aplicações são os serviços e produtos que os utilizam.
2. Compare `reviewhub_core/domains/movies.py` e `football_matches.py`. Ambos usam o mesmo controller de catálogo e o mesmo fluxo de review em `services/reviews/main.py`; seus schemas e capacidades diferem. Explique Strategy (notas), Registry (plugins) e injeção de dependência nos endpoints.
3. Mostre `test_plugins_share_review_policy_and_validate_metadata` e `test_feature_metadata_and_specialized_rating`; execute os testes para evidenciar validação e reuso. A variante opcional de futebol exige nota maior que zero quando `domain_specific_rating` está habilitada.
4. Mostre o exemplo de pacote e entry point em [arquitetura.md](arquitetura.md). Um plugin externo fornece schema e `DomainPlugin`, é instalado nos ambientes dos serviços e é selecionado por domínio no YAML. Novas features ainda exigem alterar o validador; o seed não cria dados para domínios externos.
5. Demonstre os contratos OpenAPI nos serviços e explique a consulta HTTP de reviews ao catálogo, sem compartilhar tabelas. O diagrama de componentes, o de classes e a sequência estão em [arquitetura.md](arquitetura.md).

Não confunda o exemplo de extensão com um pacote externo já distribuído: o teste automatizado simula o entry point. Valide instalação real do pacote externo antes de apresentá-la como experiência executada.

"""Popula o catálogo com filmes reais obtidos pela OMDb (dados do IMDb).

O repositório guarda apenas identificadores IMDb; título, sinopse, pôster e
créditos são buscados na OMDb a cada execução. Requer `OMDB_API_KEY` e rede.
Idempotente: filmes já presentes (mesmo identificador IMDb) são mantidos.

Uso: python -m services.catalog.seed_omdb
"""

import os
import sys

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from reviewhub_core.plugins import FeatureRegistry
from services.catalog.main import Content, Session, engine
from services.catalog.providers.base import ProviderError
from services.catalog.providers.omdb import OMDbProvider
from services.common import product
from services.migrations import migrate

MOVIE_IDS = [
    "tt0033467",  # Citizen Kane (1941)
    "tt0034583",  # Casablanca (1943)
    "tt0045152",  # Singin' in the Rain (1952)
    "tt0047478",  # Seven Samurai (1956)
    "tt0050083",  # 12 Angry Men (1957)
    "tt0052357",  # Vertigo (1958)
    "tt0054215",  # Psycho (1960)
    "tt0062622",  # 2001: A Space Odyssey (1968)
    "tt0068646",  # The Godfather (1972)
    "tt0071562",  # The Godfather Part II (1974)
    "tt0073195",  # Jaws (1975)
    "tt0073486",  # One Flew Over the Cuckoo's Nest (1975)
    "tt0075314",  # Taxi Driver (1976)
    "tt0076759",  # Star Wars: Episode IV - A New Hope (1977)
    "tt0078748",  # Alien (1979)
    "tt0078788",  # Apocalypse Now (1979)
    "tt0080684",  # Star Wars: Episode V - The Empire Strikes Back (1980)
    "tt0081505",  # The Shining (1980)
    "tt0082971",  # Raiders of the Lost Ark (1981)
    "tt0083658",  # Blade Runner (1982)
    "tt0083866",  # E.T. the Extra-Terrestrial (1982)
    "tt0088763",  # Back to the Future (1985)
    "tt0090605",  # Aliens (1986)
    "tt0099685",  # GoodFellas (1990)
    "tt0096283",  # My Neighbor Totoro (1990)
    "tt0103064",  # Terminator 2: Judgment Day (1991)
    "tt0102926",  # The Silence of the Lambs (1991)
    "tt0107290",  # Jurassic Park (1993)
    "tt0109830",  # Forrest Gump (1994)
    "tt0110912",  # Pulp Fiction (1994)
    "tt0108052",  # Schindler's List (1994)
    "tt0110357",  # The Lion King (1994)
    "tt0111161",  # The Shawshank Redemption (1994)
    "tt0114369",  # Seven (1995)
    "tt0114709",  # Toy Story (1995)
    "tt0119698",  # Princess Mononoke (1997)
    "tt0120338",  # Titanic (1997)
    "tt0140888",  # Central Station (1998)
    "tt0120815",  # Saving Private Ryan (1998)
    "tt0137523",  # Fight Club (1999)
    "tt0133093",  # The Matrix (1999)
    "tt0271383",  # A Dog's Will (2000)
    "tt0172495",  # Gladiator (2000)
    "tt0241527",  # Harry Potter and the Sorcerer's Stone (2001)
    "tt0209144",  # Memento (2001)
    "tt0120737",  # The Lord of the Rings: The Fellowship of the Ring (2001)
    "tt0211915",  # Amélie (2002)
    "tt0167261",  # The Lord of the Rings: The Two Towers (2002)
    "tt0266543",  # Finding Nemo (2003)
    "tt0266697",  # Kill Bill: Vol. 1 (2003)
    "tt0245429",  # Spirited Away (2003)
    "tt0167260",  # The Lord of the Rings: The Return of the King (2003)
    "tt0317248",  # City of God (2004)
    "tt0338013",  # Eternal Sunshine of the Spotless Mind (2004)
    "tt0407887",  # The Departed (2006)
    "tt0861739",  # Elite Squad (2007)
    "tt0477348",  # No Country for Old Men (2007)
    "tt0457430",  # Pan's Labyrinth (2007)
    "tt0468569",  # The Dark Knight (2008)
    "tt0469494",  # There Will Be Blood (2008)
    "tt0910970",  # WALL·E (2008)
    "tt0361748",  # Inglourious Basterds (2009)
    "tt1049413",  # Up (2009)
    "tt0947798",  # Black Swan (2010)
    "tt1555149",  # Elite Squad 2: The Enemy Within (2010)
    "tt1375666",  # Inception (2010)
    "tt1285016",  # The Social Network (2010)
    "tt1853728",  # Django Unchained (2012)
    "tt0993846",  # The Wolf of Wall Street (2013)
    "tt1798709",  # Her (2014)
    "tt0816692",  # Interstellar (2014)
    "tt2278388",  # The Grand Budapest Hotel (2014)
    "tt2582802",  # Whiplash (2014)
    "tt2096673",  # Inside Out (2015)
    "tt1392190",  # Mad Max: Fury Road (2015)
    "tt3742378",  # The Second Mother (2015)
    "tt5221584",  # Aquarius (2016)
    "tt2543164",  # Arrival (2016)
    "tt3783958",  # La La Land (2016)
    "tt4975722",  # Moonlight (2016)
    "tt1856101",  # Blade Runner 2049 (2017)
    "tt2380307",  # Coco (2017)
    "tt5052448",  # Get Out (2017)
    "tt4154756",  # Avengers: Infinity War (2018)
    "tt5726616",  # Call Me by Your Name (2018)
    "tt6155172",  # Roma (2018)
    "tt4633694",  # Spider-Man: Into the Spider-Verse (2018)
    "tt7286456",  # Joker (2019)
    "tt8946378",  # Knives Out (2019)
    "tt7131622",  # Once Upon a Time in... Hollywood (2019)
    "tt6751668",  # Parasite (2019)
    "tt8579674",  # 1917 (2020)
    "tt2762506",  # Bacurau (2020)
    "tt1160419",  # Dune (2021)
    "tt6710474",  # Everything Everywhere All at Once (2022)
    "tt1745960",  # Top Gun: Maverick (2022)
    "tt1517268",  # Barbie (2023)
    "tt15398776",  # Oppenheimer (2023)
    "tt13238346",  # Past Lives (2023)
    "tt14230458",  # Poor Things (2023)
    "tt17009710",  # Anatomy of a Fall (2024)
    "tt15239678",  # Dune: Part Two (2024)
    "tt14961016",  # I'm Still Here (2025)
]


def main(provider=None, ids=MOVIE_IDS):
    config = product()
    if "movies" not in config.domains:
        print("O produto não habilita filmes; nada a fazer.")
        return 0
    if provider is None:
        key = os.getenv("OMDB_API_KEY")
        if not key:
            print("Configure OMDB_API_KEY para usar este seed.", file=sys.stderr)
            return 1
        provider = OMDbProvider(key)
    plugin = FeatureRegistry(config.domains).get("movies")
    migrate("catalog", engine)
    added = kept = failed = 0
    with Session() as db:
        existing = set(
            db.scalars(
                select(Content.external_id).where(
                    Content.external_provider == "omdb", Content.domain == "movies"
                )
            )
        )
        for imdb_id in ids:
            if imdb_id in existing:
                kept += 1
                continue
            try:
                external = provider.get_details(imdb_id, "movies")
                metadata = plugin.schema.model_validate(
                    plugin.visible_metadata(external.metadata, config.features)
                ).model_dump(exclude_none=True, mode="json")
            except (ProviderError, ValidationError, ValueError) as exc:
                failed += 1
                print(f"{imdb_id}: {exc}", file=sys.stderr)
                if isinstance(exc, ProviderError) and exc.status in (429, 503):
                    break  # limite diário ou chave inválida: não insistir
                continue
            db.add(
                Content(
                    id=f"omdb-movies-{imdb_id}",
                    domain="movies",
                    title=external.title,
                    description=external.description,
                    metadata_json=metadata,
                    cover_url=external.cover_url,
                    release_date=external.release_date,
                    genres=external.genres,
                    external_provider="omdb",
                    external_id=imdb_id,
                )
            )
            existing.add(imdb_id)
            added += 1
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            print(
                "Outra execução gravou os mesmos itens; rode o comando novamente.",
                file=sys.stderr,
            )
            return 3
    print(f"Filmes OMDb: {added} adicionados, {kept} já existentes, {failed} falhas.")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

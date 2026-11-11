"""Popula o catálogo com álbuns reais do MusicBrainz.

O repositório guarda apenas os identificadores de release group do MusicBrainz;
título, artista, gêneros, data e faixas são buscados a cada execução, e as capas
vêm do Cover Art Archive. Requer `MUSICBRAINZ_USER_AGENT` com contato (URL ou
e-mail) e rede. São duas requisições por álbum, espaçadas em 1,1 s, conforme o
limite do MusicBrainz: ao menos 4 minutos para a lista completa, podendo passar
de uma hora quando o serviço limita o ritmo. Idempotente e grava o progresso.

Uso: python -m services.catalog.seed_music
"""

import sys
import time

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from reviewhub_core.plugins import FeatureRegistry
from services.catalog.main import Content, Session, engine
from services.catalog.providers.base import ProviderError
from services.catalog.providers.registry import configured_provider
from services.common import product
from services.migrations import migrate

ALBUM_IDS = [
    "9e4072b4-11c3-3fe6-be4f-4a607bbb94f9",  # João Gilberto — Chega de saudade (1959)
    "8e8a594f-2175-38c7-a871-abb68ec363e7",  # Miles Davis — Kind of Blue (1959)
    "37b80fea-0129-3546-9ffe-00a719ee9e61",  # Nina Simone — I Put a Spell on You (1965)
    "77cf47ba-58cd-3f3d-a5f9-79bf89860421",  # John Coltrane — A Love Supreme (1965)
    "fb48b1dc-412f-36aa-8820-1023c08c46c6",  # Bob Dylan — Highway 61 Revisited (1965)
    "fdd96703-7b21-365e-bdea-38029fbeb84e",  # The Beach Boys — Pet Sounds (1966)
    "72d15666-99a7-321e-b1f3-a3f8c09dff9f",  # The Beatles — Revolver (1966)
    "935fccc4-064a-339c-ba4c-b0acee6ff5eb",  # Antônio Carlos Jobim — Wave (1967)
    "8ebffd15-06c3-3b88-a761-ec18c5513287",  # The Doors — The Doors (1967)
    "5cbd9d7b-597a-3c5e-bfd1-c2b364215560",  # The Velvet Underground & Nico — The Velvet Underground & Nico (1967)
    "7d8f07a7-4c64-3afb-8daf-8f1d4df89a78",  # Aretha Franklin — I Never Loved a Man the Way I Love You (1967)
    "da40e720-2097-3730-8a7f-0c2ddbff4a96",  # The Jimi Hendrix Experience — Are You Experienced (1967)
    "9f7a4c28-8fa2-3113-929c-c47a9f7982c3",  # The Beatles — Sgt. Pepper’s Lonely Hearts Club Band (1967)
    "f3578417-4c90-3891-a2cf-d1eab06cc084",  # Os Mutantes — Os Mutantes (1968)
    "9162580e-5df4-32de-80cc-f45a8d8a9b1d",  # The Beatles — Abbey Road (1969)
    "5da13507-7e60-3dec-b2e7-0e75dba03997",  # Chico Buarque — Construção (1971)
    "6e4f39e6-3403-39d7-81c6-8e61a990d509",  # Carole King — Tapestry (1971)
    "c1fa4d2c-ec62-37d5-b01d-6df7f8fd2c90",  # Marvin Gaye — What’s Going On (1971)
    "42d725fb-a8b7-388c-8866-3b02789af326",  # Joni Mitchell — Blue (1971)
    "2e61da88-39e9-3473-81d2-c964cb394952",  # Led Zeppelin — [Led Zeppelin IV] (1971)
    "c1d7370f-5aee-3042-ab20-ec15a0056c11",  # Gal Costa — -Fa-Tal- Gal a Todo Vapor (1971)
    "65790705-6d7b-3596-a427-fe5b8ab6481d",  # Novos Baianos — Acabou chorare (1972)
    "b29e94e7-0b0b-3a66-ab06-e02f8fa5054f",  # Milton Nascimento & Lô Borges — Clube da Esquina (1972)
    "fbd4a178-0c4a-3979-b626-8f2f3e3e335d",  # Caetano Veloso — Transa (1972)
    "4838a3c9-fd2b-30a5-83eb-e32545b5d7fc",  # The Rolling Stones — Exile on Main St. (1972)
    "6c9ae3dd-32ad-472c-96be-69d0a3536261",  # David Bowie — The Rise and Fall of Ziggy Stardust and the Spiders From Mars (1972)
    "917bcbb3-77c2-3e0c-9bba-03bde7e3ef50",  # Secos & Molhados — Secos & Molhados (1973)
    "f5093c06-23e3-404f-aeaa-40f72885ee3a",  # Pink Floyd — The Dark Side of the Moon (1973)
    "a29259f6-8623-34b8-b7d0-fa6461f31f6b",  # Jorge Ben — A Tábua de Esmeralda (1974)
    "4a58c393-a455-3aa9-8bc1-6641f9873dd9",  # Cartola — Cartola (1974)
    "f9520003-6075-310e-b650-bbaa8aaeab4d",  # Elis Regina & Tom Jobim — Elis & Tom (1974)
    "2e869a98-4a0d-39f5-8104-107802751379",  # Gilberto Gil — Refazenda (1975)
    "9c1b8072-eb1d-33d2-af8c-984d46e40902",  # Bob Dylan — Blood on the Tracks (1975)
    "3a99996a-dc01-43b3-b00c-5b1765ff8a9c",  # Tim Maia — Racional (Vol 1) (1975)
    "39b22944-7503-3937-8bba-09b17281cc6a",  # Bruce Springsteen — Born to Run (1975)
    "1a272023-10d3-38ee-bab3-317b55fcc21d",  # Pink Floyd — Wish You Were Here (1975)
    "6b47c9a0-b9e1-3df9-a5e8-50a6ce0dbdbd",  # Queen — A Night at the Opera (1975)
    "7de1e321-4a53-3feb-b83e-f1dab88bf952",  # Ramones — Ramones (1976)
    "ea88b09b-fd34-33cf-a3e5-25a3a2fb4c6f",  # Stevie Wonder — Songs in the Key of Life (1976)
    "416bb5e5-c7d1-3977-8fd7-7c9daf6c2be6",  # Fleetwood Mac — Rumours (1977)
    "e959a4b3-6306-3c45-9df6-e7241dae9ea3",  # Sex Pistols — Never Mind the Bollocks Here’s the Sex Pistols (1977)
    "42352def-1aab-3000-b548-895ebd869cb6",  # Joy Division — Unknown Pleasures (1979)
    "8d73e45e-7ca1-3cb4-ae28-6da76196c17c",  # The Clash — London Calling (1979)
    "d3bc1a64-7561-3787-b680-0003aa50f8f1",  # AC/DC — Back in Black (1980)
    "f6b1b900-6108-32f0-abbd-2855af9151eb",  # Talking Heads — Remain in Light (1980)
    "f32fab67-77dd-3937-addc-9062e28e4c37",  # Michael Jackson — Thriller (1982)
    "b93a7c47-a6d4-33f2-9034-53fdd991f4ba",  # Prince and The Revolution — Purple Rain (1984)
    "3d00fb45-f8ab-3436-a8e1-b4bfc4d66913",  # Metallica — Master of Puppets (1986)
    "d8dde278-482c-3cc8-a530-fea70476f3a5",  # The Smiths — The Queen Is Dead (1986)
    "51d5ae33-82c1-3d3c-8e25-c88a2cf2c208",  # Legião Urbana — Dois (1986)
    "6f3e9fa6-be7a-3de8-a2b2-2072ece8a54d",  # U2 — The Joshua Tree (1987)
    "a0b94d0a-210b-4b15-bd1d-93be2196c14a",  # Guns N' Roses — Appetite for Destruction (1987)
    "1f75a8df-176c-3d23-8f1f-b0c8935682ec",  # Madonna — Like a Prayer (1989)
    "cea5d18a-1924-3cda-bebc-38933834b25d",  # Pearl Jam — Ten (1991)
    "1b022e01-4da6-387b-8658-8678046e4cef",  # Nirvana — Nevermind (1991)
    "ad444843-7160-33d7-b0c9-fc99f2c14a99",  # Dr. Dre — The Chronic (1992)
    "b09ea0ac-051f-3d7d-b54b-432d1ad5cde6",  # Chico Science & Nação Zumbi — Da lama ao caos (1994)
    "10ee896f-e0ed-3d92-9ec9-095785d6fdef",  # Marisa Monte — Verde anil amarelo cor de rosa e carvão (1994)
    "28298e2c-4d70-3eed-a0f5-a3280c662b3d",  # Nas — Illmatic (1994)
    "67461c8e-d864-3910-9bf4-39e44357aac9",  # Blur — Parklife (1994)
    "48140466-cff6-3222-bd55-63c27e43190d",  # Portishead — Dummy (1994)
    "5afcfeac-118a-35e6-af0d-35ec9003354d",  # The Notorious B.I.G. — Ready to Die (1994)
    "cc7e6348-cc55-31fa-aeb2-748a46a81cb3",  # Oasis — (What’s the Story) Morning Glory? (1995)
    "cf4383c2-30e2-38bd-be61-83bc32fe5f2a",  # Racionais MC’s — Sobrevivendo no inferno (1997)
    "b1392450-e666-3926-a536-22c65f834433",  # Radiohead — OK Computer (1997)
    "810272e0-aef1-3d85-b2d3-e512e87fc38c",  # Björk — Homogenic (1997)
    "6f9f6899-c0d3-311d-ae87-a10ae6bc53a9",  # Massive Attack — Mezzanine (1998)
    "8691d12c-abd8-385c-b1eb-d841190124f7",  # Lauryn Hill — The Miseducation of Lauryn Hill (1998)
    "e75c0549-ad55-39e3-8025-c72c5d4a3c5d",  # Radiohead — Kid A (2000)
    "00d2cd53-21c9-3738-b683-56847b7b0040",  # OutKast — Stankonia (2000)
    "efea26d1-a016-30f6-b8e2-bc8c02336b0a",  # The Strokes — Is This It (2001)
    "48117b90-a16e-34ca-a514-19c702df1158",  # Daft Punk — Discovery (2001)
    "11ae8c9c-27c1-3308-9761-edb87c8f54ea",  # Jay‐Z — The Blueprint (2001)
    "48aa308a-0e8d-3e0f-8055-b7e98966856f",  # Los Hermanos — Ventura (2003)
    "d85b9684-4277-3565-b89b-115c8b4b7fd3",  # The White Stripes — Elephant (2003)
    "05affa96-5959-32da-8d75-1c9eb985ca59",  # Arcade Fire — Funeral (2004)
    "6eac2e57-ee50-36f8-b0c4-c4c847a2c098",  # Amy Winehouse — Back to Black (2006)
    "5cbcdd9f-4b7d-3b3c-b9f2-6b0e75971157",  # LCD Soundsystem — Sound of Silver (2007)
    "5d6e21e1-deb5-428e-bb42-c2a567f3619b",  # Kanye West — My Beautiful Dark Twisted Fantasy (2010)
    "e4174758-d333-4a8e-a31f-dd0edd51518e",  # Adele — 21 (2011)
    "f8f4167d-897c-4b25-a171-638374d1dfa4",  # Frank Ocean — channel ORANGE (2012)
    "499c19c8-0dab-4824-884b-6191d145e95b",  # Kendrick Lamar — good kid, m.A.A.d city (2012)
    "a348ba2f-f8b3-4686-b928-e63d8d94d543",  # Arctic Monkeys — AM (2013)
    "aa997ea0-2936-40bd-884d-3af8a0e064dc",  # Daft Punk — Random Access Memories (2013)
    "4d9ec1c2-58ec-48a4-aa0a-916718adead0",  # Taylor Swift — 1989 (2014)
    "d9103c72-3807-4378-9ce7-b6f3e8fdd547",  # Kendrick Lamar — To Pimp a Butterfly (2015)
    "08aa7a6c-3e43-4459-87b2-e47faf3a088a",  # Tame Impala — Currents (2015)
    "c1f22e07-7bdf-4a4f-8b50-7747c1091ef6",  # Beyoncé — Lemonade (2016)
    "0da340a0-6ad7-4fc2-a272-6f94393a7831",  # Frank Ocean — Blonde (2016)
    "bb525db3-81e4-4c05-b529-23fa05f35c12",  # ROSALÍA — EL MAL QUERER (2018)
    "4ae027fd-4ebb-4c20-b948-9c1a834653b9",  # BaianaSystem — O Futuro Não Demora (2019)
    "72375978-a9a1-4254-b957-85565c716b7e",  # Billie Eilish — WHEN WE ALL FALL ASLEEP, WHERE DO WE GO? (2019)
    "24fd0887-9e83-42e3-b27e-e7f89ead4c03",  # Lana Del Rey — Norman Fucking Rockwell! (2019)
    "1ce12884-40b1-4691-b16e-bef85df4e2f0",  # Emicida — AmarElo (2019)
    "882db6d8-e28b-46ba-8a30-277e86fbddf7",  # Fiona Apple — Fetch the Bolt Cutters (2020)
    "f1d08326-c23b-4b43-be3b-20b33ab10bf6",  # Taylor Swift — folklore (2020)
    "2ae2e504-7116-4b4f-b632-9748bb18ccd2",  # Olivia Rodrigo — SOUR (2021)
    "e992b449-141b-4aea-b07b-9b2a478a8570",  # Bad Bunny — Un verano sin ti (2022)
    "1646286a-d0ad-4288-bfab-34b0fb7b22c1",  # SZA — SOS (2022)
    "ee37e6bf-74e1-480c-b086-7a35d30ad8fd",  # Anitta — Funk Generation (2024)
    "e0fdb431-0109-420d-8a37-f99eaeb4d671",  # Charli xcx — BRAT (2024)
    "c8bea388-c195-4177-bf9b-7469f6e695a1",  # Sabrina Carpenter — Short n’ Sweet (2024)
]


def fetch(provider, mbid, attempts=3, wait=3.0):
    # O MusicBrainz responde 503 quando o ritmo de requisições é excedido.
    for attempt in range(attempts):
        try:
            return provider.get_details(mbid, "music_albums")
        except ProviderError as exc:
            if exc.status != 503 or attempt == attempts - 1:
                raise
            time.sleep(wait * (attempt + 1))


def main(provider=None, ids=ALBUM_IDS, wait=3.0):
    config = product()
    domain = "music_albums"
    if domain not in config.domains:
        print("O produto não habilita álbuns; nada a fazer.")
        return 0
    if provider is None:
        provider = configured_provider("musicbrainz")
        if provider is None:
            print(
                "Configure MUSICBRAINZ_USER_AGENT com URL ou e-mail de contato.",
                file=sys.stderr,
            )
            return 1
    plugin = FeatureRegistry(config.domains).get(domain)
    migrate("catalog", engine)
    added = kept = failed = 0
    with Session() as db:
        existing = set(
            db.scalars(
                select(Content.external_id).where(
                    Content.external_provider == "musicbrainz",
                    Content.domain == domain,
                )
            )
        )
        for mbid in ids:
            if mbid in existing:
                kept += 1
                continue
            try:
                album = fetch(provider, mbid, wait=wait)
                metadata = plugin.schema.model_validate(
                    plugin.visible_metadata(album.metadata, config.features)
                ).model_dump(exclude_none=True, mode="json")
            except (ProviderError, ValidationError, ValueError) as exc:
                failed += 1
                print(f"{mbid}: {exc}", file=sys.stderr)
                continue
            db.add(
                Content(
                    id=f"musicbrainz-{mbid}",
                    domain=domain,
                    title=album.title,
                    description=album.description,
                    metadata_json=metadata,
                    cover_url=album.cover_url,
                    release_date=album.release_date,
                    genres=album.genres,
                    external_provider="musicbrainz",
                    external_id=mbid,
                )
            )
            existing.add(mbid)
            try:
                db.commit()  # preserva o progresso de uma execução longa
                added += 1
            except IntegrityError:
                db.rollback()  # outra execução gravou o mesmo álbum
                kept += 1
    print(f"Álbuns: {added} adicionados, {kept} já existentes, {failed} falhas.")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

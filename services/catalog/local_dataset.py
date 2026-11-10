"""Seleção local de dados factuais; origem e licença em docs/dataset-local.md."""

LOCAL_CONTENT = {
    "movies": [
        (
            "intolerance-1916",
            "Intolerance",
            {"director": "D. W. Griffith", "duration_minutes": 163, "year": 1916},
        ),
        (
            "caligari-1920",
            "The Cabinet of Dr. Caligari",
            {"director": "Robert Wiene", "duration_minutes": 76, "year": 1920},
        ),
        (
            "the-kid-1921",
            "The Kid",
            {"director": "Charlie Chaplin", "duration_minutes": 68, "year": 1921},
        ),
        (
            "nosferatu-1922",
            "Nosferatu",
            {"director": "F. W. Murnau", "duration_minutes": 94, "year": 1922},
        ),
        (
            "gold-rush-1925",
            "The Gold Rush",
            {"director": "Charlie Chaplin", "duration_minutes": 95, "year": 1925},
        ),
    ],
    "series": [
        (
            "i-love-lucy",
            "I Love Lucy",
            {"seasons": 6, "episodes": 180, "status": "concluída"},
        ),
        (
            "gunsmoke",
            "Gunsmoke",
            {"seasons": 20, "episodes": 635, "status": "concluída"},
        ),
        (
            "honeymooners",
            "The Honeymooners",
            {"seasons": 1, "episodes": 39, "status": "concluída"},
        ),
        ("bonanza", "Bonanza", {"seasons": 14, "episodes": 431, "status": "concluída"}),
        (
            "flintstones",
            "The Flintstones",
            {"seasons": 6, "episodes": 166, "status": "concluída"},
        ),
    ],
    "video_games": [
        (
            "computer-space",
            "Computer Space",
            {
                "developer": "Nutting Associates",
                "genre": "Shooter; Simulation",
                "year": 1971,
            },
        ),
        (
            "colossal-cave",
            "Colossal Cave Adventure",
            {"developer": "Don Woods", "genre": "Adventure", "year": 1976},
        ),
        (
            "breakout",
            "Breakout",
            {"developer": "Atari, Inc.", "genre": "Action; Puzzle", "year": 1976},
        ),
        (
            "space-invaders",
            "Space Invaders",
            {"developer": "Taito", "genre": "Shooter", "year": 1978},
        ),
        ("pac-man", "Pac-Man", {"developer": "Namco", "genre": "Puzzle", "year": 1980}),
    ],
    "football_matches": [
        (
            "argentina-saudi-2022",
            "Argentina × Arábia Saudita",
            {
                "home_team": "Argentina",
                "away_team": "Arábia Saudita",
                "home_score": 1,
                "away_score": 2,
                "competition": "Copa do Mundo 2022",
                "match_date": "2022-11-22",
            },
        ),
        (
            "argentina-mexico-2022",
            "Argentina × México",
            {
                "home_team": "Argentina",
                "away_team": "México",
                "home_score": 2,
                "away_score": 0,
                "competition": "Copa do Mundo 2022",
                "match_date": "2022-11-26",
            },
        ),
        (
            "argentina-poland-2022",
            "Argentina × Polônia",
            {
                "home_team": "Argentina",
                "away_team": "Polônia",
                "home_score": 2,
                "away_score": 0,
                "competition": "Copa do Mundo 2022",
                "match_date": "2022-11-30",
            },
        ),
        (
            "argentina-australia-2022",
            "Argentina × Austrália",
            {
                "home_team": "Argentina",
                "away_team": "Austrália",
                "home_score": 2,
                "away_score": 1,
                "competition": "Copa do Mundo 2022",
                "match_date": "2022-12-03",
            },
        ),
        (
            "argentina-croatia-2022",
            "Argentina × Croácia",
            {
                "home_team": "Argentina",
                "away_team": "Croácia",
                "home_score": 3,
                "away_score": 0,
                "competition": "Copa do Mundo 2022",
                "match_date": "2022-12-13",
            },
        ),
    ],
    "music_albums": [
        (
            "american-folk",
            "Anthology of American Folk Music",
            {"artist": "Various", "genre": "Blues; Country; Folk", "year": 1952},
        ),
        (
            "wee-small-hours",
            "In the Wee Small Hours",
            {"artist": "Frank Sinatra", "genre": "Jazz", "year": 1955},
        ),
        (
            "elvis-presley",
            "Elvis Presley",
            {"artist": "Elvis Presley", "genre": "Rock", "year": 1956},
        ),
        (
            "swingin-lovers",
            "Songs for Swingin' Lovers!",
            {"artist": "Frank Sinatra", "genre": "Pop; Jazz", "year": 1956},
        ),
        (
            "blue-train",
            "Blue Train",
            {"artist": "John Coltrane", "genre": "Jazz", "year": 1958},
        ),
    ],
}

# Static playlist definitions
# Each playlist maps to a list of track keys from the CSV

PLAYLISTS: dict[str, list[str]] = {
    # Example playlists - replace with your actual track keys
    # "test": [
    #     "HAUNTING_TAVERN_REMST_FULLMIX",
    #     "MYSTIC_FOREST_AMBIENCE",
    #     "EPIC_BATTLE_THEME",
    # ],
    "city_chill": [
        "EMBERS",
        "DIMITRI_THE_RUSSION_FULLMIX",
        "251230TATOMJULJAD",
        "GRILL_THIS_AMB",
        "GRILL_THIS_FULLMIX",
        "SLOW_COOKING_AMB",
        "SLOW_COOKING_CUTDOWN",
        "SLOW_COOKING_FULLMIX",
        "LOST_WORLD",
        "UNSEEN",
    ],
    # Add more playlists here:
    # "tavern_ambience": ["TRACK_KEY_1", "TRACK_KEY_2", ...],
    # "combat_epic": ["BATTLE_KEY_1", "BATTLE_KEY_2", ...],

}


def get_playlist(name: str) -> list[str] | None:
    """Get track keys for a playlist."""
    return PLAYLISTS.get(name)


def get_all_playlists() -> list[str]:
    """Get all playlist names."""
    return list(PLAYLISTS.keys())

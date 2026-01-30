# Static playlist definitions
# Each playlist maps to a list of track keys from the CSV

PLAYLISTS: dict[str, list[str]] = {
    "City Chill Test": [
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
    "Big City Combat": [
        "BREAKIN",
        "BYTE_ME",
        "NOOBSLAYER92",
        "BULLETPROOF",
        "BREAKIN",
        "PLEASE_RESET_YOUR_PASSWORD",
        "CHASING_GHOSTS",
        "DEMONROBOTODLER",
        "DISTOPIA",
        "FIGHT_TOWN",
        "SLOW_COOKING_ACTION",
        "SLOW_COOKING_CUTDOWN",
        "IMPENDING_DOOM_FULLMIX",
        "BATTLE_OF_THE_BOOKCLUB_FULLMIX",
        "MADMANATEE_FULLMIX.MP3",
        "MADMANATEE_STING",
        "RESOLUTE",
        "SUPER_FUTURE_CAR_CHASE_FULLMIX",
        "SUPER_FUTURE_CAR_CHASE_CUTDOWN1",
        "SUPER_FUTURE_CAR_CHASE_CUTDOWN2",
        "SUPER_FUTURE_CAR_CHASE_CUTDOWN3",
        "SYSTEM_OVERLOAD",
        "THE_WITCH_AND_THE_DRAGON",
        "INTERSPIRATION",
        "COOLCRESS",
        "CONFRONTATION",
        "CASTLE_CRIME",
    ],
    "Big City Tensions": [
        "BLACKHATS",
        "CODE_BREAKERS",
        "CYBER_CRIMINAL",
        "BULLETPROOF",
        "IN_THE_CODE",
        "GRILL_THIS_FULLMIX",
        "LIKE_YOURE_BEING_WATCHED",
        "CREEPILY",
        "DARKNESS",
        "IMPENDING_DOOM_FULLMIX",
        "AND_DENIAL",
        "SUNKEN_JAR",
        "SACRED_DWELLING" "LOST_WORLD",
    ],
    "Big City Chillout": [
        "SAD_OLD_MANOR_FULLMIX",
        "SAD_OLD_MANOR_ALT02",
        "SAD_OLD_MANOR_ALT03",
        "SAD_OLD_MANOR_ALT04",
        "SHADY_STREETS_FULLMIX",
        "SHADY_STREETS_MARIMBA",
        "SHADY_STREETS_DULCIMER",
        "SHADY_STREETS_VIOLADEGAMBA",
        "HAUNTING_TAVERN_REMST_FULLMIX",
        "HAUNTING_TAVERN_REMST_LITE",
        "HAUNTING_TAVERN_REMST_CUTDOWN",
        "PEACEFUL_EXPLORATION",
        "MEDIEVAL_FOLKSONG",
        "DISTILLATION",
        "SLOW_COOKING_AMB",
        "SNOWYS_THEME",
        "THE_MEADOW",
        "LIGHT",
        "MISCHIEF",
        "RUBIKS_CUBE",
    ],
}


def get_playlist(name: str) -> list[str] | None:
    """Get track keys for a playlist."""
    return PLAYLISTS.get(name)


def get_all_playlists() -> list[str]:
    """Get all playlist names."""
    return list(PLAYLISTS.keys())

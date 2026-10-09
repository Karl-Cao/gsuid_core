"""Pure guard for a QR login requested from a public QQ group."""


def owns_game_uid(roles: object, expected_uid: str, game_id: str) -> bool:
    if not isinstance(roles, list) or not expected_uid:
        return False
    return any(
        isinstance(role, dict)
        and "game_id" in role
        and "game_role_id" in role
        and str(role["game_id"]) == game_id
        and str(role["game_role_id"]) == expected_uid
        for role in roles
    )


def owns_zzz_uid(roles: object, expected_uid: str) -> bool:
    return owns_game_uid(roles, expected_uid, "8")


def group_login_game(command: str) -> tuple[str, str, str, int]:
    if command.lstrip("/").lower().startswith(("ys", "gs")):
        return "2", "原神", "ys", 0
    return "8", "绝区零", "zzz", 2

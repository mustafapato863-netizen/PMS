import re


def humanize_username(username: str | None) -> str:
    normalized = (username or "").strip()
    words = [word for word in re.split(r"[._\-\s]+", normalized) if word]
    return " ".join(word.capitalize() for word in words) or "User"


def default_user_full_name(context) -> str:
    return humanize_username(context.get_current_parameters().get("username"))

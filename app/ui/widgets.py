def progress_bar(
    current: int,
    total: int,
    length: int = 10,
) -> str:
    if total <= 0:
        return "░" * length

    filled = round(current / total * length)
    filled = max(0, min(filled, length))

    return "█" * filled + "░" * (length - filled)
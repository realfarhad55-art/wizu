"""
points_banner.py — 10-emoji progress banner (Wave Crest) for a channel's points (0..100).

    10+ points -> 1 FILLED + 9 EMPTY   ...   90+ -> 9 FILLED + 1 EMPTY   |   100 -> 10 FILLED

The emoji IDs live in  points_banner_ids.json  (next to the bot, inside /opt/bot/data when that folder exists).
You never type them by hand: make the emoji pack, then send the bot (owner)   /setbannerpack <pack link>
-> the bot reads the pack (first 10 = filled 10..100, next 10 = empty 10..100) and saves the IDs.
Until the file exists, banner_line() returns "" so the record looks exactly as before (nothing breaks).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(HERE, "data")
IDS_FILE = os.environ.get("POINTS_BANNER_IDS") or os.path.join(_DATA if os.path.isdir(_DATA) else HERE,
                                                                "points_banner_ids.json")
FALLBACK = "🔹"      # shown only where custom emoji is not supported


def load_ids():
    """-> (fill_ids[10], empty_ids[10]) or None when not configured."""
    try:
        with open(IDS_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
        fill = [int(d["fill"][str(p)]) for p in range(10, 101, 10)]
        empty = [int(d["empty"][str(p)]) for p in range(10, 101, 10)]
        return (fill, empty) if all(fill) and all(empty) else None
    except Exception:
        return None


def save_ids(ids):
    """ids: list of 20 custom-emoji IDs, upload order (10 filled, then 10 empty)."""
    d = {"fill": {str(10 * (i + 1)): str(ids[i]) for i in range(10)},
         "empty": {str(10 * (i + 1)): str(ids[10 + i]) for i in range(10)}}
    os.makedirs(os.path.dirname(IDS_FILE), exist_ok=True)
    with open(IDS_FILE, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1)


def filled_count(points):
    try:
        return max(0, min(10, int(points) // 10))
    except (TypeError, ValueError):
        return 0


def banner_ids(points):
    ids = load_ids()
    if not ids:
        return None
    fill, empty = ids
    n = filled_count(points)
    return [fill[i] if i < n else empty[i] for i in range(10)]


def banner_html(points):
    """Bot API HTML (parse_mode='HTML'); '' when not configured. The 10 emojis sit side by side, NO spaces."""
    ids = banner_ids(points)
    if not ids:
        return ""
    return "".join(f'<tg-emoji emoji-id="{i}">{FALLBACK}</tg-emoji>' for i in ids)


def banner_line(points):
    """banner + newline, ready to append to a record message ('' when not configured)."""
    b = banner_html(points)
    return b + "\n" if b else ""


def banner_text_entities(points):
    """Telethon/userbot version -> (text, [MessageEntityCustomEmoji]) or ("", [])."""
    ids = banner_ids(points)
    if not ids:
        return "", []
    from telethon.tl.types import MessageEntityCustomEmoji
    ln = len(FALLBACK.encode("utf-16-le")) // 2
    return FALLBACK * 10, [MessageEntityCustomEmoji(offset=k * ln, length=ln, document_id=int(i)) for k, i in enumerate(ids)]

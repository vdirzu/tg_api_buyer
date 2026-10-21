import json
from pathlib import Path

MESSAGES = {
    lang: json.loads((Path(__file__).parent / f"{lang}.json").read_text(encoding="utf-8"))
    for lang in ("ru", "en")
}


def tr(lang: str | None, key: str) -> str:
    return MESSAGES.get(lang, MESSAGES["en"]).get(key, key)

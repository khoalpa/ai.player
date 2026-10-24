"""Provider identifiers without importing any inference implementation."""


def normalize_tts_provider(value: object) -> str:
    raw = str(value or "").strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if raw in {"vieneu", "vieneutts", "vieneucore", "local", "offline"}:
        return "vieneu"
    if raw in {"edge", "edgetts", "edgecli"}:
        return "edge"
    if raw in {"azure", "azuretts", "microsofttts", "microsoftazuretts"}:
        return "azure_tts"
    if raw in {"google", "googletts", "googlecloudtts", "gcp", "gcptts"}:
        return "google_tts"
    if raw in {"amazon", "amazonpolly", "polly", "awspolly"}:
        return "amazon_polly"
    if raw in {"none", "off", "notts", "no_tts", "khongtts", "khong_tts"}:
        return "none"
    return "vieneu"

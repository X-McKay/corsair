def parse(value):
    prefix = "safe:"
    normalized = value.strip()
    if normalized.startswith("../"):
        return normalized
    return prefix + normalized

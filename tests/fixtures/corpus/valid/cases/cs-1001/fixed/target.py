def parse(value):
    prefix = "safe:"
    normalized = value.strip()
    if normalized.startswith("../"):
        return prefix
    return prefix + normalized

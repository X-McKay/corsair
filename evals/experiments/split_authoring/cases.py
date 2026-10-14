"""Frozen matched pilot inputs; fixture labels and scripted patches never enter live prompts."""
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).parent


def load_cases(version=1):
    manifest = json.loads((ROOT / f'manifest-v{version}.json').read_text())
    for name in (f'cases-v{version}.json', f'rubric-v{version}.json', 'scripted-patches-v1.json'):
        if sha256((ROOT / name).read_bytes()).hexdigest() != manifest[name]:
            raise ValueError(f'frozen split-authoring artifact differs: {name}')
    return json.loads((ROOT / f'cases-v{version}.json').read_text())


def scripted_patches():
    load_cases()  # Check the same freeze before injecting scripted answers.
    return json.loads((ROOT / 'scripted-patches-v1.json').read_text())

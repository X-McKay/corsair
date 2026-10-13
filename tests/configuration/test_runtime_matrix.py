"""SPEC-0042 runtime matrix guards: every row is a prepared, qualified toolchain image with existing evidence."""
from pathlib import Path

from corsair.nodes.runtime.matrix import load
from tests.qualification.prepare_toolchains import BASES

ROOT = Path(__file__).resolve().parents[2]
RECORDS = {p.name.split('-', 2)[0] + '-' + p.name.split('-', 2)[1]
           for p in (ROOT / 'docs/development').glob('*/*-[0-9][0-9][0-9][0-9]-*.md')}


def test_rows_are_the_prepared_toolchain_images():
    # A prepared image gets its row only after its live gate passes, so rows are a subset of the prepared images.
    matrix = load()
    # Every row is a prepared image; a prepared image gets its row only once its live gate passes (SPEC-0045).
    assert {(Path(row.image_source).name, row.base_image) for row in matrix.images} <= set(BASES.items())
    assert all(row.image_source == f'deploy/qualification/toolchains/{Path(row.image_source).name}' for row in matrix.images)
    for row in matrix.images:
        assert (ROOT / row.image_source / 'Dockerfile').read_text().startswith('FROM ' + row.base_image)


def test_every_row_cites_existing_qualification_evidence():
    matrix = load()
    for row in (*matrix.images, *matrix.frameworks):
        assert (ROOT / row.qualification.report).is_file(), row
        assert set(row.qualification.records) <= RECORDS, row
    for row in matrix.frameworks:
        assert (ROOT / row.runner).is_file(), row

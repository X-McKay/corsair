import pytest
from pydantic import ValidationError

from corsair.contracts import Citation, Finding, ProbeDraft


def test_safe_paths_refuse_absolute_and_climbing():
    for bad in ("/etc/passwd", "../x", "a/../../b"):
        with pytest.raises(ValidationError):
            Citation(path=bad, start_line=1, end_line=1)
    Citation(path="src/app.py", start_line=1, end_line=2)


def test_probe_draft_requires_both_markers():
    with pytest.raises(ValidationError):
        ProbeDraft(role="control", test_file="t/test_x.py", test_name="test_x", source="writes no markers")
    ProbeDraft(role="control", test_file="t/test_x.py", test_name="test_x",
               source="open(os.environ['CORSAIR_MARKER_DIR'] + '/start', 'w')")


def test_finding_cwe_shape():
    with pytest.raises(ValidationError):
        Finding(title="t", cwe="89")
    assert Finding(title="t", cwe="CWE-89").cwe == "CWE-89"

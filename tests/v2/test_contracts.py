import pytest
from pydantic import ValidationError

from corsair.v2.contracts import Citation, Finding, ProbeDraft


def test_safe_paths_refuse_absolute_and_climbing():
    for bad in ("/etc/passwd", "../x", "a/../../b"):
        with pytest.raises(ValidationError):
            Citation(path=bad, start_line=1, end_line=1)
    Citation(path="src/app.py", start_line=1, end_line=2)


def test_probe_draft_requires_the_marker_dir():
    with pytest.raises(ValidationError):
        ProbeDraft(role="control", test_file="t/test_x.py", test_name="test_x", source="CORSAIR_START CORSAIR_END")
    ProbeDraft(role="control", test_file="t/test_x.py", test_name="test_x", source="os.environ['CORSAIR_MARKER_DIR']")


def test_finding_cwe_shape():
    with pytest.raises(ValidationError):
        Finding(title="t", cwe="89")
    assert Finding(title="t", cwe="CWE-89").cwe == "CWE-89"

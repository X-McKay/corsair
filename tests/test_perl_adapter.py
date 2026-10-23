"""Perl native-coverage adapter tests, including one real Devel::Cover database."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from corsair.adapters.frameworks import pytest_
from corsair.adapters.frameworks.perl import PERL_COVER_COLLECTOR, PERL_COVERAGE_JSON, Perl
from corsair.domain.verification import Outcome

PERL_TARGET = SimpleNamespace(target_file="lib/Target.pm", target_lines=(5, 7, 9))


def native_report(files: object) -> bytes:
    return json.dumps({"files": files}).encode()


def test_perl_native_map_binds_only_the_exact_work_target_and_native_lines():
    report = native_report(
        {
            "/work/lib/Target.pm": {"executed_lines": [5, 6, 7]},
            "/work/lib/Other.pm": {"executed_lines": [9]},
        }
    )
    assert pytest_.read_coverage(report, PERL_TARGET) == (True, (5, 7))
    assert pytest_.read_coverage(
        native_report({"/work/elsewhere/Target.pm": {"executed_lines": [5]}}), PERL_TARGET
    ) == (False, ())


@pytest.mark.parametrize(
    "report",
    [
        None,
        b"not json",
        native_report({"/work/lib/Target.pm": {"executed_lines": [True]}}),
        native_report({"/work/lib/Target.pm": {"executed_lines": "5"}}),
    ],
)
def test_perl_native_map_parser_fails_closed_for_missing_or_malformed_evidence(report):
    assert pytest_.read_coverage(report, PERL_TARGET) == (None, ())


def test_perl_keeps_the_shared_driver_but_replaces_python_coverage_with_native_evidence():
    junit = b'<testsuites><testsuite><testcase name="test_probe[control]"/></testsuite></testsuites>'
    record = json.dumps(
        {"role": "control", "outcome": "holds", "exception_type": None, "message": None}
    ).encode()
    files = {
        "/tmp/corsair/result.json": record,
        "/tmp/corsair/junit.xml": junit,
        # This deliberately claims a target line that the real Perl report did not execute.
        "/tmp/corsair/coverage.json": native_report({"/work/lib/Target.pm": {"executed_lines": [5, 7, 9]}}),
        PERL_COVERAGE_JSON: native_report({"/work/lib/Target.pm": {"executed_lines": [5, 7]}}),
    }
    adapter = Perl()
    assert adapter.command("control", "anything") == pytest_.Pytest().command("control", "anything")
    assert adapter.after_command() == [
        "env",
        "-u",
        "PERL5OPT",
        "perl",
        "/work/.corsair/collect_perl_coverage.pl",
    ]
    assert (
        adapter.environment("control")["PERL5OPT"]
        == "-MDevel::Cover=-db,/tmp/corsair/perl,-coverage,statement,-silent,1"
    )
    assert "/tmp/corsair/coverage.json" not in adapter.result_paths()
    result = adapter.read(files, PERL_TARGET)
    assert result.outcome is Outcome.HOLDS and result.covered_lines == (5, 7)


@pytest.mark.skipif(
    not shutil.which("perl")
    or subprocess.run(["perl", "-MDevel::Cover::DB", "-e", "1"], capture_output=True).returncode,
    reason="Perl with Devel::Cover is required",
)
def test_perl_collector_reads_real_statement_hits_from_a_native_target(tmp_path):
    work, result = tmp_path / "work", tmp_path / "result"
    source = work / "lib" / "Target.pm"
    source.parent.mkdir(parents=True)
    result.mkdir()
    source.write_text(
        "use strict;\n"
        "use warnings;\n"
        "\n"
        "sub guarded {\n"
        "    my ($value) = @_;\n"
        "    if ($value > 0) {\n"
        "        return $value;\n"
        "    }\n"
        "    return 0;\n"
        "}\n"
        'print guarded(1), "\\n";\n'
    )
    db = result / "perl"
    environment = {**os.environ, "PERL5OPT": f"-MDevel::Cover=-db,{db},-coverage,statement,-silent,1"}
    subprocess.run(
        ["perl", "lib/Target.pm"], cwd=work, check=True, env=environment, capture_output=True, text=True
    )

    collector = (
        PERL_COVER_COLLECTOR.replace('my $DB_DIR = "/tmp/corsair/perl";', f'my $DB_DIR = "{db}";')
        .replace(
            'my $REPORT = "/tmp/corsair/perl-coverage.json";',
            f'my $REPORT = "{result / "perl-coverage.json"}";',
        )
        .replace('my $WORKDIR = "/work";', f'my $WORKDIR = "{work}";')
    )
    script = tmp_path / "collect_perl_coverage.pl"
    script.write_text(collector)
    clean_environment = dict(os.environ)
    clean_environment.pop("PERL5OPT", None)
    subprocess.run(["perl", str(script)], check=True, env=clean_environment, capture_output=True, text=True)

    report = json.loads((result / "perl-coverage.json").read_text())
    lines = report["files"][str(source)]["executed_lines"]
    # Devel::Cover 1.38 maps the nested return op to its containing ``if``;
    # these are stable executed statement locations on Bookworm and newer.
    assert 5 in lines and 6 in lines and 9 not in lines

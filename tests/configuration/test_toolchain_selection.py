"""TOOLCHAINS gate selection: collection only, no cluster. A gate runs only when every image it uses is named."""
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATES = 'tests/qualification/test_toolchains.py::'


def collect(*names):
    argv = [sys.executable, '-m', 'pytest', '--collect-only', '-q', '-p', 'no:cacheprovider', 'tests/qualification',
            '-m', 'toolchain', *[arg for name in names for arg in ('--toolchain', name)]]
    done = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=120)
    return done.returncode, [line for line in done.stdout.splitlines() if line.startswith(GATES)], done.stdout + done.stderr


@pytest.mark.parametrize('names, gates', [
    (('python',), ['test_native_python_toolchain']),  # not python37: selection is by marker, never by substring
    (('python37',), ['test_native_python37_toolchain']),
    (('java8',), ['test_native_java8_toolchain']),
    (('node8',), ['test_native_node8_toolchain']),
    (('java', 'python'), ['test_native_java_toolchain', 'test_native_python_toolchain']),
    (('python', 'java', 'python37'), ['test_native_java_toolchain', 'test_native_python_toolchain', 'test_native_python37_toolchain']),
])
def test_named_images_select_exactly_the_gates_they_cover(names, gates):
    code, found, output = collect(*names)
    assert code == 0, output
    assert found == [GATES + gate for gate in gates]


@pytest.mark.parametrize('names, message', [
    (('bogus',), 'Unknown toolchain image directories'),
])
def test_an_unknown_image_is_a_usage_error(names, message):
    code, found, output = collect(*names)
    assert code == 4 and message in output

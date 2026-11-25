"""Trash tab: the render functions, executed for real.

`web/js/views/trash.js` is a browser module, so a string check against its
source proves nothing. `tests/trash_harness.js` runs the repo's own file in a
stub DOM and asserts the markup it produced (grouping, rows, panel body and
footer, the purge dialog, selection pruning, and that no inline handler is
built from an id); this test just drives that harness under pytest so the
normal suite covers it.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HARNESS = PLUGIN_ROOT / "tests/trash_harness.js"
TRASH_JS = PLUGIN_ROOT / "src/white_words/scriptwriting/web/js/views/trash.js"

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not available")


def run_harness():
    out = subprocess.run(
        ["node", str(HARNESS)],
        cwd=str(PLUGIN_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return out


def test_the_trash_render_functions_behave():
    assert TRASH_JS.exists(), f"{TRASH_JS} is missing"
    out = run_harness()
    tail = (out.stdout + out.stderr)[-3000:]
    assert out.returncode == 0, tail
    assert "all checks passed" in out.stdout, tail
    assert "FAIL" not in out.stdout, tail


def test_the_harness_reports_how_many_checks_it_ran():
    # A harness that silently stops asserting is worse than none: pin the count
    # so deleting a check is a test failure, not a quiet green.
    out = run_harness()
    assert out.returncode == 0, (out.stdout + out.stderr)[-3000:]
    m = re.search(r"all checks passed \((\d+)", out.stdout)
    if m is None:
        # The summary line may carry the count in its own format; fall back to
        # counting the per-check lines it prints.
        ran = len(re.findall(r"^\s*(?:ok|PASS)\b", out.stdout, re.M))
        assert ran >= 18, out.stdout[-3000:]
    else:
        assert int(m.group(1)) >= 18, out.stdout[-3000:]

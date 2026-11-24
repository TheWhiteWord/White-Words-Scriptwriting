import json
import shutil
import tempfile
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "save-the-children"


def _alias_legacy_package() -> None:
    """Let archived task scripts keep importing the package's pre-rename name.

    `tasks/task_40/upgrade_live_db.py` is loaded by test_utc_conversion.py, and it
    imports `story_architect`, the name the package carried before the White Words
    rename. tasks/ is history and is deliberately not rewritten, so the old name is
    answered here by a shim that forwards to the real module. A shim rather than
    the module itself: handing back the real object lets the import machinery
    rename it (`__name__`, `__spec__`), which corrupts every later import of the
    genuine path. Delete this with tasks/ when the archive leaves the tree.
    """
    import importlib
    import importlib.abc
    import importlib.util
    import sys
    import types

    OLD, NEW = "story_architect", "white_words.scriptwriting"

    class _Legacy(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_spec(self, fullname, path=None, target=None):
            if fullname != OLD and not fullname.startswith(OLD + "."):
                return None
            return importlib.util.spec_from_loader(fullname, self)

        def create_module(self, spec):
            real = importlib.import_module(NEW + spec.name[len(OLD):])
            shim = types.ModuleType(spec.name)

            def _forward(name, _real=real):
                return getattr(_real, name)

            shim.__getattr__ = _forward
            shim.__path__ = list(getattr(real, "__path__", []))
            return shim

        def exec_module(self, module):
            pass                                    # everything forwards

    if not any(getattr(f, "_legacy_alias", False) for f in sys.meta_path):
        finder = _Legacy()
        finder._legacy_alias = True
        sys.meta_path.append(finder)


_alias_legacy_package()


@pytest.fixture(autouse=True)
def _isolate_root(monkeypatch, tmp_path):
    """Patch load_plugin_config so tests never write to the live story root.

    Handlers without an explicit root_path kwarg fall back to
    load_plugin_config(). Without this, they'd read ~/.hermes/config.yaml and
    write to the real projects directory.
    """
    monkeypatch.setattr("white_words.scriptwriting.core.config.load_plugin_config", lambda: {"root_path": str(tmp_path)})


@pytest.fixture(autouse=True)
def _isolate_budget(monkeypatch, tmp_path):
    """The response budget is a user setting (env var or config.toml), so a
    developer's own value must not change what a test expects. Without this, a
    config.toml sized for a small model would make every completeness test that
    asks for all entity types start failing on that one machine."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("STORY_ARCHITECT_MAX_RESPONSE_CHARS", raising=False)


def build_fixture_db(dest: Path, root: str) -> None:
    """Import the fixture's markdown into `dest`, which must already be a copy.

    The DB is BUILT, never committed. It used to be committed, and `.gitignore`
    (`*.db`) meant git never tracked it anyway — so a fresh clone had no DB and
    **119 tests failed**. Worse, `git checkout` never restored it, so every
    "verified by stashing" claim about a fixture-dependent test was evidence of
    nothing: the stale local DB was always what ran. Three tests were called
    "pre-existing failures" across three phases because of it.

    Markdown is the source of truth and is tracked. The DB is a build artefact of
    it, so it is built from it — which removes the whole class of bug rather than
    the one instance that surfaced.
    """
    from white_words.scriptwriting.tools.story_import import handler as import_handler

    shutil.rmtree(dest / ".story" / "story.db", ignore_errors=True)
    # This fixture is session-scoped, so `_isolate_root` (function-scoped) has not
    # run yet and `load_plugin_config` still reaches for the real Hermes home.
    # Pass root_path explicitly AND patch the resolver for the duration.
    import white_words.scriptwriting.core.config

    real = white_words.scriptwriting.core.config.load_plugin_config
    white_words.scriptwriting.core.config.load_plugin_config = lambda: {"root_path": root}
    try:
        result = json.loads(import_handler(
            {"project": str(dest), "confirm": True, "root_path": root}))
    finally:
        white_words.scriptwriting.core.config.load_plugin_config = real
    assert result.get("success"), f"fixture import failed: {result}"


@pytest.fixture(scope="session")
def _built_fixture():
    """The fixture markdown with its DB built, in a temp dir, once per session.

    Session-scoped because the import is ~1s and four test files need it. Tests
    that WRITE to the project must still copy it (`fixture_path` does).
    """
    tmp = tempfile.mkdtemp()
    dst = Path(tmp) / "save-the-children"
    shutil.copytree(str(FIXTURE), str(dst))
    build_fixture_db(dst, tmp)
    yield dst
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def fixture_path(_built_fixture):
    """A private, writable copy of the fixture, DB built.

    Tests that import or modify the fixture use this so nothing writes into the
    repo.
    """
    tmp = tempfile.mkdtemp()
    dst = Path(tmp) / "save-the-children"
    shutil.copytree(str(_built_fixture), str(dst))
    yield dst
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def fixture_db(_built_fixture):
    """The fixture project, DB built, shared and READ-ONLY.

    For tests that only read. The repo fixture itself no longer carries a DB, so
    the four files that used to reach for it must be given a built one — this is
    that, so the build stays in one place.
    """
    return _built_fixture
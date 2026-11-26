"""Reading a frozen draft, without touching it.

`get_db` opens ``story.db`` read-write and migrates it. That is right for the
live database and wrong for a draft: a draft is ``chmod 0444``, and one
read-write open still leaves ``-wal``/``-shm`` beside it (SQLite creates them
before it discovers the file is read-only), while the migration would rewrite a
file nothing may ever modify.

So a draft is never opened. It is copied out with SQLite's backup API into a
throwaway project directory shaped the way every read function expects
(``<dir>/.story/story.db``), and that directory is the project path the caller
reads. The copy is text and small; it is deleted when the block ends.

``head_view`` is the same for a branch's parked head, which is a database rather
than a draft but is just as much not-to-be-opened while a merge reads it.
"""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

from ..backups import check_source
from . import store


@contextmanager
def project_view(project_path: Path, snapshot_id: str):
    """Yield a project path holding a private copy of `snapshot_id`.

    The draft itself is only ever read: it is opened ``immutable`` for the copy
    and nothing is written beside it. The yielded path is a normal project, so
    every read function and every validator reaches it unchanged. `check_source`
    refuses a draft from a newer build or below the baseline before the copy, so
    the migration `get_db` runs on the copy can never fail.
    """
    source = store.snapshot_file(project_path, snapshot_id)
    if not source.exists():
        raise ValueError(f"Draft {snapshot_id} has no file on disk.")
    check_source(source, f"Draft {snapshot_id}")
    with _copied(source) as tmp:
        yield tmp


@contextmanager
def head_view(project_path: Path, branch_id: str):
    """Yield a project path holding a private copy of a branch's parked head.

    The other branch's working state, read the way a draft is: the parked file is
    never opened read-write, and the yielded directory is a project every reader and
    validator already understands.

    The current branch is refused — its head is `story.db`, so pass the project path
    itself rather than a copy that could drift from it.
    """
    if store.get_branch(project_path, branch_id)["is_current"]:
        raise ValueError(
            f"{branch_id!r} is the branch you are working on; read the project itself."
        )
    source = store.head_file(project_path, branch_id)
    if not source.exists():
        raise ValueError(f"Branch {branch_id!r} has no head on disk.")
    check_source(source, f"branch {branch_id!r}")
    with _copied(source) as tmp:
        yield tmp


@contextmanager
def _copied(source: Path):
    """A throwaway project directory holding `source`'s bytes as `.story/story.db`."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        story = Path(tmp) / ".story"
        story.mkdir()
        with sqlite3.connect(f"file:{source}?mode=ro&immutable=1", uri=True) as src:
            dest = sqlite3.connect(str(story / "story.db"))
            try:
                # backup(), not a file copy: WAL mode means a committed write can
                # still be in story.db-wal, and a plain copy would read a stale
                # draft. The copy carries the draft's bytes, not a link to them.
                src.backup(dest)
            finally:
                dest.close()
        yield Path(tmp)

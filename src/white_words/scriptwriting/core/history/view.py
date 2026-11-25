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

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        story = Path(tmp) / ".story"
        story.mkdir()
        with sqlite3.connect(f"file:{source}?mode=ro&immutable=1", uri=True) as draft:
            dest = sqlite3.connect(str(story / "story.db"))
            try:
                # backup(), not a file copy: WAL mode means a committed write can
                # still be in story.db-wal, and a plain copy would read a stale
                # draft. The copy carries the draft's bytes, not a link to them.
                draft.backup(dest)
            finally:
                dest.close()
        yield Path(tmp)

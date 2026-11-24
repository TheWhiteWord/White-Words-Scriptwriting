from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def periodic_backup(root, slug: str) -> None:
    """Opening a project is the moment to make sure it has a recent backup.

    Runs after the response has gone out, so the page never waits for it, and
    never raises: a backup that cannot be made is logged, not shown as a broken
    dashboard.
    """
    try:
        if Path(slug).name != slug:
            return
        from white_words.scriptwriting.core.backups import maybe_periodic_backup
        maybe_periodic_backup(Path(root) / "projects" / slug)
    except Exception:
        log.warning("periodic backup of %s failed", slug, exc_info=True)


class DbChangeWatcher:
    """Reports whether another connection has committed to a SQLite database.

    Built on ``PRAGMA data_version``. SQLite defines that value per
    *connection*: it changes between two reads on the same connection only if a
    different connection committed in the interim. Reading it from a fresh
    connection each time therefore tells you nothing (every new connection sees
    the same number), so this keeps one connection open and polls on it.

    If the database file is replaced (a backup restored over it), the old
    connection still points at the old file, so the file's identity is checked
    and the connection reopened when it changes.
    """

    def __init__(self, db_path: Path):
        self._path = Path(db_path)
        self._conn = None
        self._ident = None
        self._last = None

    def _open(self):
        import sqlite3
        # mode=ro: never create an empty database file just by watching one.
        conn = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True,
                               isolation_level=None)
        st = self._path.stat()
        self._ident = (st.st_dev, st.st_ino)
        return conn

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None
        self._ident = None

    def changed(self) -> bool:
        """True if the database changed since the previous call.

        The first successful call only records a baseline and returns False.
        Any error (file missing, locked) reads as "no news" and the connection
        is rebuilt on the next call.
        """
        try:
            st = self._path.stat()
            if self._conn is not None and self._ident != (st.st_dev, st.st_ino):
                self.close()
                self._last = None
            if self._conn is None:
                self._conn = self._open()
            version = self._conn.execute("PRAGMA data_version").fetchone()[0]
        except Exception:
            self.close()
            return False
        changed = self._last is not None and version != self._last
        self._last = version
        return changed


async def event_stream(watcher: DbChangeWatcher, request, interval: float = 1.0):
    """Server-sent events: one ``update`` frame each time the database changes."""
    try:
        while not await request.is_disconnected():
            if watcher.changed():
                yield 'event: update\ndata: {"type": "update"}\n\n'
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        return
    finally:
        watcher.close()


def make_router(config, app):
    router = APIRouter()

    @router.get("/api/projects")
    def projects():
        from white_words.scriptwriting.app import services
        return {"projects": services.list_projects(config.root)}

    @router.get("/api/projects/{slug}/dashboard")
    def dashboard(slug: str, background: BackgroundTasks):
        from white_words.scriptwriting.app import services
        try:
            data = services.get_project_dashboard(config.root, slug)
        except services.ProjectNotFound as e:
            return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": str(e)}})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": {"code": "error", "message": str(e)}})
        background.add_task(periodic_backup, config.root, slug)
        return data

    @router.get("/api/projects/{slug}/events")
    async def project_events(slug: str, request: Request):
        db_path = Path(config.root) / "projects" / slug / ".story" / "story.db"
        return StreamingResponse(
            event_stream(DbChangeWatcher(db_path), request),
            media_type="text/event-stream")

    return router

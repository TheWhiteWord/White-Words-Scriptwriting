"""The one clock for stored timestamps.

Every timestamp the app WRITES to a database (or a trash record) comes from
here, as UTC with an explicit offset: `2026-11-20T09:15:00+00:00`. They used to
be naive local time, which broke the comparisons that matter: stamps are
compared as TEXT (the purge age floor, the receipt pruning) and matched by
equality ("deleted together"), so they only mean something when every stamp has
one format and one zone. A machine whose timezone or DST changed between two
writes, or a vault shared across timezones, shifted those comparisons by hours.

Not here, on purpose: names. A backup FILE name, a draft id and a trash folder
name carry the local time they were made at; they are labels, never compared
with a stamp, and renaming them would mix old and new names in one folder.
"""

from datetime import datetime, timedelta, timezone

# Every column that holds a stamp, as (table, column). The one-off conversion
# (tasks/task_40/upgrade_live_db.py) walks this list, and a test fails if the
# schema gains a `*_at` column that is not in it.
STORED_STAMPS = (
    ("entities", "deleted_at"),
    ("drafts", "created_at"),
    ("revisions", "replaced_at"),
)


def now_iso(timespec: str = "seconds") -> str:
    """Now, in UTC, with an explicit offset: '2026-11-20T09:15:00+00:00'.

    Whole seconds for the database columns. `timespec="microseconds"` is for a
    stamp that must keep two events in one second in order (a deleted project);
    it is fixed width, because `isoformat` alone drops a zero fraction and
    stamps of different lengths do not sort as text.
    """
    return datetime.now(timezone.utc).isoformat(timespec=timespec)


def ago_iso(days: int) -> str:
    """A stamp `days` before now, in the same format as `now_iso()`.

    For cutoffs that stored stamps are compared against as text, so it has to
    be exactly that format.
    """
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def parse(ts: str) -> datetime:
    """Parse a stored stamp. A naive one raises: the conversion has already run,
    so a naive stamp is unconverted data, not a format to tolerate."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        raise ValueError(f"naive timestamp in the database: {ts!r}")
    return dt

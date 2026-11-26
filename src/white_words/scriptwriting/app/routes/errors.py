"""The HTTP error envelope every route body uses.

`{"error": {"code", "message", …payload}}`, with the payload at the TOP level of
`error`. A refusal a caller must act on carries its structured parts there — a
restore's `collisions`, a switch's `open_drafts` — beside `code` and `message`,
rather than nested under a second key, because that is where the dashboard reads
them.

An HTTP concern, so it lives here and not in `core`: the core raises exceptions
with actionable messages, and each boundary decides how to spell them.
"""

from __future__ import annotations

from fastapi.responses import JSONResponse


def _err(status: int, code: str, message: str, **extra):
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message, **extra}}
    )

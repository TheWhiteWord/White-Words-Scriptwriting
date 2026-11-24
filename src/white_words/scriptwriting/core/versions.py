"""The one fingerprint behind the three version tokens (form, structure, script).

Each caller decides WHAT it hashes — the state a person was shown — and this
decides how. The tokens are opaque and short-lived: the browser stores one at
load and presents it at save, where the compare happens inside the save's
transaction (see the manual_* modules).
"""
from __future__ import annotations

import hashlib
import json


def token(payload) -> str:
    """Opaque 16-hex-digit fingerprint of what a person was shown."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

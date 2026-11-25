"""Drafts, branches and the manifest that records them.

`store` owns `history.db` and the files it points at; `fingerprint` decides when
two states are the same draft.
"""

from . import fingerprint, store

__all__ = ["fingerprint", "store"]

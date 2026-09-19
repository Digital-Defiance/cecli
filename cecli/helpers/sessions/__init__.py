"""Session persistence helpers.

The session concerns are split into focused modules so each one stays readable:

* ``layout`` - where session payloads live on disk (single files, folder
  bundles, and the ``s/`` tree used for sub-agents).
* ``storage`` - reading/writing payload files and reference documents, including
  optional encryption.
* ``payload`` - serialising a coder's state into a payload and applying a
  payload back onto a coder.
* ``subagents`` - detecting, saving, and resolving the sub-agents that belong to
  a session.
* ``manager`` - :class:`SessionManager`, the facade that ties the above together
  for save/list/load.
"""

from .layout import SESSION_REFERENCE_TYPE
from .manager import SessionManager

__all__ = ["SessionManager", "SESSION_REFERENCE_TYPE"]

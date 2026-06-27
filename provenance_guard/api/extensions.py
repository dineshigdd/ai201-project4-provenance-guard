"""Shared Flask extensions.

The rate limiter is instantiated here (unbound) and bound to the app in the
factory via `limiter.init_app(app)`. Keeping it in its own module is what avoids
a circular import: routes.py imports `limiter` to decorate `/submit`, and the
factory imports both routes and `limiter` — neither imports the other directly.

No `default_limits` are set: rate limiting is scoped to the submission endpoint
(the requirement), so read/liveness endpoints like `/health` and `/log` are not
throttled. The key function is the client IP (`get_remote_address`).
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",  # in-process store; fine for a single-node dev service
)

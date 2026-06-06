"""LandTek `holes/` package — gap-finding routines that surface system holes.

Each routine inherits from `holes.base.Routine`, implements `find_holes(cur)`, and
emits findings via `self.emit(severity, description, ...)`. The base class handles
persistence, idempotency, and run logging.

The dispatcher (`holes.dispatcher`) runs routines on their declared cadence.
The digest (`holes.digest`) consolidates open findings into a daily Telegram report.
P0 findings are pushed immediately via `holes.p0_pusher`.

See holes/README.md for the architecture.
"""
__version__ = "0.1.0"

"""LandTek client PWA assets — makes the client portal an INSTALLABLE home-screen app.

Serves the web-app manifest, the service worker, and the icon set under
/client/_app/… so they ride the existing /client/ nginx location (no new nginx
block needed) and sit OUTSIDE the /client/<token> route space (distinct path
segment, no routing conflict with client_access).

This blueprint is inert until:
  1. it is registered in server.py, AND
  2. the PWA <head> tags + SW registration are added to client_portal._client_layout
     (see PWA_INTEGRATION.md — deferred to the post-breach-fix convergence so it
     goes live only once the dependability gate reads green and tokens are re-minted).

Nothing here serves client data or requires a token — only static app chrome.
"""
from __future__ import annotations

import os

from flask import Blueprint, send_from_directory, Response

bp = Blueprint("client_pwa", __name__, url_prefix="/client/_app")

_PWA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pwa")
_ICON_DIR = os.path.join(_PWA_DIR, "icons")


@bp.route("/manifest.webmanifest")
def manifest():
    with open(os.path.join(_PWA_DIR, "manifest.webmanifest"), "rb") as f:
        body = f.read()
    return Response(body, mimetype="application/manifest+json")


@bp.route("/sw.js")
def service_worker():
    with open(os.path.join(_PWA_DIR, "sw.js"), "rb") as f:
        body = f.read()
    resp = Response(body, mimetype="application/javascript")
    # Allow the SW (served from /client/_app/) to control the wider /client/ scope
    # where the actual tokened portal pages live.
    resp.headers["Service-Worker-Allowed"] = "/client/"
    # A SW must always be revalidated so updates ship promptly.
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@bp.route("/icons/<path:name>")
def icon(name: str):
    return send_from_directory(_ICON_DIR, name, max_age=60 * 60 * 24 * 30)

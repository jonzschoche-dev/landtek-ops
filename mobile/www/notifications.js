/**
 * LandTek — local deadline reminders (the App Store guideline 4.2 native value-add).
 *
 * WHY THIS EXISTS
 *   Apple rejects bare website wrappers ("minimum functionality", guideline 4.2).
 *   This module gives the app a genuine native capability the web cannot deliver:
 *   it schedules ON-DEVICE local notifications for a client's upcoming legal
 *   deadlines, so the client is reminded even with the app closed and offline.
 *   No server push infra is required — these are LocalNotifications fired by iOS.
 *
 * DATA SOURCE (STUBBED — see TODO below)
 *   The portal already knows each client's deadlines (countdowns are rendered in
 *   the /client/<token> cockpit). We need those same deadlines as JSON so the
 *   native layer can schedule reminders. That endpoint does NOT exist yet.
 *
 *   >>> TODO (portal side, owner: leo_tools/client_access.py): expose
 *       GET https://leo.hayuma.org/client/<token>/deadlines.json
 *   returning ONLY this client's deadlines, token-scoped exactly like the portal
 *   (same trust boundary, _safe views only, no cross-matter contamination, no
 *   unmarked inference). Contract:
 *
 *     {
 *       "client_code": "MWK-001",
 *       "generated_at": "2026-07-04T09:00:00+08:00",
 *       "deadlines": [
 *         {
 *           "id": "cv26360-sj-hearing",              // stable id -> stable notification id
 *           "matter_code": "MWK-001",                 // display only
 *           "title": "Summary Judgment hearing",
 *           "due_at": "2026-08-12T09:00:00+08:00",    // ISO 8601 with offset
 *           "provenance": "verified"                  // verified | operator | inferred_*
 *         }
 *       ]
 *     }
 *
 *   RULES for the endpoint (enforce server-side, not here):
 *     - Emit a deadline ONLY when provenance is "verified" or "operator".
 *       Never schedule a reminder off inferred/pattern-matched dates — a client
 *       pinged about a fabricated deadline is a trust-ending event.
 *     - Token-scope identically to the portal: one token -> one client_code.
 *     - Dates already reconciled to a real calendar date (no draft/claimed dates).
 *
 *   Until the endpoint ships, the fetch below 404s and we schedule nothing
 *   (graceful no-op). The app still functions as the portal shell.
 *
 * NO BUNDLER: classic script. Uses window.Capacitor.Plugins.LocalNotifications.
 */
(function () {
  'use strict';

  function plugin() {
    var C = window.Capacitor;
    return C && C.Plugins && C.Plugins.LocalNotifications;
  }
  function platform() {
    var C = window.Capacitor;
    return C && C.getPlatform ? C.getPlatform() : 'web';
  }

  function deadlinesPath(token) {
    return '/client/' + encodeURIComponent(token) + '/deadlines.json';
  }

  // Notification ids are ints in Capacitor; derive a stable one from a string.
  function hashId(str) {
    var h = 0;
    for (var i = 0; i < str.length; i++) h = (Math.imul(31, h) + str.charCodeAt(i)) | 0;
    return (Math.abs(h) % 2147483000) + 1;
  }

  // Reminders placed at a few lead times; only future times are scheduled.
  var LEAD_TIMES = [
    { days: 7, label: 'in one week' },
    { days: 3, label: 'in 3 days' },
    { days: 1, label: 'tomorrow' },
  ];

  function ensurePermission(LN) {
    return LN.checkPermissions().then(function (perm) {
      if (perm.display === 'granted') return true;
      return LN.requestPermissions().then(function (r) { return r.display === 'granted'; });
    });
  }

  function fmtDate(iso) {
    try {
      return new Date(iso).toLocaleDateString(undefined,
        { month: 'short', day: 'numeric', year: 'numeric' });
    } catch (e) { return iso; }
  }

  function cancelAll() {
    var LN = plugin();
    if (!LN) return Promise.resolve();
    return LN.getPending()
      .then(function (p) {
        if (p && p.notifications && p.notifications.length) {
          return LN.cancel({ notifications: p.notifications });
        }
      })
      .catch(function () {});
  }

  /**
   * Fetch the client's deadlines (token-scoped) and (re)schedule local reminders.
   * Idempotent: cancels our previously-scheduled reminders first so a changed
   * deadline never leaves a stale ping behind.
   */
  function init(origin, token) {
    var LN = plugin();
    if (!LN || platform() !== 'ios') return Promise.resolve(); // native-only feature

    return ensurePermission(LN).then(function (granted) {
      if (!granted) return;
      return fetch(origin + deadlinesPath(token), { headers: { Accept: 'application/json' } })
        .then(function (res) {
          if (!res.ok) return null;        // endpoint not live yet (404) -> no-op
          return res.json();
        })
        .then(function (payload) {
          if (!payload) return;
          var deadlines = (payload && Array.isArray(payload.deadlines)) ? payload.deadlines : [];
          return cancelAll().then(function () {
            var now = Date.now();
            var toSchedule = [];
            deadlines.forEach(function (d) {
              // Only verified/operator provenance honored client-side too.
              if (d.provenance && !/^(verified|operator)/.test(d.provenance)) return;
              var due = Date.parse(d.due_at);
              if (isNaN(due)) return;
              LEAD_TIMES.forEach(function (lead) {
                var fireAt = due - lead.days * 86400000;
                if (fireAt <= now) return; // never schedule in the past
                toSchedule.push({
                  id: hashId(d.id + ':' + lead.days),
                  title: 'LandTek deadline',
                  body: d.title + ' is due ' + lead.label + ' (' + fmtDate(d.due_at) + ').',
                  schedule: { at: new Date(fireAt), allowWhileIdle: true },
                  smallIcon: 'ic_stat_landtek',
                  extra: { deadlineId: d.id, matter: d.matter_code },
                });
              });
            });
            if (toSchedule.length) {
              return LN.schedule({ notifications: toSchedule }).then(function () {
                console.info('[landtek] scheduled ' + toSchedule.length + ' reminder(s).');
              });
            }
          });
        })
        .catch(function () { /* offline / unreachable -> no-op, never crash launch */ });
    });
  }

  window.LandTekNotifications = { init: init, cancelAll: cancelAll };
})();

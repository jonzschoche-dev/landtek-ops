# LandTek — native iOS client app (Capacitor scaffold)

A native iOS shell around the **live, token-scoped client portal**
(`https://leo.hayuma.org/client/<token>`). One App Store binary serves every
client; each client signs in once with their access code, which is stored in the
**iOS Keychain**, and the app then loads *their* portal in a WebView.

> **Honest status:** this is a **buildable scaffold**, not a compiled app. It was
> authored on a Linux/VPS-adjacent environment with **no Xcode and no Apple
> Developer account**, so it has **never been run through `npx cap add ios`,
> compiled, signed, or submitted**. Everything under "What YOU do on your Mac" is
> genuinely still to do. The web shell logic (login, Keychain flow, portal load,
> notifications hook) is written and syntax-checked, but the native project
> (`ios/`) does not exist until you generate it on the Mac.

---

## What's DONE in this repo

- `package.json` — Capacitor 6 + the three plugins we use (`@capacitor/ios`,
  `capacitor-secure-storage-plugin` for the **Keychain**, `@capacitor/local-notifications`).
- `capacitor.config.ts` — `appId: org.hayuma.landtek`, `webDir: www`, allowed
  navigation locked to `leo.hayuma.org`, https-only scheme. Deliberately **no
  `server.url`** (the binary must not bake in a per-client tokened URL).
- `www/` — the bundled login shell:
  - `index.html` + `assets/styles.css` — the access-code entry screen.
  - `app.js` — reads/writes the token in the **iOS Keychain**, validates it
    against the live portal before saving, loads the tokened portal, and provides
    `window.LandTek.signOut()` (clears Keychain + cancels reminders).
  - `notifications.js` — the **guideline-4.2 native value-add**: schedules
    on-device local notifications for the client's upcoming deadlines. Reads a
    portal JSON endpoint that is **stubbed** (see "TODO: deadlines endpoint").
- `ios-resources/` — Info.plist additions (notification usage string, ATS note)
  and icon instructions to merge after the native project is generated.

## What YOU do on your Mac (the app is NOT built until you do this)

### 0. Prerequisites
- **macOS + Xcode** (from the Mac App Store; includes the iOS SDK + Simulator).
- **Node.js 18+** (`brew install node`) and CocoaPods (`sudo gem install cocoapods`
  or `brew install cocoapods`).
- **Apple Developer Program membership — $99/year** (required to run on a real
  device via TestFlight and to submit to the App Store).
- A **bundle identifier** — this scaffold uses `org.hayuma.landtek`. Register it
  under Certificates, Identifiers & Profiles (or let Xcode auto-create it during
  "Automatically manage signing").

### 1. Install dependencies
```bash
cd mobile
npm install
```

### 2. Generate the native iOS project
```bash
npx cap add ios      # creates mobile/ios/ (the real Xcode project)
npx cap sync ios     # copies www/ + installs the native plugins via CocoaPods
```

### 3. Merge the iOS resources
- Merge `ios-resources/Info.plist.additions.xml` into `ios/App/App/Info.plist`
  (notification usage string is required).
- Add app icons — see `ios-resources/README-icons.md` (the
  `@capacitor/assets` route is easiest).

### 4. Open + sign in Xcode
```bash
npx cap open ios
```
- Select the **App** target -> **Signing & Capabilities**.
- Check **Automatically manage signing**, pick your **Team** (your Apple
  Developer account).
- Confirm the bundle id is `org.hayuma.landtek`.
- Under **Signing & Capabilities**, add the **Push Notifications** capability is
  **NOT** needed — we use *local* notifications only. You may add the
  **Background Modes** capability if you later want remote refresh; not required now.

### 5. Run it
- Pick a Simulator or your plugged-in iPhone and press **Run** (⌘R).
- First launch shows the access-code screen. Paste a **real client token** (mint
  one with `python3 leo_tools/client_access.py mint MWK-001`). The app validates
  it against `leo.hayuma.org`, stores it in the Keychain, and loads the portal.
- To test "switch account": call `window.LandTek.signOut()` from Safari Web
  Inspector, or wire a Sign-out button in the portal (see below).

### 6. TestFlight (internal testing)
- In Xcode: **Product -> Archive** -> **Distribute App** -> **App Store Connect** ->
  **Upload**.
- In **App Store Connect** (appstoreconnect.apple.com), the build appears under
  **TestFlight** after processing (~10-30 min). Add yourself / clients as
  internal or external testers. External testers require a **Beta App Review**
  (usually < 24h).

### 7. App Store submission
- In App Store Connect, create the app record (same bundle id), fill in
  metadata, privacy details, screenshots (6.7" + 6.5" iPhone at minimum).
- Attach the build, submit for review.
- **Review takes ~1-3 weeks in practice for a first submission** (often faster,
  but plan for it). Expect at least one round of questions.

---

## App Store guideline 4.2 (minimum functionality) — the rationale to paste into Review Notes

> LandTek is the native client app for an existing legal-matter service. Beyond
> presenting the client's secure workspace, the app provides **on-device local
> notifications that remind the client before each of their matter deadlines**
> (hearings, filing dates). These reminders are scheduled and fired natively by
> iOS and work with the app closed and offline — functionality a website cannot
> provide. Sign-in is via a per-client access code stored in the iOS Keychain,
> with sign-out/switch-account support. The app is not a generic web wrapper; it
> is the dedicated, secured client surface for our service with native reminder
> capability.

Reviewers reject apps that are *only* a website in a frame. Our defensible
native value-add is the **local deadline reminders**. Keep that feature working
and visible (the permission prompt appears on first portal entry) before you
submit.

### Privacy answers (App Store Connect "App Privacy")
- Data collected: the app itself stores only the **access token, on-device, in
  the Keychain**. It transmits nothing to third parties. The portal it loads is
  first-party (`leo.hayuma.org`). Declare "Data Not Collected" for the app layer;
  describe the portal's data handling per your service's privacy policy.
- You will need a **privacy policy URL** — host one on `hayuma.org`.

---

## TODO: the deadlines endpoint (portal side — NOT in this scaffold)

`www/notifications.js` fetches:
```
GET https://leo.hayuma.org/client/<token>/deadlines.json
```
This endpoint **does not exist yet**. Until it ships, the app schedules nothing
(graceful no-op) and still works as the portal shell. It belongs in the portal
(`leo_tools/client_access.py`), owned by another session — do not add it here.

Required JSON shape (token-scoped, same trust boundary as the portal):
```json
{
  "client_code": "MWK-001",
  "generated_at": "2026-07-04T09:00:00+08:00",
  "deadlines": [
    {
      "id": "cv26360-sj-hearing",
      "matter_code": "MWK-001",
      "title": "Summary Judgment hearing",
      "due_at": "2026-08-12T09:00:00+08:00",
      "provenance": "verified"
    }
  ]
}
```
Server-side rules (must be enforced there, not trusted from the client):
- Emit a deadline **only** when provenance is `verified` or `operator`. Never
  schedule a reminder off inferred/pattern-matched dates.
- Token-scope identically to the portal (one token -> one client_code); **no
  cross-matter contamination**.
- Dates already reconciled to a real calendar date (no draft/claimed dates).

---

## Security / discipline notes

- **Token in Keychain only.** `capacitor-secure-storage-plugin` persists to the
  iOS Keychain (`kSecClassGenericPassword`), not `UserDefaults`/plaintext. The
  only non-iOS fallback is a **dev localStorage shim** in `app.js` that runs when
  Capacitor is absent (i.e. opening the page in a desktop browser) — it never
  runs on device.
- **The app never bypasses the portal.** All client data rendering, auth
  resolution, and `_safe`-view enforcement stay server-side behind the token.
  The app only holds the token to build the one portal URL.
- **No client data cached.** The WebView loads the live portal each launch; we do
  not persist matter content locally.
- **Before you submit:** make sure the underlying data has cleared your
  dependability gate. A paying client catching a fabricated fact or a
  cross-matter leak in the app is worse than no app. Ship the reliability first.

## Optional: wire a "Sign out" button inside the portal
The portal can call the native sign-out via a link/button that navigates the
WebView back to the shell:
```html
<a href="index.html" onclick="window.LandTek && window.LandTek.signOut(); return false;">
  Sign out
</a>
```
`window.LandTek.signOut()` clears the Keychain token and cancels scheduled
reminders, then returns to the access-code screen. (The portal is a different
origin than the bundled shell, so `window.LandTek` is only in scope on the shell
page; for an in-portal button, use a `capacitor://` deep link or a small bridge —
documented as a follow-up, not required for v1.)

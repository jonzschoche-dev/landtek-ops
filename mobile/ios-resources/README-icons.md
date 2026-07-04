# iOS app icon + notification icon

Capacitor does not generate icons for you. Two ways to get them onto the native
project (done ON YOUR MAC, after `npx cap add ios`):

## Option A — @capacitor/assets (recommended)
1. Put a single 1024x1024 PNG at `mobile/assets/icon.png` (no alpha, no rounded
   corners — Apple rounds it).
2. Optionally `mobile/assets/splash.png` (2732x2732, centered logo).
3. Run:
   ```
   cd mobile
   npm i -D @capacitor/assets
   npx capacitor-assets generate --ios
   ```
   This writes all required sizes into `ios/App/App/Assets.xcassets`.

## Option B — by hand in Xcode
Open `ios/App/App/Assets.xcassets` -> `AppIcon`, drag in the required sizes.

## Notification small icon
`capacitor.config.ts` and the scheduled notifications reference
`ic_stat_landtek`. On iOS the notification uses the app icon by default, so this
name matters mainly if you later add Android. You can leave it as-is for iOS.

The brand color used in the shell is `#1f513f` (deep green). Match the icon to it.

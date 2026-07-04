import type { CapacitorConfig } from '@capacitor/cli';

/**
 * LandTek client workspace — Capacitor iOS config.
 *
 * DESIGN NOTE (read before changing anything here):
 *   A single App Store binary is identical for every client, so it CANNOT bake
 *   in a per-client token. `server.url` is therefore intentionally NOT set to the
 *   tokened portal. The app boots its own bundled login shell (www/index.html),
 *   the client enters their access code once, we store it in the iOS Keychain,
 *   and only THEN do we navigate the WebView to the live token-scoped portal:
 *
 *       https://leo.hayuma.org/client/<token>
 *
 *   The portal is the trust boundary (token -> one client_code, server-side,
 *   hashed). The app never reimplements it and never caches client data.
 */
const config: CapacitorConfig = {
  appId: 'org.hayuma.landtek',
  appName: 'LandTek',
  webDir: 'www',

  // Bundled login shell loads first. No remote server.url on launch — the
  // tokened portal is loaded by the shell AFTER Keychain auth (see www/app.js).
  server: {
    // The portal origin the WebView is allowed to navigate to after login.
    // Keeping it here (not as server.url) documents the one allowed host.
    allowNavigation: ['leo.hayuma.org'],
    // iOS: https only. No cleartext.
    iosScheme: 'https',
  },

  ios: {
    // Content stays within the WebView; links to the portal open in-app.
    limitsNavigationsToAppBoundDomains: false,
  },

  plugins: {
    LocalNotifications: {
      // Small mono badge/icon config is set in Xcode asset catalog after
      // `npx cap add ios`. See mobile/README.md.
      smallIcon: 'ic_stat_landtek',
      iconColor: '#1f513f',
    },
  },
};

export default config;

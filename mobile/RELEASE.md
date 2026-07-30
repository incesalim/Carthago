# Shipping the app to Google Play

Build path is **EAS Build** (Expo's cloud builder). It generates and stores the
signing keys, produces the Play-ready `.aab`, and uploads it — which is also why
it is the safer option: the one artefact you can never regenerate is a signing
key, and EAS keeps it off this laptop.

## What only you can do

These need an account or a credential, so they are yours — not something that
can or should be automated from this repo:

1. **An Expo account** — <https://expo.dev/signup>, free.
2. **A Google Play Console account** — <https://play.google.com/console>,
   **one-off $25**. Registration asks for identity verification and, for an
   individual account, a public contact address.
3. **`eas login`** on this machine, once.

Everything else below is already configured in `app.json` / `eas.json`.

## Build and submit

```bash
npm i -g eas-cli          # or npx eas-cli@latest <cmd>
cd mobile
eas login
eas build:configure       # links this project to your Expo account, writes the project id
eas build --platform android --profile production
```

The first production build asks to generate an Android Keystore — **say yes**.
EAS then holds it, and Google's Play App Signing holds the final app signing
key, so a lost laptop is not a lost app.

That emits an `.aab`. Then either upload it by hand in the Play Console, or:

```bash
eas submit --platform android --latest
```

`eas.json` deliberately submits to the **`internal` track as a `draft`** — it
does not go live to the public on the first push. Promote it in the Play Console
once you have looked at it. Change `submit.production.android.track` when you
actually want production.

## Versioning

`eas.json` sets `appVersionSource: "remote"` with `autoIncrement`, so **EAS owns
`versionCode`** and bumps it per build. The `versionCode: 1` in `app.json` is
only a seed. Play rejects a re-used `versionCode`, and hand-managing it across
two platforms is the usual way that happens.

Bump `expo.version` (`"1.0.0"`) by hand for a user-visible release name.

## The Play Data Safety form

Answer **"No, this app does not collect or share any user data."** That is
verifiable rather than aspirational:

| Question | Answer | Evidence |
|---|---|---|
| Data collected / shared | None | no analytics SDK in `package.json`; nothing in `src/` calls one |
| Permissions | `INTERNET` only | merged release manifest — `SYSTEM_ALERT_WINDOW`, `VIBRATE` and both legacy storage permissions are stripped via `android.blockedPermissions` in `app.json` |
| Accounts / login | None | no auth code exists |
| Local storage | On-device cache only, never uploaded | `src/api/use-resource.ts` (AsyncStorage) |
| Ads / IAP | None | no SDKs |
| Data deletion | Uninstall removes everything | nothing is held server-side about a user |

Privacy policy URL: **<https://carthago.app/privacy>** — its "The mobile app"
section describes exactly the above. Keep the two in step; a Data Safety answer
that contradicts the policy is a review rejection and, later, a takedown.

## Store listing

- **App name**: Carthago
- **Short description** (≤80): *Turkish banking sector data — audited bank
  financials, ratios and macro context.*
- **Full description**: lead with what it is (a reader over BRSA/BDDK filings
  and TCMB macro series), that every figure is computed from published sources,
  and that it is free with no account. Do not claim investment advice.
- **Category**: Finance. **Content rating**: everyone.
- **Screenshots**: at least 2 phone shots, 1080×2364 works. Capture with
  `adb shell screencap -p /sdcard/x.png && adb pull /sdcard/x.png`.
- **Feature graphic**: 1024×500 — **not yet made**.

⚠️ **The app icon is a 256→1024 upscale** of the site's brand mark. It passes,
but it is soft at 512px in the Play listing. A native-resolution export of the
mark is worth doing before you publish.

## Before you submit — read this

**Upstream data terms.** The Yahoo-sourced market tape (BIST indices, FX, Brent,
gold) was **removed from the app and from `/api/app/v1`** precisely because a
store listing is a formal, publisher-named act of redistribution and Yahoo's
terms forbid it. The website still shows it. Do not add it back to the app.

The app's remaining sources — BRSA/BDDK filings and TCMB EVDS — are
attribution-licensed, which covers a free app. **Monetising** this app (ads,
paid tier, IAP) would need written permission from those upstreams first. See
`docs/PROJECT_STATE.md` § upstream data terms.

## Local release build (no EAS)

Only if you need an `.aab` without the cloud. Requires your own keystore, which
you must generate and back up yourself — lose it and you can never update the
listing:

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:JAVA_HOME    = "C:\Program Files\Android\Android Studio\jbr"
cd android; .\gradlew.bat bundleRelease -PreactNativeArchitectures=arm64-v8a
```

⚠️ Out of the box this signs with the **debug** keystore — the React Native
template's default — and Play rejects it. A real local release needs a
`signingConfigs.release` block, and because `android/` is regenerated by
`expo prebuild` that has to come from a config plugin, not a hand edit. EAS
avoids the whole problem, which is why it is the documented path.

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

That emits an `.aab`. Getting it to Play has two routes, and for a **first**
release the manual one is preferable:

**Manual (recommended for release 1).** Create the app in the Play Console,
then upload the `.aab` yourself under Testing → Internal testing. Contrary to a
common belief, EAS *can* do a first submission — but doing it by hand means no
Google service-account key has to exist yet, you see exactly what is uploaded,
and there is one less credential in play the first time round.

**Automated (`eas submit`).** Worth setting up once releases become routine:

```bash
eas submit --platform android --latest
```

⚠️ This needs a **Google Service Account JSON key** — created in Google Cloud,
granted access in the Play Console, then uploaded to EAS. That file is a
credential with upload rights to your Play account: keep it out of this repo,
and never paste it into a chat (including with me).

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
- **Category**: Finance · **Content rating**: everyone · **Free**, no IAP
- **Feature graphic**: `assets/store/feature-graphic.png` (1024×500, ✅ made).
  Regenerate with `assets/store/make-feature-graphic.ps1` — it renders in the
  Desk's own system from the real Instrument Sans / Plex Mono files in
  `node_modules`, so it cannot drift from the app's typography.
- **Screenshots**: at least 2 phone shots; 1080×2364 from the test device works.
  `adb shell screencap -p /sdcard/x.png && adb pull /sdcard/x.png`

**Short description** (79/80 chars):

```
Turkish banking sector data — audited bank financials, ratios and macro context.
```

**Full description:**

```
Carthago is a reader for Türkiye's banking sector. Every figure is computed
from a published source — never typed in.

WHAT IT COVERS
• Audited BRSA filings for 38 banks — balance sheet, income statement, capital,
  asset quality, liquidity
• BDDK monthly and weekly sector aggregates
• TCMB macro series — inflation, policy rate, GDP, current account, budget

IN THE APP
Overview — the sector's vitals (capital adequacy, NPL ratio, net interest
margin, loan/deposit, ROE, ROA) with 13-month trends, what moved since last
month, how the macro backdrop feeds through to bank earnings, and rule-based
flags that print the rule they fired by.

Banks — every bank, size-ranked and searchable. Tap through for a per-bank
scorecard with quarterly trends, earnings quality, TFRS-9 loan stages, branch
and headcount figures, and that bank's KAP disclosures.

Economy — twelve TCMB series, tap any one to chart it.

News — regulator announcements and press coverage, with a summary of the
recent regulatory window.

PRIVACY
No account. No ads. No tracking of any kind: the app ships no analytics SDK and
requests exactly one permission — internet access. Screens you have opened are
cached on your device so the app opens instantly and still shows something
without a connection. Nothing about you is collected or uploaded.

Carthago is an information tool, not investment advice. It is not affiliated
with BDDK, the BRSA, the TCMB, or any bank.

Sources: BDDK, BRSA bank filings, TCMB EVDS, TÜİK, KAP.
Full dashboard: https://carthago.app
```

- **App icon**: `assets/store/store-icon-512.png` (512×512 exactly, opaque —
  Play renders alpha as black). Regenerate with `assets/store/make-app-icons.ps1`,
  which also emits the in-app icons. Both derive from
  `scripts/brand/carthago-app-icon-512.png` — a native-resolution export, not an
  upscale.

## Closed testing — the 12/14 rule

A **personal** Play developer account created after 2023-11-13 cannot publish to
production until it has run a **closed test with ≥12 testers opted in
continuously for 14 days**. Only then does "Apply for production access" unlock
on the Console dashboard. Organisation accounts and older personal accounts are
exempt.

What actually counts:

- **Opted in** = the tester followed the closed-track opt-in link and accepted
  it under the *same Google account* they use on the device. An invite that was
  sent but never accepted counts for nothing.
- **Continuously** = the 14-day clock restarts if the tester count drops below
  12. Recruit a couple of spares rather than exactly 12.
- **14 days** is elapsed time on the closed track, not time since upload — the
  clock starts when the twelfth tester is opted in, not when the build lands.
- Testers must be added to the **closed** track (`Testing → Closed testing`).
  The **internal** track — which `eas.json` targets by default — does *not*
  count towards this requirement. Internal is for you and a handful of people;
  it is the right place for a first smoke test, but promote the build to a
  closed track before starting the clock.

So the order is: upload → internal track, look at it yourself → promote to a
closed track → send the opt-in link → hold ≥12 for 14 days → apply.

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

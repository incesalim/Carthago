/**
 * /privacy — what the site collects, stated against what the code does.
 *
 * Written 2026-07-25, two days after GA4 shipped, because a page that runs
 * analytics without saying so is the one kind of claim this project cannot
 * verify for the reader. Every statement here corresponds to code in this repo,
 * which is public: `GoogleAnalytics.tsx` / `AnalyticsConsent.tsx` (the tag and
 * its gate), `Beacon.tsx` (Cloudflare), `lib/bot.ts` + migrations 0020/0033 (the
 * Telegram bot's storage). If one of them changes, this page changes with it.
 *
 * Static — no data layer, no D1 read.
 */
import type { Metadata } from "next";
import Link from "next/link";
import ConsentControl from "./ConsentControl";

export const metadata: Metadata = {
  title: "Privacy",
  description:
    "What Carthago collects, why, and how to opt out — analytics, cookies, the Telegram bot, and the third parties involved.",
  alternates: { canonical: "/privacy" },
};

const UPDATED = "25 July 2026";
const CONTACT = "incesalim10@gmail.com";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-hair pt-5">
      <h2 className="mb-2 text-[15px] font-semibold tracking-tight text-foreground">{title}</h2>
      <div className="space-y-3 text-[13.5px] leading-relaxed text-foreground">{children}</div>
    </section>
  );
}

export default function PrivacyPage() {
  return (
    <div className="mx-auto max-w-3xl px-5 py-8 lg:px-8 lg:py-10">
      <header className="mb-6">
        <h1 className="text-[26px] font-semibold tracking-tight text-foreground">Privacy</h1>
        <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.06em] text-faint">
          Last updated {UPDATED}
        </p>
      </header>

      <p className="mb-7 text-[13.5px] leading-relaxed text-foreground">
        Carthago is a public dashboard over Turkish banking-sector data. There are no
        accounts, no sign-up, no newsletter and no forms — nothing on this site asks you
        for personal information, and nothing here is sold or shared for advertising.
        What follows is the complete list of what is nevertheless collected when you
        visit.
      </p>

      <div className="space-y-6">
        <Section title="Analytics, and your choice">
          <p>
            Two analytics tools measure how the site is used. They are not equivalent, and
            only one of them asks you first.
          </p>
          <ul className="ml-4 list-disc space-y-2.5 marker:text-faint">
            <li>
              <b className="font-semibold">Google Analytics 4</b> — loads only if you
              accept. It sets cookies in your browser and sends your visit (pages viewed,
              approximate location from your IP address, device and browser, referring
              site) to Google, which acts as an independent controller of that data under
              its own terms. If you decline, or never answer, the Google tag is never
              requested at all — nothing is set and nothing is sent.
            </li>
            <li>
              <b className="font-semibold">Cloudflare Web Analytics</b> — always on. It is
              cookieless by design: it stores no identifier in your browser and does not
              build a profile across visits. It reports page counts, referrers and load
              performance in aggregate. Because it cannot single you out, it is not gated
              behind the choice below.
            </li>
          </ul>
          <ConsentControl />
        </Section>

        <Section title="Cookies">
          <p>
            If you decline analytics, this site sets <b className="font-semibold">no
            cookies at all</b>. Accepting sets Google&rsquo;s (
            <code className="font-mono text-[12px]">_ga</code> and related), which is what
            the choice is about.
          </p>
          <p>
            Your answer itself is remembered in your browser&rsquo;s local storage under a
            single key, <code className="font-mono text-[12px]">carthago:analytics-consent</code>.
            It never leaves your device, contains no identifier, and exists only so you are
            not asked on every page. Clearing your browser storage forgets it, and the
            question comes back.
          </p>
          <p>
            One further cookie exists but is not for visitors: an administrative session
            cookie on <code className="font-mono text-[12px]">/admin</code>, set only after
            a password login by the site&rsquo;s operator.
          </p>
        </Section>

        <Section title="Hosting and logs">
          <p>
            The site runs on Cloudflare Workers, and the data behind it in Cloudflare D1
            and R2. Serving a page necessarily involves Cloudflare processing your IP
            address and request headers, as any web host does, including for security and
            abuse prevention. The public read-only API under{" "}
            <code className="font-mono text-[12px]">/api/v1</code> uses no cookies and
            requires no key.
          </p>
        </Section>

        <Section title="The mobile app">
          <p>
            The Carthago app for Android and iOS is a read-only reader over the same
            data. It collects <b className="font-semibold">nothing</b> — and unlike the
            website, that is not a claim with an analytics caveat attached: the app ships
            no analytics SDK of any kind, no Google Analytics, no Cloudflare beacon, no
            crash reporter, no advertising identifier.
          </p>
          <ul className="ml-4 list-disc space-y-2.5 marker:text-faint">
            <li>
              <b className="font-semibold">No account, and nothing to sign into.</b> The
              app never asks for a name, an email or a password.
            </li>
            <li>
              <b className="font-semibold">One permission: internet access.</b> That is
              the entire list. No location, no contacts, no files, no camera, no
              notifications — and nothing that lets it draw over other apps.
            </li>
            <li>
              <b className="font-semibold">A local cache, on your device only.</b> Screens
              you have opened are stored on the phone so the app opens instantly and
              still shows something without a connection. It holds published banking
              figures, never anything about you, it is never uploaded anywhere, and
              uninstalling the app deletes it.
            </li>
            <li>
              <b className="font-semibold">Requests reach our own server only.</b> The app
              talks to <code className="font-mono text-[12px]">carthago.app</code> and
              nowhere else. Those requests are logged the same way this website&rsquo;s
              are, described under &ldquo;Hosting and logs&rdquo; below. Tapping a news
              headline opens that publisher&rsquo;s page in your browser, at which point
              their privacy policy applies, not ours.
            </li>
          </ul>
        </Section>

        <Section title="The Telegram bot">
          <p>
            If you use the Telegram question-and-answer bot, that is a separate surface
            with its own handling, and more is retained there than on the website:
          </p>
          <ul className="ml-4 list-disc space-y-2.5 marker:text-faint">
            <li>
              <b className="font-semibold">Your question text is stored</b>, together with
              the database query the model generated from it and whether that query
              succeeded. This exists to catch a specific failure — a model that quietly
              answers over the wrong subset of banks — which is not diagnosable after the
              fact without the question.
            </li>
            <li>
              Those stored questions carry a <b className="font-semibold">short,
              non-reversible hash</b> of your Telegram chat id, not the id itself: enough
              to group repeated failures from one conversation, not enough to identify who
              asked.
            </li>
            <li>
              A separate daily counter used for rate-limiting does hold your{" "}
              <b className="font-semibold">Telegram chat id</b> in full, with a per-day
              message count and nothing else.
            </li>
            <li>
              Your question is sent to a third-party model provider (currently Groq and
              Cerebras) to be turned into a database query. Do not put anything
              confidential in it.
            </li>
          </ul>
          <p>
            Telegram itself is not operated by this site; your use of it is governed by
            Telegram&rsquo;s own privacy policy.
          </p>
        </Section>

        <Section title="What is not here">
          <p>
            No advertising, no ad networks, no third-party trackers beyond the two
            analytics tools named above, no fingerprinting, no session recording, no
            heatmaps, no data sold or shared with data brokers. Fonts are served from this
            site, not from Google Fonts, so loading a page makes no request to Google
            unless you accepted analytics.
          </p>
        </Section>

        <Section title="Your rights, and how to exercise them">
          <p>
            Depending on where you live — under the GDPR in the EU/UK, or under KVKK
            (Law No. 6698) in Türkiye — you may have the right to ask what personal data
            is held about you, to have it corrected or deleted, and to object to its
            processing.
          </p>
          <p>
            In practice the website holds nothing that identifies you: decline analytics
            and there is no identifier to request. For the Telegram bot, a request naming
            your chat id will have the stored questions and counter for that id deleted.
          </p>
          <p>
            Write to{" "}
            <a
              href={`mailto:${CONTACT}`}
              className="font-semibold text-primary underline-offset-2 hover:underline"
            >
              {CONTACT}
            </a>
            . This is a solo, non-commercial project, so expect a human reply rather than
            a ticketing system.
          </p>
        </Section>

        <Section title="Changes">
          <p>
            This page carries the date it was last changed. Because the site is{" "}
            <a
              href="https://github.com/incesalim/Carthago"
              className="font-semibold text-primary underline-offset-2 hover:underline"
              rel="noopener"
            >
              open source
            </a>
            , the change history of both the code described here and this page itself is
            public and checkable.
          </p>
          <p className="text-[12.5px] text-muted-foreground">
            This notice describes what the software does. It is not legal advice.
          </p>
        </Section>
      </div>

      <footer className="mt-9 border-t border-border pt-3 font-mono text-[8.5px] uppercase leading-relaxed tracking-[0.04em] text-faint">
        Every statement above corresponds to code in the public repository ·{" "}
        <Link href="/" className="text-primary">
          Back to the dashboard
        </Link>
      </footer>
    </div>
  );
}

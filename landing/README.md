# Plugfile landing page

Single-file landing page (`index.html`) for `plugfile.ai` — value prop,
architecture diagram, pricing tiers, and a Stripe-backed waitlist deposit.
Designed to deploy in ~30 minutes for under $20.

## What it is

Plain HTML + inline CSS, zero build step, zero JavaScript framework. Loads
in under 100 ms on cold cache. The single dependency is the Stripe Payment
Link URL you'll paste in below.

## Deploy in 3 steps

### Step 1 — Buy the domain (~$15/yr)

`plugfile.ai` is the recommended target. Fallbacks: `plugfile.com`,
`useplugfile.com`, `plugfilew3.com`. Buy through:

- **Cloudflare Registrar** — sells domains at wholesale, free WHOIS privacy.
- **Porkbun** — comparable pricing, decent UX.
- **Namecheap** — fine but a touch pricier.

### Step 2 — Set up the Stripe Payment Link (~5 min, free)

1. Sign up at `dashboard.stripe.com` (free until you take payments).
2. Products → **+ Add product**:
   - Name: `Plugfile — Founders early access`
   - Pricing: **One time**, $1.00 USD
   - Description: "Refundable deposit. Locks launch-tier pricing for 12 months."
3. Save → click the new product → **Create payment link**.
4. Configure the link:
   - **Collect customer email** ✓ (this IS the signal; you need it)
   - **Billing address**: Off
   - After payment: **Show confirmation page** with message
     "Reserved. We'll email you when Plugfile opens to your district."
   - **Refund policy** in description: "Fully refundable any time before launch."
5. Copy the URL (looks like `https://buy.stripe.com/abc123...`).
6. Open `index.html`, find the placeholder
   `https://buy.stripe.com/REPLACE_WITH_YOUR_PAYMENT_LINK`,
   paste your real URL.

### Step 3 — Deploy to Vercel (free)

The fastest path uses your existing GitHub repo:

```bash
cd C:\Users\karee\Plugfile\Plugfile
git add landing/
git commit -m "Add plugfile.ai landing page with Stripe waitlist"
git push
```

Then in your browser:

1. `vercel.com` → **Add new project** → import `meencoder/PlugFile`.
2. **Root directory** → set to `landing/`.
3. **Framework preset** → Other (no build step).
4. Deploy. You'll get a `plugfile-Plugfile.vercel.app` URL within ~30 sec.
5. Project → **Settings → Domains** → add `plugfile.ai`. Vercel will show
   the DNS records to add at your registrar (an A record + CNAME). Copy
   them into Cloudflare/Porkbun/Namecheap. SSL provisions automatically
   in 1-5 min.

Alternative hosts that work just as well: Cloudflare Pages, Netlify,
GitHub Pages. All free for this volume.

## What to measure

The conversion you care about is **deposit-paid / unique visitor**, not
pageviews. Stripe Dashboard shows the deposit count directly. Add a free
analytics pixel for visitor counts:

- **Plausible** ($9/mo, privacy-friendly, 1-line script tag).
- **Simple Analytics** ($9/mo, similar.)
- **Vercel Analytics** (free for hobby tier, baked in.)

Realistic baseline expectations for cold traffic in a B2B vertical:

| Metric | Cold LinkedIn ad to Texas operators | Warm intro / referral |
|--------|-------------------------------------|----------------------|
| Pageview → "Reserve" click | 3-8% | 15-25% |
| Click → Stripe checkout start | 30-50% | 50-70% |
| Checkout start → $1 paid | 40-60% | 60-80% |
| **Visitor → deposit paid** | **0.4-2.4%** | **5-14%** |

So 1000 cold visitors = roughly 4-24 deposits. 1000 warm visitors = 50-140.
Either signal is more credible than 100 verbal "yes I'd pay $299" answers.

## Drive traffic

Cheap, fast, real-signal channels:

1. **LinkedIn ads.** Target job titles "Production Engineer," "Compliance
   Manager," "Operations Manager" + companies in the SPE Texas chapter
   directory. $200-500 budget over 7 days yields ~500-2000 impressions
   per $100 in this niche.
2. **r/oilandgasworkers** — a single Show HN-style post is free and gets
   real practitioner replies; just don't be a vendor about it.
3. **TIPRO / Texas Alliance member forums.** Members-only but high signal.
4. **Cold-DM sequence to ex-RRC inspectors and plugging contractors on
   LinkedIn** — not the operators directly. They're the influencers in
   this space.

## Iteration: A/B-testable surfaces

If you want to test pricing rigorously, swap the headline on the pricing
section and the deposit amount on the Stripe Payment Link. Suggested
tests, in order of value:

1. **Deposit amount.** $1 vs $25 vs $100. Bigger deposit = stronger
   signal but lower volume. Most B2B founders learn the most from $25.
2. **Headline.** "W-3 compliance, automated" vs "Stop hand-typing
   plugging records" vs "The W-3 your district office stops returning."
3. **Pricing tiers.** $299/$499 vs $399/$799 vs per-well usage pricing.
4. **Hero CTA.** "Reserve early access" vs "Lock founder pricing" vs
   "Join the waitlist."

Run one test at a time, two weeks each, ~500 visitors per arm minimum.

## Legal one-liner to add when you take real deposits

Update the small print under the Reserve button to:

> Plugfile LLC will hold your $1 deposit pending product launch (estimated
> Q3 2026). You may request a full refund at any time by replying to your
> deposit confirmation email. If Plugfile does not launch by 2026-12-31,
> deposits are refunded automatically.

This is a fair, simple commitment. Not legal advice.

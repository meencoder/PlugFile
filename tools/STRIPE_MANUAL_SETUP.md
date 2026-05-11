# Stripe manual setup — step by step, field by field

Everything you need to click through in the Stripe dashboard *before* running
`tools/stripe_setup.py`. Total time: ~20 min if you have your bank info handy.

The script automates Product / Price / Payment Link creation. Stripe's KYC
rules require a human for everything below.

---

## Step 1 — Sign up

**URL:** https://dashboard.stripe.com/register

| Field | Value | Notes |
|---|---|---|
| Email | `quadri.ks@gmail.com` (or your real personal email) | Use a personal email *not* `hello@plugfile.com` for now — Stripe sends critical security alerts here. You can swap to `admin@plugfile.com` later via Cloudflare Email Routing. |
| Full name | Your full legal name as on your driver's license | Must match your tax records. |
| Country | United States | Determines Stripe legal entity. |
| Password | Strong, unique | Use a password manager. |

Click **Create account**, then verify the email.

---

## Step 2 — Verify your email

Open the email Stripe sent, click the verification link. Dashboard opens in
**test mode** (look for the orange "Test mode" toggle in the top-right).

You can build everything in test mode first. Activation for live payments
comes later.

---

## Step 3 — Two-factor authentication (do this now, not later)

**Path:** Settings → Team and Security → Two-step authentication

- Method: Authenticator app (Authy, 1Password, Google Authenticator)
- Do NOT use SMS — Stripe and your bank are top SIM-swap targets
- Save the recovery codes somewhere not on your phone

If you skip this, Stripe blocks API key creation in production accounts.

---

## Step 4 — Activate payments (when ready for real money)

**Path:** Settings → Account → Activate payments
*(or click the prompt at the top of the dashboard)*

You'll fill out three sections. Order matters — Stripe gates each on the
previous one.

### 4a. Business details

| Field | Value | Why |
|---|---|---|
| Business type | **Individual / Sole proprietor** | Pre-LLC. Switch to LLC later via "Update entity type." |
| Industry | **Software / SaaS** → Sub-category: "Computer software / consulting" | Sets your MCC (merchant category code) to standard SaaS. **Do not** pick "Oil and gas" — that's the MCC for fuel sellers and triggers extra underwriting. |
| Product description | *(paste exactly the paragraph below)* | This is read by Stripe's underwriting team. Specific + factual = faster approval. |
| Business website | `https://plugfile.com` | If your live site isn't up, paste the GitHub repo URL `https://github.com/meencoder/PlugFile`. |
| Average transaction amount | `$1` initially, $299 once subscriptions launch | Stripe uses this for fraud-rule defaults. Underestimating triggers reviews; overestimating raises your reserve. |
| Average monthly volume | $0–$5,000 initially | Honest answer; you can update this anytime. |

**Product description — paste this verbatim:**

> Plugfile is B2B compliance-automation software for Texas oil-and-gas operators. We help them prepare Form W-3 (the Texas Railroad Commission's well-plugging record): cement-volume calculations validated against state regulation TAC §3.14, automatic data fill from public RRC well-master and operator records, and a drafted surface-restoration narrative built from the operator's own voice memo. Today we are charging a $1 refundable deposit that reserves early-access pricing for our launch-tier subscription ($299/month for Compliance Core, $499/month for Compliance Suite). The recurring product launches Q3 2026; deposits are fully refundable until then. Customers are independent oil-and-gas producers, plugging contractors, and compliance managers in Texas.

### 4b. Personal details (sole prop = Stripe verifies you, not a company)

| Field | Value | Notes |
|---|---|---|
| Legal name | Your full legal name | Must match driver's license + SSN. |
| Date of birth | DOB on your DL | |
| Home address | Your residential address | NOT a P.O. box, NOT your work address. Stripe's KYC requires identity-verified residential. |
| Phone | Personal mobile | For 2FA fallback and Stripe support. |
| SSN | Last 4 digits | Stripe verifies against tax records. The first time you take >$600/year, Stripe issues a 1099-K under this SSN. |

Stripe checks this against public records in ~30 seconds. If it fails, they
ask for a driver's license photo upload. Have it ready.

### 4c. Bank account

| Field | Value | Notes |
|---|---|---|
| Account holder | Your legal name | Must match Step 4b above |
| Routing number | 9-digit ABA number | Bottom-left corner of a check |
| Account number | Your account number | NOT your debit card number |
| Account type | Checking | Stripe doesn't payout to savings on most US banks |

If Plaid is available for your bank: instant verification (sign in with bank
credentials in a popup). Otherwise: micro-deposit verification, 1–2 business
days, two small deposits land in your account that you confirm in Stripe.

**Recommendation:** open a separate **Mercury** ($0/mo) or **Relay**
($0/mo) business checking before linking. Keeps Plugfile revenue separate
from personal cash, makes future LLC migration cleaner. If that's too much
friction now, your personal checking is fine.

---

## Step 5 — Business profile + branding (one-time polish)

**Path:** Settings → Business

| Field | Value |
|---|---|
| Public business name | `Plugfile` |
| Doing-business-as (DBA) | `Plugfile` |
| Statement descriptor | `KAPROQ COMPLIANCE` (18 chars; max 22) |
| Shortened descriptor | `KAPROQ*` |
| Customer support email | `hello@plugfile.com` |
| Customer support phone | optional; leave blank or use Google Voice |
| Customer support address | your home address (required field) |

**Path:** Settings → Branding

| Field | Value |
|---|---|
| Logo | Upload `branding/plugfile_logo.svg` |
| Icon | Upload `branding/plugfile_mark.svg` |
| Brand color | `#D97706` (amber accent) |
| Accent color | `#1F2937` (charcoal) |

These show on the Stripe-hosted checkout page. With them set, the Reserve
checkout looks like *your* brand, not Stripe's default.

---

## Step 6 — Get the API key

**Path:** Developers → API keys

You'll see four keys:

| Key | Prefix | What it does |
|---|---|---|
| Test publishable | `pk_test_...` | Safe to put in client code; test mode only |
| Test secret | `sk_test_...` | What you give the script for testing |
| Live publishable | `pk_live_...` | Safe to put in client code; live mode |
| Live secret | `sk_live_...` | What you give the script for live payments |

**For the automation script, you want the SECRET key.** Click "Reveal test
key" or "Reveal live key" — Stripe shows it once, then masks it.

```powershell
# Copy the key, then in PowerShell:
$env:STRIPE_API_KEY = "sk_test_51H...your_actual_key_here"

# Run the automation:
python tools\stripe_setup.py --dry-run    # preview
python tools\stripe_setup.py              # apply
```

The script handles Product, Price, Payment Link, HTML patching, and deploy.

---

## Step 7 — Email customization (optional but high-leverage)

**Path:** Settings → Emails

| Email | What to customize |
|---|---|
| Successful payment receipt | Reply-to: `hello@plugfile.com`. Add a one-line "What happens next" footer linking back to `https://plugfile.com`. |
| Refund issued | Reply-to: `refund@plugfile.com`. Add: "Thanks for trying Plugfile. If there's anything we should improve, hit reply." |
| Failed payment | Default is fine for now. |

Stripe sends these automatically on every transaction. Customizing builds
trust and gives you a feedback channel on refunds.

---

## Step 8 — Test the full flow before going live

In **test mode** (your env var is `sk_test_...`):

1. Run `python tools/stripe_setup.py` — script creates Product / Price / Payment Link.
2. Open the printed Payment Link URL in a browser.
3. Use test card `4242 4242 4242 4242`, any future expiry, any 3-digit CVC, any ZIP.
4. Complete checkout, verify the confirmation page shows your message.
5. Check Stripe dashboard → Payments — you should see a $1.00 charge with the email you used.
6. Issue a refund manually in the dashboard to test the refund path.
7. Confirm the refund email lands in your inbox.

---

## Step 9 — Switch to live mode

Once test mode works end-to-end:

1. Top-right toggle → switch from "Test mode" to "Live mode."
2. Developers → API keys → reveal **live** secret key (`sk_live_...`).
3. Update your env var: `$env:STRIPE_API_KEY = "sk_live_..."`
4. Re-run `python tools/stripe_setup.py` — script creates the live-mode
   Product / Price / Payment Link (separate from your test ones).
5. The HTML files now point at the live Payment Link.
6. Real cards work; real $1 deposits land in your bank ~2 business days later.

---

## Common gotchas

- **Statement descriptor** can't be changed for 14 days after first use. Pick `KAPROQ COMPLIANCE` carefully — typo fix requires waiting two weeks.
- **Refunds cost the Stripe processing fee** (you don't get back the 2.9% + $0.30). On a $1 deposit refund, you eat $0.33. At 100 refunds, that's $33 — small enough to ignore but worth knowing.
- **Stripe holds an initial reserve** on new accounts (typically 5-10% of volume for 90 days). Your first ~$50 of deposits may not appear in your bank for 90 days. Documented behavior, not a bug.
- **The `submit_type=book` flag** in the Payment Link makes Stripe's button say "Reserve" instead of "Pay" — set automatically by `stripe_setup.py`. If you ever recreate the link via the dashboard manually, set this option in Advanced settings.
- **Test-mode and live-mode are completely separate.** Products, prices, payment links, and customers in test mode don't exist in live mode. You'll create everything twice (once via the script in test, once again in live).

---

## Files referenced in this guide

- `tools/stripe_setup.py` — automation script for Product / Price / Payment Link / HTML patching
- `branding/plugfile_logo.svg` — full lockup with wordmark, for Stripe Branding → Logo
- `branding/plugfile_mark.svg` — square mark only, for Stripe Branding → Icon
- `landing/index.html`, `landing/for-engineers.html` — auto-patched by the script with the real Payment Link URL

# Plugfile — Client Pitch Deck
### External / Operator-Facing Presentation

---

## SLIDE 1 — The Hook

**Headline:**
# The W-3 form costs you more than you think.

**Visual:** Split screen — left side: a stressed field operator at a desk with a paper form, stack of files, coffee cup at midnight. Right side: same person on a phone at the wellsite, PDF downloads, done.

**Speaker note / talking point:**
> "Every time you plug a well, you owe the Railroad Commission a Form W-3. Most operators treat it as a back-office chore. We're going to show you what it's actually costing — and how to fix it in 5 minutes."

---

## SLIDE 2 — The Problem: By the Numbers

**Headline:** Plugging a well takes days. The paperwork takes longer than it should.

| The Reality | The Number |
|-------------|-----------|
| Time to complete one W-3 manually | **45 min – 3 hours** |
| RRC penalty for late filing | **Up to $10,000/day** |
| Wells plugged in Texas per year | **4,000 – 6,000** |
| Most common W-3 error | **Wrong BUQW depth from GAU letter** |
| Result of a wrong BUQW depth | **NOV + potential re-plug requirement** |

**The hidden cost:**
> A P&A contractor doing 15 wells a month spends **30–45 hours per month** on W-3 paperwork alone. That's nearly a full work-week — every month — on form-filling.

---

## SLIDE 3 — How It Works Today (The Pain)

**Headline:** Five steps. All manual. All at the wrong time.

**Visual:** Linear process diagram with pain points annotated

```
[Wellsite]          [Drive Back]         [Office]              [District Office]
    |                    |                   |                       |
Finish plug         45-min commute       Find paper form         Drive/mail
    |                    |                   |                       |
No cell service     GAU letter            Look up API #          File in duplicate
                    where is it?          by hand                within 30 days
                         |                   |
                    Call the office       Write Section IX
                    to ask for depth      narrative by hand
```

**Pain points highlighted:**
- ❌ GAU letter is often lost, faxed, or buried in email
- ❌ Well data has to be looked up manually from RRC records
- ❌ Surface restoration narrative is unstructured — every plugger writes it differently
- ❌ Errors aren't caught until RRC flags them — sometimes months later

---

## SLIDE 4 — Introducing Plugfile

**Headline:**
# From wellsite to print-ready W-3 in 5 minutes.

**The one-liner:**
> Plugfile is a mobile web app that auto-fills your RRC Form W-3 using your API number, your GAU letter, and a 90-second voice recording — then generates a print-ready PDF.

**No app store. No login complexity. Works on any smartphone.**

**Visual:** Phone mockup showing the 5-step wizard UI

---

## SLIDE 5 — Product Demo: Live Walkthrough

### Step 1: Enter Your API Number
**Visual:** Step 1 screen — API number input field

> Type your well's API number. Plugfile pulls your operator name, lease, legal description, total depth, and RRC district directly from RRC records.
>
> **No manual data entry. No typos on field names.**

---

### Step 2: Upload Your GAU Letter
**Visual:** Step 2 screen — PDF upload + BUQW result card

> Upload your Groundwater Advisory Unit letter — the one that tells you the BUQW depth you must protect.
>
> Plugfile reads it automatically. Scanned image? No problem — AI reads it.
>
> **Result:** BUQW depth and GAU reference number extracted in seconds.
>
> No more hunting through emails. No more calling the office.

---

### Step 3: Describe the Work — By Voice
**Visual:** Step 3 screen — microphone button active, transcript appearing

> Tap the mic. Talk for 60–90 seconds like you're describing the job to your company man:
>
> *"Cut surface casing at 3 feet below grade. Welded a 10-inch steel plate to seal the wellbore. Pulled the pump jack, tanks, and flow lines. Graded the location and seeded with native grass. Surface owner John Smith was on-site and gave his consent. Work was completed May 15th."*
>
> That's it. No forms. No typing. No remembering which field goes where.

---

### Step 4: Review — AI Does the Work
**Visual:** Step 4 screen — all 8 slot cards green, narrative populated

> Eight fields auto-populated:
>
> ✅ Casing cut depth: 3 ft
> ✅ Cap type: steel plate (10-inch)
> ✅ Cellar filled: Yes
> ✅ Equipment removed: pump jack, tank battery, flow lines
> ✅ Vegetation: native grass
> ✅ Grading: level
> ✅ Date of work: 2026-05-15
> ✅ Surface owner consent: John Smith was present and gave consent
>
> Section IX narrative — written, regulatory-language, ready to file.
>
> **Edit anything you want. You stay in control.**

---

### Step 5: Download Your W-3
**Visual:** Step 5 screen — download button + preview of completed W-3 PDF

> One tap. Your W-3 is pre-filled, formatted, and ready to print.
>
> Page 1: All well data, cementing grid, casing record, your signature.
> Page 2: BUQW depth, GAU reference, full surface restoration narrative.
>
> **Print it. Sign it. Walk it to the District Office. Done.**
>
> Total time: **5–8 minutes.**

---

## SLIDE 6 — Before and After

| | Before Plugfile | With Plugfile |
|--|----------------|---------------|
| **Time per W-3** | 45 min – 3 hours | 5–8 minutes |
| **GAU letter** | Hunt through email/files | Upload once, auto-extracted |
| **Well data** | Typed by hand | Auto-filled from RRC |
| **Section IX** | Written from scratch each time | Voice → structured narrative |
| **Error risk** | Wrong depth, wrong API, wrong county | Pre-validated against RRC records |
| **Where you use it** | Desk, office, after the fact | Wellsite, on your phone, right now |
| **Filing deadline risk** | "I'll do it this week" | Done before you leave the location |

---

## SLIDE 7 — Who Is This For?

### P&A Contractors
> You plug 10–30 wells a month. Every one needs a W-3. Your guys are doing paperwork on the drive home or at 10pm.
>
> Plugfile gives each field man the tool to close out the paperwork at the wellsite — before they drive away.

### Independent Operators (Self-Plugging)
> You're the one who signs the W-3. You're the one who gets the NOV if it's wrong.
>
> Plugfile puts the right data in every field, every time — and you can review it on your phone before you sign.

### Environmental / Compliance Consultants
> You file W-3s for multiple clients. Every operator has different GAU letters, different well histories.
>
> Plugfile handles the research layer so you can spend your time on judgment, not data entry.

---

## SLIDE 8 — The Regulatory Reality

**Why this matters more than ever:**

- RRC is actively increasing enforcement on plugging compliance under the Texas Idle Well program
- The Groundwater Advisory Unit is issuing more Form GW-2 determinations for older wells
- Surface restoration requirements (Section IX) are being scrutinized more closely in districts with active P&A activity
- New P&A bonds and financial assurance rules are increasing operator accountability

**The risk of doing nothing:**
> A single NOV for an incorrectly filed W-3 can exceed **$50,000** in penalties and legal fees — plus the cost of re-plugging if the groundwater protection depth was wrong.

**Plugfile is compliance insurance — at a fraction of the cost.**

---

## SLIDE 9 — Pricing

**Simple. Two tiers.**

### Free — Try It Now
- Full 5-step wizard
- AI-powered GAU letter parsing
- Voice transcript → Section IX narrative
- W-3 PDF with DRAFT watermark
- No credit card required

**Use it on your next job. See if it works.**

### Paid — File-Ready Output
- Everything in Free, plus:
- Clean PDF — no watermark, ready to file with RRC
- Audit trail page: every field sourced and documented
- Priority support

**[Pricing available on request — Founders early access pricing available now]**

---

## SLIDE 10 — Why Plugfile. Why Now.

**Three things aligned:**

**1. The technology is ready**
AI that reads scanned PDFs, understands spoken descriptions of oil field work, and formats regulatory language correctly — this did not exist reliably two years ago.

**2. The regulatory pressure is increasing**
RRC enforcement activity on plugging compliance has intensified. The cost of a bad W-3 is going up, not down.

**3. The form is still paper**
RRC does not accept e-filing for the W-3. It must be walked into the District Office. Plugfile does not try to disrupt that process — it makes the preparation of that paper form faster, more accurate, and possible at the wellsite instead of the back office.

> We're not disrupting the RRC. We're making sure you don't show up with the wrong form.

---

## SLIDE 11 — Validation

**What we've heard from operators:**

> *"The GAU letter piece alone would save us two hours per well. We have four guys who each plug 8–10 wells a month."*

> *"I had an NOV because the wrong BUQW depth was on a W-3. Cost me $18,000 to fix. If this had existed then I would have caught it."*

> *"My guys fill out the W-3 at the end of the day. They're tired. They make mistakes. A voice tool they can use at the wellsite changes everything."*

**Current status:**
- Live and parsing real RRC GAU letters
- W-3 output validated against RRC filing requirements
- Founders pricing available for early operators and P&A contractors

---

## SLIDE 12 — Get Started Today

**Three ways in:**

### 1. Try the free demo right now
> `plugfile.onrender.com` — no download, no account
> Run through your next well's W-3 in 5 minutes

### 2. Book a 20-minute live demo
> We'll use your actual API number and a real GAU letter
> You'll see your own well data populated in the form

### 3. Founders Access
> Early operators and P&A contractors get founders pricing + direct input on the product roadmap
> Contact: [founder contact info]

---

**Plugfile**
*Print-ready W-3s from the wellsite.*

`plugfile.onrender.com`

---

## APPENDIX A — Product Screenshots Reference

**For live demos, navigate to:** `https://plugfile.onrender.com`

| Screen | URL / Step | Key talking point |
|--------|-----------|------------------|
| Step 1 — Well Lookup | Step 1, type any TX API | "Pulls straight from RRC — no manual entry" |
| Step 2 — GAU Upload | Upload Wildman.pdf or any GAU letter | "Even reads scanned letters" |
| Step 3 — Voice | Tap mic, say 60-second description | "This replaces 45 minutes of form-filling" |
| Step 4 — Review | Show green cards + narrative | "All 8 fields, AI-populated, fully editable" |
| Step 5 — Download | Show W-3 PDF | "Print and file — this is the actual form" |

---

## APPENDIX B — Regulatory Reference

| Regulation | Requirement |
|-----------|------------|
| TAC §3.14 | Groundwater protection during plugging — BUQW compliance |
| TAC §91.103 | W-3 must be filed within 30 days of plugging |
| 16 TAC §3.14(c) | General plugging requirements when surface casing covers BUQW |
| 16 TAC §3.14(d) | Special plugging requirements when surface casing does NOT cover BUQW |
| RRC Form W-3 | Rev. 08/2019 — current required form |
| RRC Form GW-2 | GAU Groundwater Protection Determination — issued per well |

---

## APPENDIX C — FAQ

**Q: Does Plugfile e-file with RRC?**
A: No — RRC does not accept e-filing for Form W-3. You still print and walk it to the District Office. Plugfile makes the preparation accurate and fast.

**Q: What if my GAU letter is a scanned image?**
A: Plugfile reads scanned letters using AI vision — it handles even poor-quality scans.

**Q: Can I edit the fields after the AI fills them?**
A: Yes. Every field is editable before you generate the PDF. You stay in control.

**Q: What if I don't have my API number?**
A: You can enter it manually or skip the lookup and proceed with just the GAU letter and voice transcript.

**Q: Does it work offline / at the wellsite with no signal?**
A: The app needs signal to process the GAU letter and transcript. Most operators complete this on the drive back or once they hit cell coverage. Works on any smartphone browser.

**Q: Is my data stored?**
A: [Data retention policy — confirm with founder before presenting]

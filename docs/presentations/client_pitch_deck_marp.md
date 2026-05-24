---
marp: true
theme: default
paginate: true
style: |
  section {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    background: #0f172a;
    color: #f1f5f9;
  }
  section.title {
    background: linear-gradient(135deg, #0f172a 60%, #1e3a5f);
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: flex-start;
    padding: 60px;
  }
  h1 { color: #3b82f6; font-size: 2.2rem; }
  h2 { color: #60a5fa; font-size: 1.4rem; border-bottom: 2px solid #3b82f6; padding-bottom: 6px; }
  h3 { color: #93c5fd; font-size: 1.1rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
  th { background: #1e3a5f; color: #93c5fd; padding: 6px 10px; }
  td { padding: 5px 10px; border-bottom: 1px solid #1e293b; }
  tr:nth-child(even) td { background: #1e293b; }
  code { background: #1e293b; color: #34d399; padding: 2px 6px; border-radius: 4px; font-size: 0.85rem; }
  pre { background: #1e293b; padding: 14px; border-radius: 8px; font-size: 0.78rem; }
  blockquote { border-left: 4px solid #3b82f6; padding-left: 16px; color: #94a3b8; font-style: italic; margin: 12px 0; }
  .big { font-size: 2.8rem; font-weight: 700; color: #3b82f6; }
  .green { color: #22c55e; }
  .red { color: #ef4444; }
  .muted { color: #94a3b8; font-size: 0.85rem; }
---

<!-- _class: title -->

# Plugfile

## From wellsite to print-ready W-3 in 5 minutes.

*The smarter way to file your RRC Plugging Record*

`plugfile.com`

---

# The W-3 Form Costs You More Than You Think

**Every time you plug a well, you owe the RRC a Form W-3.**
Most operators treat it as a back-office chore.

Here's what it's actually costing:

| The Reality | The Number |
|-------------|-----------|
| Time to complete one W-3 manually | **45 min – 3 hours** |
| RRC penalty for late filing | **Up to $10,000/day** |
| Most common W-3 error | **Wrong BUQW depth from GAU letter** |
| Cost to resolve a single NOV | **$18,000 – $50,000** |

> A P&A contractor doing 15 wells/month spends **30–45 hours on paperwork alone** — nearly a full work week, every month.

---

# How It Works Today

```
  Wellsite          Drive back         Office              District Office
     │                  │                 │                      │
  Finish plug       45-min commute    Pull paper form       Drive or mail
     │                  │                 │                      │
  No cell signal    GAU letter?       Look up API #         File in duplicate
                    Where is it?      by hand               within 30 days
                         │                │
                    Call the office   Write Section IX
                    to ask for depth  narrative by hand
```

- ❌ GAU letter is lost, buried in email, or faxed
- ❌ Well data typed by hand from memory or RRC printouts
- ❌ Surface restoration narrative written differently every time
- ❌ Errors caught months later when RRC calls

---

# Introducing Plugfile

## From wellsite to print-ready W-3 in 5 minutes.

> Plugfile is a mobile web app that auto-fills your RRC Form W-3 using your API number, your GAU letter, and a 90-second voice recording — then generates a print-ready PDF.

**No app download. No login. Works on any smartphone.**

| What you bring | What Plugfile does |
|---------------|-------------------|
| API number | Pulls all well data from RRC automatically |
| GAU letter (PDF or scan) | Extracts BUQW depth + GAU reference |
| 90-second voice recording | Populates all 8 Section IX fields |
| Your name | Generates signed, print-ready W-3 |

---

# Demo — Step 1: Enter Your API Number

## `plugfile.com → Step 1`

Type your well's API number. Plugfile pulls:

- ✅ Operator name and address
- ✅ Lease name and well number
- ✅ Legal description (section, block, survey)
- ✅ Total depth
- ✅ RRC district
- ✅ Spud and completion dates

**No manual data entry. No typos on field names.**

> *"It pulled everything. I didn't type a single field."*

---

# Demo — Step 2: Upload Your GAU Letter

## `plugfile.com → Step 2`

Upload your Groundwater Advisory Unit letter.

**Plugfile reads it automatically — including scanned images.**

Extracted in seconds:
- ✅ **BUQW depth** (Base of Usable Quality Water)
- ✅ **GAU reference number**
- ✅ Letter type (standard vs. special-case requirements)

**No more hunting through emails.**
**No more calling the office to ask for the depth.**

> *"The GAU letter piece alone saves us 2 hours per well."*

---

# Demo — Step 3: Describe the Work — By Voice

## `plugfile.com → Step 3`

Tap the mic. Talk for 60–90 seconds:

> *"Cut surface casing at 3 feet below grade. Welded a 10-inch steel plate to seal the wellbore. Pulled the pump jack, tanks, and flow lines. Graded the location and seeded with native grass. Surface owner John Smith was on-site and gave consent. Work completed May 15th."*

**That's it.**

No forms. No typing. No remembering which field goes where.

---

# Demo — Step 4: AI Does the Work

## `plugfile.com → Step 4`

Eight fields auto-populated from your voice:

| Field | Extracted Value |
|-------|----------------|
| ✅ Casing cut depth | 3 ft below ground level |
| ✅ Cap type | 10-inch steel plate |
| ✅ Cellar filled | Yes |
| ✅ Equipment removed | pump jack, tank battery, flow lines |
| ✅ Vegetation | native grass (seeded) |
| ✅ Grading | level |
| ✅ Date of work | 2026-05-15 |
| ✅ Surface owner consent | John Smith present, consent given |

**Section IX narrative — written, regulatory-language, ready to file.**
*Edit anything you want. You stay in control.*

---

# Demo — Step 5: Download Your W-3

## `plugfile.com → Step 5`

One tap. Your W-3 is pre-filled, formatted, and ready to print.

**Page 1:** All well data · Cementing grid · Casing record · Signature block

**Page 2:** BUQW depth · GAU reference · Full surface restoration narrative

---

**Print it. Sign it. Walk it to the District Office. Done.**

Total time: **5–8 minutes.**

---

# Before and After

| | ❌ Before Plugfile | ✅ With Plugfile |
|--|-------------------|----------------|
| **Time per W-3** | 45 min – 3 hours | **5–8 minutes** |
| **GAU letter** | Hunt through email | Upload once, auto-extracted |
| **Well data** | Typed by hand | Auto-filled from RRC |
| **Section IX** | Written from scratch | Voice → structured narrative |
| **Error risk** | Wrong depth, wrong county | Pre-validated against RRC |
| **Where you use it** | Desk, after the fact | **Wellsite, on your phone** |
| **Filing deadline risk** | "I'll do it this week" | Done before you drive away |

---

# Who Is This For?

### P&A Contractors
You plug 10–30 wells a month. Every job needs a W-3. Your guys are doing paperwork at 10pm.
Plugfile closes out the paperwork **at the wellsite, before they drive away.**

### Independent Operators
You sign the W-3. You get the NOV if it's wrong.
Plugfile puts the right data in every field — and you review it on your phone before you sign.

### Environmental / Compliance Consultants
You file W-3s for multiple clients. Every operator has different GAU letters.
Plugfile handles the research layer so you spend your time on **judgment, not data entry.**

---

# The Regulatory Reality

**Why this matters more than ever:**

- RRC is actively increasing enforcement under the **Texas Idle Well program**
- The GAU unit is issuing more **Form GW-2 determinations** for older wells
- Section IX surface restoration requirements are under **greater scrutiny** in active P&A districts
- New P&A bonds and financial assurance rules are increasing **operator accountability**

**The risk of doing nothing:**

> A single NOV for an incorrectly filed W-3 can exceed **$50,000** in penalties and legal fees — plus the cost of re-plugging if the BUQW depth was wrong.

**Plugfile is compliance insurance — at a fraction of the cost.**

---

# Pricing

## Simple. Two tiers.

| | **Free** | **Paid** |
|--|---------|---------|
| 5-step wizard | ✅ | ✅ |
| GAU letter parsing | ✅ | ✅ |
| Voice → Section IX | ✅ | ✅ |
| W-3 PDF output | DRAFT watermark | ✅ Clean, file-ready |
| Audit trail page | ❌ | ✅ |
| Priority support | ❌ | ✅ |
| **Price** | **$0** | **Founders pricing available** |

*No credit card required to start.*

---

# Why Plugfile. Why Now.

**Three things aligned:**

**1. The technology is ready**
AI that reads scanned PDFs, understands oil field voice descriptions, and formats regulatory language — this did not exist reliably two years ago.

**2. Regulatory pressure is increasing**
RRC enforcement on plugging compliance has intensified. The cost of a bad W-3 is going up, not down.

**3. The form is still paper**
RRC does not accept e-filing for the W-3. It must be walked into the District Office.

> We're not disrupting the RRC.
> We're making sure you don't show up with the wrong form.

---

# What Operators Are Saying

> *"The GAU letter piece alone would save us two hours per well. We have four guys who each plug 8–10 wells a month."*

> *"I had an NOV because the wrong BUQW depth was on a W-3. Cost me $18,000 to fix. If this had existed then I would have caught it."*

> *"My guys fill out the W-3 at the end of the day. They're tired. They make mistakes. A voice tool they can use at the wellsite changes everything."*

**Current status:**
- ✅ Live and parsing real RRC GAU letters
- ✅ W-3 output validated against RRC filing requirements
- ✅ Founders pricing available now

---

# Get Started Today

## Three ways in:

**1. Try the free demo right now — no login**
`plugfile.com`
Run through your next well's W-3 in 5 minutes

**2. Book a 20-minute live demo**
We'll use your actual API number and a real GAU letter
You'll see your own well data in the form

**3. Founders Access**
Early operators and P&A contractors get founders pricing
+ direct input on the product roadmap

---

<!-- _class: title -->

# Plugfile

## *Print-ready W-3s from the wellsite.*

`plugfile.com`

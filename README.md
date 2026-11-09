# Auto Intern Apply & Alert Bot 🚀

An automated multi-platform tech internship tracker and auto-application assistant that monitors thousands of internship openings across major platforms, filters for target roles (AI/ML, Fullstack, Backend, and SWE), enforces location rules (India or Remote) and minimum stipend thresholds (≥ ₹10,000/mo), dispatches rich embed digests directly to Discord, and assists with one-click ATS applications.

---

## 🎯 Target Domains
* **AI & Machine Learning**: AI Engineer, Machine Learning, Deep Learning, NLP, Computer Vision, LLM / Generative AI
* **Backend Development**: Backend Engineer, Distributed Systems, Cloud / Platform Services
* **Fullstack Development**: Fullstack Engineer, Web Applications
* **Software Engineering**: General SWE / SDE Internships

---

## 📡 Data Sources & Aggregation
* **RapidAPI JSearch (`/search-v2`)**: Live real-time index covering **LinkedIn India, Indeed, Internshala, Naukri.com, Glassdoor, and Wellfound (AngelList)**.
* **SimplifyJobs Verified Feeds**: Community-driven real-time tracking across 35,000+ postings directly from company ATS platforms (**Greenhouse, Lever, SmartRecruiters, Workday, Ashby**).
* **Arbeitnow**: European and worldwide remote tech job board feeds.

---

## 🔍 Smart Filtering & Distribution
* **Strict Location Filter**: Rejects on-site and hybrid roles located outside India (e.g. US, Canada, UK, Europe). Keeps physical locations in India (Bengaluru, Hyderabad, Delhi/NCR, Pune, Mumbai, etc.) and 100% Remote / Work from Home roles.
* **Stipend Threshold (≥ ₹10,000/mo)**: Checks descriptions and structured pay from every source. Blocks explicit unpaid and known low-pay internships, using the lower bound of salary ranges. Preserves undisclosed pay. Foreign currencies require a configured conversion rate to verify the INR threshold; otherwise alerts retain the currency and say the threshold is unverified.
* **Balanced Quota (30 Total / 15 India)**: Dispatches 30 curated daily openings with a dedicated priority quota of at least 15 physical Indian openings, complemented with worldwide Remote openings.
* **Deduplication Engine**: Uses requisition IDs and normalized URLs in `seen_jobs.json`. Separate vacancies with the same company/title remain eligible. State is saved after each confirmed Discord message; failed deliveries and console previews remain eligible for the next run. A network timeout after Discord accepts a message can still cause a duplicate on retry.
* **Internship Filter**: Requires an internship/working-student title or structured internship employment type, and excludes senior roles. JSearch runs all five domain queries on each run.
* **Posting Age Filter**: Includes jobs posted within the last six calendar months by default, including the cutoff day, based on IST. For example, a November 9 run accepts May 9 through November 9. Set `max_posting_age_months` in `config.json` to adjust the window (an integer from 1 to 120). Existing configurations without this setting use six months automatically. Missing, invalid, and future dates are skipped. The original posting date is used; editing a listing does not refresh its age. Discord cards show the posting date.

---

## 🛠️ Setup & Configuration

### 1. Configure Credentials
Copy the template configuration:
```bash
cp config.example.json config.json
```
Edit `config.json` with your credentials:
```json
{
  "discord_webhook_url": "https://discord.com/api/webhooks/your/webhook/url",
  "rapidapi_key": "YOUR_RAPIDAPI_KEY",
  "min_stipend": 10000,
  "max_alerts_per_run": 30,
  "min_indian_alerts": 15,
  "max_posting_age_months": 6,
  "currency_to_inr": {"INR": 1}
}
```

Optional `currency_to_inr` entries specify INR per unit of foreign currency. Supply and maintain your own rates for currencies you want checked. Structured pay with no currency or pay period is retained with an unverified label. Bare amounts in Indian descriptions are treated as INR/month unless a different currency or period is stated. Hourly, daily, and weekly equivalents use 160 hours/month, 20 days/month, and 52 weeks/year.

### 2. Configure Applicant Profile
Copy the profile template:
```bash
cp profile.example.json profile.json
```
Edit `profile.json` with your details (name, email, phone, college, LinkedIn, GitHub, portfolio). Place your PDF resume in the root directory as `resume.pdf`.

*(Note: `config.json`, `profile.json`, and `*.pdf` are strictly ignored by `.gitignore` to prevent secret or credential leaks).*

---

## 🚀 Usage

### 1. Run the Tracker
```bash
python tracker.py
```
Dispatches rich color-coded cards directly to your Discord channel with direct application links.

Without a webhook, the tracker displays a preview and leaves seen-state unchanged. A partial or total delivery failure exits with a nonzero status, while successful batches remain saved. GitHub Actions persists those checkpoints even when the tracker fails and serializes runs to avoid overlapping state updates.

### 2. Auto-Apply to Openings
When you find an opening you want to apply for, use the auto-apply engine:

**Assisted Review Mode (Recommended):**
```bash
python auto_apply.py "https://jobs.lever.co/company-name/job-id/apply"
```
Opens your browser, fills supported contact and link fields, attempts to attach `resume.pdf`, and waits for you to review and submit.

Prefilling is best effort and depends on the form. Review missing fields and custom questions manually; the bot does not guess work authorization or answer every radio question with “Yes.”

`--mode auto` attempts submission on Lever and Greenhouse only after contact details and resume filling succeed and native form validation passes. It reports success only after a visible application receipt appears. Failed or unconfirmed attempts leave the browser open for review until you press Enter. Ashby and generic forms fall back to assisted review.

`--mode headless` supports Lever and Greenhouse only. Unsupported ATS forms or unconfirmed submissions exit with a nonzero status. Automatic mode also exits nonzero if automatic submission was not confirmed, including after a manual handoff. A missing receipt does not prove the application failed: check the employer's confirmation before retrying.

**Interactive Mode:**
```bash
python auto_apply.py
```

---

## ⏰ Automated Scheduling
This project is configured to run automatically using **Google Antigravity Scheduled Automations** (`/automation`) or via cron / GitHub Actions on a daily cadence (e.g. 9:00 AM IST).

## Regression Tests

Install dependencies, then run:

```bash
python -m unittest discover -s tests -v
```

Tests use mocked network and browser objects. They do not send alerts, read your profile, upload your resume, or submit applications. The GitHub Actions workflow runs them before the tracker.

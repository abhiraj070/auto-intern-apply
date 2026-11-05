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
* **Stipend Threshold (≥ ₹10,000/mo)**: Blocks unpaid, volunteer, and low-stipend internships (< ₹10,000/mo). Preserves competitive / undisclosed corporate postings.
* **Balanced Quota (30 Total / 15 India)**: Dispatches 30 curated daily openings with a dedicated priority quota of at least 15 physical Indian openings, complemented with worldwide Remote openings.
* **Deduplication Engine**: Uses local persistent state (`seen_jobs.json`) to guarantee zero duplicate notifications across daily runs.

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
  "min_indian_alerts": 15
}
```

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

### 2. Auto-Apply to Openings
When you find an opening you want to apply for, use the auto-apply engine:

**Assisted Review Mode (Recommended):**
```bash
python auto_apply.py "https://jobs.lever.co/company-name/job-id/apply"
```
Opens your browser, pre-fills your contact details, education, and links in ~2 seconds, attaches `resume.pdf`, and lets you submit with 1 click.

**Interactive Mode:**
```bash
python auto_apply.py
```

---

## ⏰ Automated Scheduling
This project is configured to run automatically using **Google Antigravity Scheduled Automations** (`/automation`) or via cron / GitHub Actions on a daily cadence (e.g. 9:00 AM IST).

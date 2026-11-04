# Auto Intern Apply & Alert Bot 🚀

An automated multi-platform tech internship tracker that monitors thousands of internship openings, filters for target roles (AI/ML, Fullstack, Backend, and SWE), deduplicates previously seen roles, and dispatches rich embed notifications directly to Discord.

---

## 🎯 Target Roles
* **AI & Machine Learning**: AI Engineer, Machine Learning, Deep Learning, NLP, Computer Vision, LLM / Generative AI
* **Backend Development**: Backend Engineer, Distributed Systems, Cloud / Platform Services
* **Fullstack Development**: Fullstack Engineer, Web Applications
* **Software Engineering**: General SWE / SDE Internships

---

## 📡 Data Sources
* **Curated Repositories**: Community trackers (e.g. SimplifyJobs Summer 2025 & Summer 2026 listings) aggregating verified ATS openings (Greenhouse, Lever, SmartRecruiters, Workday).
* **Job Board Feeds**: Arbeitnow and external technical job board APIs.

---

## 🛠️ Setup & Usage

### 1. Configure Discord Webhook
Copy the template configuration:
```bash
cp config.example.json config.json
```
Edit `config.json` and insert your Discord Webhook URL:
```json
{
  "discord_webhook_url": "https://discord.com/api/webhooks/your/webhook/url"
}
```
*(Alternatively, set the `DISCORD_WEBHOOK_URL` environment variable).*

### 2. Run the Tracker
```bash
python tracker.py
```
* On first run, it fetches active openings and seeds `seen_jobs.json`.
* On subsequent runs, it only alerts for **new** openings posted since the last check.

---

## ⏰ Automated Scheduling
This project is configured to run automatically using **Google Antigravity Scheduled Automations** (`/automation`) or via cron / GitHub Actions on a daily cadence.

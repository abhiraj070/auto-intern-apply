"""
Internship Search & Discord Notifier
Targets: AI Engineering, Machine Learning, Fullstack Development, Backend Development, SWE internships.
Platforms: SimplifyJobs (ATS direct), Arbeitnow, and RapidAPI JSearch (LinkedIn, Indeed, Internshala, Glassdoor, etc.).
"""

import os
import sys
import json
import re
import time
import urllib.request
import urllib.parse
import urllib.error

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(SCRIPT_DIR, "seen_jobs.json")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")

# Keywords matching AI, Fullstack, Backend, and SWE internship roles
ROLE_KEYWORDS = [
    r"\bai\b",
    r"artificial intelligence",
    r"machine learning",
    r"\bml\b",
    r"deep learning",
    r"\bnlp\b",
    r"computer vision",
    r"\bllm\b",
    r"genai",
    r"fullstack",
    r"full[\s\-]stack",
    r"backend",
    r"back[\s\-]end",
    r"software engine(?:er|ering)",
    r"\bswe\b",
    r"\bsde\b",
    r"software developer",
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in ROLE_KEYWORDS]

# Negative keywords to filter out non-technical or unrelated roles
NEGATIVE_KEYWORDS = [
    "sales", "marketing", "recruiter", "hr ", "human resources", 
    "accountant", "finance intern", "legal intern", "hardware", "civil"
]


def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_seen(seen_ids):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_ids), f, indent=2)


def is_target_role(title):
    if not title:
        return False
    title_lower = title.lower()
    for neg in NEGATIVE_KEYWORDS:
        if neg in title_lower:
            return False
    return any(p.search(title_lower) for p in COMPILED_PATTERNS)


def fetch_simplify_listings(repo_name):
    url = f"https://raw.githubusercontent.com/SimplifyJobs/{repo_name}/dev/.github/scripts/listings.json"
    req = urllib.request.Request(url, headers={"User-Agent": "InternshipBot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except Exception as e:
        print(f"[!] Warning: failed to fetch {repo_name}: {e}")
        return []


def fetch_arbeitnow_listings():
    url = "https://www.arbeitnow.com/api/job-board-api"
    req = urllib.request.Request(url, headers={"User-Agent": "InternshipBot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            jobs = []
            for item in data.get("data", []):
                title = item.get("title", "")
                if "intern" in title.lower() or "junior" in title.lower() or "working student" in title.lower():
                    jobs.append({
                        "id": f"arbeitnow-{item.get('slug')}",
                        "company_name": item.get("company_name", "Unknown"),
                        "title": title,
                        "url": item.get("url", ""),
                        "locations": [item.get("location", "Remote" if item.get("remote") else "Various")],
                        "active": True,
                        "source": "Arbeitnow"
                    })
            return jobs
    except Exception as e:
        print(f"[!] Warning: failed to fetch Arbeitnow: {e}")
        return []


def fetch_jsearch_listings(rapidapi_key):
    """
    Fetches real-time tech internships from Google for Jobs / JSearch
    Aggregates LinkedIn, Indeed, Glassdoor, Internshala, Naukri, etc.
    """
    if not rapidapi_key or not rapidapi_key.strip() or rapidapi_key == "YOUR_RAPIDAPI_KEY_HERE":
        return []

    queries = [
        "Software Engineer intern India",
        "AI Machine Learning intern India",
        "Fullstack Developer intern India",
        "Backend Developer intern India"
    ]

    headers = {
        "X-RapidAPI-Key": rapidapi_key.strip(),
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    jobs = []
    print("[*] Querying RapidAPI JSearch (aggregates LinkedIn, Indeed, Internshala, Glassdoor)...")

    for q in queries[:2]:
        encoded_q = urllib.parse.quote(q)
        url = f"https://jsearch.p.rapidapi.com/search?query={encoded_q}&page=1&num_pages=1&employment_types=INTERN"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("data", []):
                    job_id = item.get("job_id", "")
                    title = item.get("job_title", "")
                    company = item.get("employer_name", "Unknown")
                    url_link = item.get("job_apply_link") or item.get("job_google_link") or ""
                    city = item.get("job_city") or ""
                    country = item.get("job_country") or "India"
                    location = f"{city}, {country}".strip(", ") if city else country
                    publisher = item.get("job_publisher") or "Job Board"

                    jobs.append({
                        "id": f"jsearch-{job_id}" if job_id else url_link,
                        "company_name": company,
                        "title": title,
                        "url": url_link,
                        "locations": [location],
                        "active": True,
                        "source": f"{publisher} (via JSearch)"
                    })
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            if "Endpoint" in err_body or e.code in (403, 404):
                print(f"[!] JSearch API Note (HTTP {e.code}): Please ensure you clicked 'Subscribe' on the Free Basic plan on RapidAPI's JSearch page.")
            else:
                print(f"[!] JSearch API Notice ({e.code}): {err_body[:100]}")
            break
        except Exception as e:
            print(f"[!] JSearch Exception: {e}")
            break

    print(f"[*] JSearch returned {len(jobs)} postings.")
    return jobs


def send_discord_webhook(webhook_url, embeds):
    """Sends embeds to a Discord webhook in chunks of 10."""
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "InternshipBot/1.0"
    }

    # Discord allows max 10 embeds per message
    for i in range(0, len(embeds), 10):
        chunk = embeds[i:i + 10]
        payload = {
            "content": "🚀 **New Internship Openings Found!**" if i == 0 else "",
            "embeds": chunk
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(webhook_url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                pass
            time.sleep(1)  # avoid rate limiting
        except urllib.error.HTTPError as e:
            print(f"[!] Discord Webhook HTTP Error: {e.code} - {e.read().decode('utf-8', errors='ignore')}")
        except Exception as e:
            print(f"[!] Error sending to Discord: {e}")


def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    rapidapi_key = os.environ.get("RAPIDAPI_KEY")

    # Also check config.json if available
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if not webhook_url and "discord_webhook_url" in cfg:
                    webhook_url = cfg["discord_webhook_url"]
                if not rapidapi_key and "rapidapi_key" in cfg:
                    rapidapi_key = cfg["rapidapi_key"]
        except Exception:
            pass

    seen_ids = load_seen()
    print(f"[*] Loaded {len(seen_ids)} previously seen jobs.")

    print("[*] Fetching listings from SimplifyJobs (Summer 2025 / Summer 2026)...")
    listings_2025 = fetch_simplify_listings("Summer2025-Internships")
    listings_2026 = fetch_simplify_listings("Summer2026-Internships")
    arbeitnow_jobs = fetch_arbeitnow_listings()
    jsearch_jobs = fetch_jsearch_listings(rapidapi_key)

    all_raw = listings_2025 + listings_2026 + arbeitnow_jobs + jsearch_jobs
    print(f"[*] Total raw listings gathered: {len(all_raw)}")

    new_matches = []
    
    for item in all_raw:
        job_id = str(item.get("id") or item.get("url") or "")
        if not job_id:
            continue

        if job_id in seen_ids:
            continue

        # Check if active
        if item.get("active") is False:
            continue

        title = item.get("title", "")
        if not is_target_role(title):
            continue

        company = item.get("company_name", "Unknown Company")
        url = item.get("url", "")
        locs = item.get("locations", [])
        loc_str = ", ".join(locs) if isinstance(locs, list) else str(locs or "Not specified")
        terms = item.get("terms", [])
        term_str = ", ".join(terms) if isinstance(terms, list) else str(terms or "")

        new_matches.append({
            "id": job_id,
            "company": company,
            "title": title,
            "url": url,
            "location": loc_str,
            "term": term_str,
            "source": item.get("source", "Simplify")
        })

    print(f"[*] Found {len(new_matches)} new matching internship openings.")

    if not new_matches:
        print("[OK] No new postings since last check. All caught up!")
        return

    # Prepare Discord embeds
    embeds = []
    for match in new_matches:
        # Determine color: purple for AI/ML, green for Fullstack/Backend/SWE
        t_lower = match["title"].lower()
        if any(k in t_lower for k in ["ai", "machine learning", "ml", "deep learning", "nlp", "llm", "genai"]):
            color = 0x9B59B6  # Purple
            role_type = "AI / Machine Learning"
        elif any(k in t_lower for k in ["backend", "back-end", "back end"]):
            color = 0x3498DB  # Blue
            role_type = "Backend Development"
        elif any(k in t_lower for k in ["fullstack", "full stack", "full-stack"]):
            color = 0x2ECC71  # Green
            role_type = "Fullstack Development"
        else:
            color = 0x1ABC9C  # Teal
            role_type = "Software Engineering"

        fields = [
            {"name": "Company", "value": match["company"], "inline": True},
            {"name": "Location", "value": match["location"] or "Remote/Various", "inline": True},
        ]
        if match["term"]:
            fields.append({"name": "Term", "value": match["term"], "inline": True})
        if match["source"]:
            fields.append({"name": "Source", "value": match["source"], "inline": True})

        embed = {
            "title": match["title"][:256],
            "url": match["url"] if match["url"].startswith("http") else "https://simplify.jobs",
            "description": f"**Category:** {role_type}\n[**Click Here to Apply Directly**]({match['url']})",
            "color": color,
            "fields": fields,
            "footer": {"text": "Internship Alert Bot • Automated Update"}
        }
        embeds.append(embed)

    if webhook_url and webhook_url.strip() and "discord.com/api/webhooks" in webhook_url:
        print(f"[*] Dispatching {len(embeds)} embeds to Discord...")
        send_discord_webhook(webhook_url, embeds)
        print("[OK] Discord notifications sent successfully!")
    else:
        print("[!] No Discord Webhook configured yet (or URL is placeholder).")
        print("[*] Displaying top 5 new matches in console:")
        for m in new_matches[:5]:
            print(f"  - [{m['company']}] {m['title']} ({m['location']}) -> {m['url']}")
        if len(new_matches) > 5:
            print(f"  ... and {len(new_matches) - 5} more.")

    # Mark as seen
    for m in new_matches:
        seen_ids.add(m["id"])
    save_seen(seen_ids)
    print(f"[*] Updated seen database. Total tracked jobs: {len(seen_ids)}")


if __name__ == "__main__":
    main()

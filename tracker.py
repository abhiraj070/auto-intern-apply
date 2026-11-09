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
import html
import calendar
from datetime import date, datetime, timedelta, timezone

# Ensure clean UTF-8 printing on Windows console
if sys.platform == "win32" and __name__ == "__main__":
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(SCRIPT_DIR, "seen_jobs.json")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
POSTING_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


def posting_window(today=None):
    """Inclusive dates from two calendar months ago through today in IST."""
    today = today if today is not None else datetime.now(POSTING_TIMEZONE).date()
    year, month_index = divmod(today.year * 12 + today.month - 1 - 2, 12)
    month = month_index + 1
    cutoff = date(year, month, min(today.day, calendar.monthrange(year, month)[1]))
    return cutoff, today


def parse_posting_date(value):
    """Read ISO dates/timestamps or Unix seconds/milliseconds as an IST date."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and re.fullmatch(r"\d+(?:\.\d+)?", value.strip())):
            timestamp = float(value)
            if timestamp >= 100_000_000_000:
                timestamp /= 1000
            posted = datetime.fromtimestamp(timestamp, timezone.utc)
        elif isinstance(value, str):
            value = value.strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                return date.fromisoformat(value)
            posted = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if posted.tzinfo is None:
                posted = posted.replace(tzinfo=timezone.utc)
        else:
            return None
        return posted.astimezone(POSTING_TIMEZONE).date()
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def get_posting_date(item):
    # Only posting/creation dates count. An edit must not make an old job fresh.
    for key in ("posted_at", "posted_at_timestamp", "date_posted"):
        posted = parse_posting_date(item.get(key))
        if posted is not None:
            return posted
    return None

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

# Location matching: Only allow India OR Remote roles
INDIA_REGEX = re.compile(
    r"\b(?:india|bengaluru|bangalore|hyderabad|pune|mumbai|delhi|noida|gurugram|gurgaon|chennai|kolkata|ahmedabad|jaipur|indore|chandigarh|kochi|kerala|telangana|karnataka|maharashtra|haryana|tamil nadu|uttar pradesh)\b",
    re.IGNORECASE
)
REMOTE_REGEX = re.compile(
    r"\b(?:remote|work from home|wfh|worldwide|anywhere|telecommute)\b",
    re.IGNORECASE
)


def is_valid_location(loc_str, is_remote=False):
    """
    Returns True ONLY if:
    1. Located inside India, OR
    2. Explicitly Remote.
    Rejects physical on-site/hybrid roles in US, Canada, Europe, etc.
    """
    if is_remote:
        return True

    if not loc_str:
        return False

    if INDIA_REGEX.search(loc_str):
        return True

    if REMOTE_REGEX.search(loc_str):
        return True

    return False


def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_seen(seen_ids):
    # Replace atomically so interruption cannot leave a truncated database.
    temp_file = SEEN_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen_ids)), f, indent=2)
    os.replace(temp_file, SEEN_FILE)


def get_canonical_keys(company, title, url, job_id=""):
    """Identify a requisition by URL/ID, never by its reusable company/title."""
    keys = set()
    if job_id and not str(job_id).startswith("jsearch-LTJ"):
        keys.add(str(job_id).strip())

    if url:
        parts = urllib.parse.urlsplit(str(url))
        tracking = {"ref", "trk", "refid", "trackingid", "midtoken", "position", "pagenum"}
        query = [(key, value) for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                 if not key.lower().startswith("utm_") and key.lower() not in tracking]
        clean_url = urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                                            parts.path.rstrip("/"),
                                            urllib.parse.urlencode(sorted(query)), ""))
        if clean_url:
            keys.add(clean_url)

    return keys


def is_target_role(title, employment_types=None):
    if not title:
        return False
    title_lower = title.lower()
    if re.search(r"\b(?:senior|sr\.?|staff|principal|lead|manager)\b", title_lower):
        return False
    types = employment_types or []
    if isinstance(types, str):
        types = [types]
    internship = re.search(r"\b(?:intern|interns|internship|internships|working student)\b", title_lower)
    if not internship and not any(str(t).upper() in {"INTERN", "INTERNSHIP"} for t in types):
        return False
    for neg in NEGATIVE_KEYWORDS:
        if neg in title_lower:
            return False
    return any(p.search(title_lower) for p in COMPILED_PATTERNS)


def parse_and_filter_stipend(salary_min, salary_max, period, desc, min_stipend=10000,
                             currency=None, currency_to_inr=None, default_currency=None):
    """Compare known pay in INR; retain unconvertible pay with an explicit label.

    Rates are supplied in config, never guessed. A range uses its lower bound.
    Bare amounts in descriptions default to monthly; structured pay without a
    period is retained for review rather than inventing a pay period.
    """
    rates = {"INR": 1.0}
    rates.update({str(k).upper(): float(v) for k, v in (currency_to_inr or {}).items()})
    text = html.unescape(re.sub(r"<[^>]+>", " ", desc or ""))
    text = re.sub(r"\s+", " ", text).lower()
    if re.search(r"\b(?:unpaid|no stipend|zero stipend|without stipend|volunteer intern|non-paid)\b", text):
        return False, "Unpaid"

    def amount(value):
        if value is None or value == "":
            return None
        match = re.fullmatch(r"(\d[\d,]*(?:\.\d+)?)\s*(k|lakh|lac|lpa)?", str(value).strip().lower())
        if not match:
            return None
        number = float(match.group(1).replace(",", ""))
        return number * {None: 1, "k": 1000, "lakh": 100000, "lac": 100000, "lpa": 100000}[match.group(2)]

    def evaluate(value, pay_period, pay_currency):
        code = (pay_currency or "").upper()
        label = f"{code or 'Currency unspecified'} {value:,.0f}/{pay_period or 'period unspecified'}"
        factors = {"MONTH": 1, "YEAR": 1 / 12, "HOUR": 160, "WEEK": 52 / 12, "DAY": 20}
        if value == 0:
            return False, "Unpaid"
        if code not in rates or pay_period not in factors:
            return True, label + " (INR threshold unverified)"
        passed = value * factors[pay_period] * rates[code] >= min_stipend
        return passed, label

    # Inspect explicit stipend/salary mentions in every source's description.
    number = r"\d[\d,]*(?:\.\d+)?\s*(?:k\b|lakh\b|lac\b|lpa\b)?"
    pay_pattern = (r"\b(?:stipend|salary|compensation)\b\s*"
                   r"(?:(?:range|offered|is|of|up to|from|between)\s*)?[:=–-]?\s*"
                   r"(?:(?:inr|rs\.?|usd|eur|gbp|₹|\$|€|£)\s*)?"
                   r"(?P<low>" + number + r")"
                   r"(?:\s*(?:-|–|to)\s*(?:(?:inr|rs\.?|usd|eur|gbp|₹|\$|€|£)\s*)?"
                   r"(?P<high>" + number + r"))?")
    described = None
    for match in re.finditer(pay_pattern, text):
        context = match.group(0) + text[match.end():match.end() + 35]
        code_match = re.search(r"\b(inr|usd|eur|gbp)\b|₹|\brs\.?\b|\$|€|£", context)
        code = currency or default_currency
        if code_match:
            token = code_match.group(0)
            code = {"₹": "INR", "rs": "INR", "rs.": "INR", "$": "USD", "€": "EUR", "£": "GBP"}.get(token, token.upper())
        pay_period = "MONTH"
        if re.search(r"month|/mo\b", context):
            pay_period = "MONTH"
        elif re.search(r"year|annual|annum|\blpa\b|/yr", context):
            pay_period = "YEAR"
        elif re.search(r"hour|/hr", context):
            pay_period = "HOUR"
        elif re.search(r"week|/wk", context):
            pay_period = "WEEK"
        elif re.search(r"daily|/day|per day", context):
            pay_period = "DAY"
        low = match.group("low").strip()
        high = match.group("high")
        # Share a suffix in forms such as 5-10k or 2-3 LPA.
        if high and not re.search(r"[a-z]", low):
            suffix = re.search(r"(k|lakh|lac|lpa)\s*$", high)
            if suffix:
                low += suffix.group(1)
        value = amount(low)
        if value is not None:
            described = evaluate(value, pay_period, code)
            if not described[0]:
                return described

    low, high = amount(salary_min), amount(salary_max)
    value = low if low is not None else high
    if value is not None:
        period_name = (period or "").upper().rstrip("S")
        period_name = {"MONTHLY": "MONTH", "YEARLY": "YEAR", "ANNUAL": "YEAR", "HOURLY": "HOUR"}.get(period_name, period_name)
        return evaluate(value, period_name, currency)
    return described or (True, "Competitive / Disclosed on Apply")


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
                if is_target_role(title):
                    jobs.append({
                        "id": f"arbeitnow-{item.get('slug')}",
                        "company_name": item.get("company_name", "Unknown"),
                        "title": title,
                        "url": item.get("url", ""),
                        "locations": [item.get("location", "Remote" if item.get("remote") else "Various")],
                        "active": True,
                        "source": "Arbeitnow",
                        "stipend": "Disclosed on Apply",
                        "description": item.get("description", ""),
                        "posted_at": item.get("created_at"),
                        "is_remote": bool(item.get("remote", False))
                    })
            return jobs
    except Exception as e:
        print(f"[!] Warning: failed to fetch Arbeitnow: {e}")
        return []


def fetch_jsearch_listings(rapidapi_key, min_stipend=10000):
    """
    Fetches real-time tech internships from Google for Jobs / JSearch
    Aggregates LinkedIn, Indeed, Glassdoor, Internshala, Naukri, Wellfound, etc.
    """
    if not rapidapi_key or not rapidapi_key.strip() or rapidapi_key == "YOUR_RAPIDAPI_KEY_HERE":
        return []

    queries = [
        "Software Engineer intern in India",
        "AI Machine Learning intern in India",
        "Backend Developer intern in India",
        "Fullstack Developer intern in India",
        "Remote Software Engineer intern"
    ]

    headers = {
        "X-RapidAPI-Key": rapidapi_key.strip(),
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    jobs = []
    print("[*] Querying RapidAPI JSearch (indexes LinkedIn, Indeed, Internshala, Naukri, Glassdoor)...")

    # Run every configured domain query, including fullstack and remote.
    for q in queries:
        encoded_q = urllib.parse.quote(q)
        url = f"https://jsearch.p.rapidapi.com/search-v2?query={encoded_q}&num_pages=1"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                job_list = []
                data_field = data.get("data", {})
                if isinstance(data_field, dict):
                    job_list = data_field.get("jobs", [])
                elif isinstance(data_field, list):
                    job_list = data_field

                for item in job_list:
                    job_id = item.get("job_id", "")
                    title = item.get("job_title", "")
                    company = item.get("employer_name", "Unknown")
                    url_link = item.get("job_apply_link") or item.get("job_google_link") or ""
                    city = item.get("job_city") or ""
                    country = item.get("job_country") or ""
                    if country.upper() == "IN":
                        country = "India"
                    location = f"{city}, {country}".strip(", ") if city else country
                    publisher = item.get("job_publisher") or "Web"
                    desc = item.get("job_description", "")

                    sal_min = item.get("job_min_salary")
                    sal_max = item.get("job_max_salary")
                    period = item.get("job_salary_period")

                    job_uid = item.get("job_uid") or ""
                    stable_id = f"jsearch-{job_uid or job_id}" if job_uid or job_id else url_link

                    jobs.append({
                        "id": stable_id,
                        "company_name": company,
                        "title": title,
                        "url": url_link,
                        "locations": [location],
                        "active": True,
                        "source": f"{publisher} (via JSearch)",
                        "description": desc,
                        "salary_min": sal_min,
                        "salary_max": sal_max,
                        "salary_period": period,
                        "salary_currency": item.get("job_salary_currency"),
                        "employment_types": item.get("job_employment_types", []),
                        "posted_at": item.get("job_posted_at_datetime_utc"),
                        "posted_at_timestamp": item.get("job_posted_at_timestamp"),
                        "is_remote": bool(item.get("job_is_remote", False))
                    })
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            print(f"[!] JSearch notice ({e.code}): {err_body[:100]}")
            break
        except Exception as e:
            print(f"[!] JSearch exception: {e}")
            break

    print(f"[*] JSearch returned {len(jobs)} postings for filtering.")
    return jobs


def send_discord_webhook(webhook_url, embeds, on_delivered=None):
    """Return delivered embed indexes; checkpoint each acknowledged message."""
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "InternshipBot/1.0"
    }

    # Discord also limits the combined embed text to 6,000 characters.
    batches = []
    chunk, indexes, chars = [], [], 0
    for index, embed in enumerate(embeds):
        size = len(embed.get("title", "")) + len(embed.get("description", ""))
        size += len(embed.get("footer", {}).get("text", ""))
        size += sum(len(f["name"]) + len(f["value"]) for f in embed.get("fields", []))
        if chunk and (len(chunk) == 10 or chars + size > 6000):
            batches.append((chunk, indexes))
            chunk, indexes, chars = [], [], 0
        chunk.append(embed)
        indexes.append(index)
        chars += size
    if chunk:
        batches.append((chunk, indexes))
    delivered = set()
    for i, (chunk, indexes) in enumerate(batches):
        payload = {
            "content": "🚀 **New Internship Openings Found!**" if i == 0 else "",
            "embeds": chunk
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(webhook_url, data=data, headers=headers)
        success = False
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                success = 200 <= resp.status < 300
        except urllib.error.HTTPError as e:
            print(f"[!] Discord Webhook HTTP Error: {e.code} - {e.read().decode('utf-8', errors='ignore')}")
        except Exception as e:
            print(f"[!] Error sending to Discord: {e}")
        if success:
            delivered.update(indexes)
            # Keep state-write errors visible; never treat them as delivery errors.
            if on_delivered:
                on_delivered(indexes)
            time.sleep(1)
    return delivered


def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    rapidapi_key = os.environ.get("RAPIDAPI_KEY")
    min_stipend = 10000
    max_alerts = 30
    min_indian_alerts = 15
    currency_to_inr = {"INR": 1.0}

    # Check config.json if available
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if not isinstance(cfg, dict):
                    raise ValueError("config.json must contain an object")
                if not webhook_url and "discord_webhook_url" in cfg:
                    webhook_url = cfg["discord_webhook_url"]
                if not rapidapi_key and "rapidapi_key" in cfg:
                    rapidapi_key = cfg["rapidapi_key"]
                if "min_stipend" in cfg:
                    min_stipend = int(cfg["min_stipend"])
                if "max_alerts_per_run" in cfg:
                    max_alerts = int(cfg["max_alerts_per_run"])
                if "min_indian_alerts" in cfg:
                    min_indian_alerts = int(cfg["min_indian_alerts"])
                currency_to_inr.update({str(k).upper(): float(v) for k, v in cfg.get("currency_to_inr", {}).items()})
        except (ValueError, TypeError, OSError) as e:
            print(f"[!] Invalid configuration: {e}")
            return False
    if min_stipend < 0 or max_alerts < 1 or min_indian_alerts < 0 or any(v <= 0 for v in currency_to_inr.values()):
        print("[!] Invalid alert limits or currency conversion rates.")
        return False
    min_indian_alerts = min(min_indian_alerts, max_alerts)

    seen_ids = load_seen()
    cutoff, today = posting_window()
    print(f"[*] Loaded {len(seen_ids)} previously seen jobs.")
    print(f"[*] Configuration: Min Stipend = INR {min_stipend:,} | Total Daily Alerts = {max_alerts} (Min {min_indian_alerts} for India)")
    print(f"[*] Posting dates must be {cutoff.isoformat()} through {today.isoformat()} (IST, inclusive).")

    print("[*] Fetching listings from SimplifyJobs (Summer 2025 / Summer 2026)...")
    listings_2025 = fetch_simplify_listings("Summer2025-Internships")
    listings_2026 = fetch_simplify_listings("Summer2026-Internships")
    arbeitnow_jobs = fetch_arbeitnow_listings()
    jsearch_jobs = fetch_jsearch_listings(rapidapi_key, min_stipend=min_stipend)

    all_raw = listings_2025 + listings_2026 + arbeitnow_jobs + jsearch_jobs
    print(f"[*] Total raw listings gathered: {len(all_raw)}")

    new_matches = []
    current_run_keys = set()
    date_rejections = 0
    
    for item in all_raw:
        job_id = str(item.get("id") or item.get("url") or "")
        company = item.get("company_name", "Unknown Company")
        title = item.get("title", "")
        url = item.get("url", "")

        # Legacy sig: keys in seen_jobs.json are intentionally no longer consulted.
        item_keys = get_canonical_keys(company, title, url, job_id)
        if not item_keys:
            continue

        # Check if already alerted in ANY prior run
        if any(k in seen_ids for k in item_keys):
            continue

        # Check if already caught in current run (intra-run deduplication across queries)
        if any(k in current_run_keys for k in item_keys):
            continue

        # Check if active
        if item.get("active") is False:
            continue

        posted_date = get_posting_date(item)
        if posted_date is None or not cutoff <= posted_date <= today:
            date_rejections += 1
            continue

        if not is_target_role(title, item.get("employment_types")):
            continue

        locs = item.get("locations", [])
        loc_str = ", ".join(locs) if isinstance(locs, list) else str(locs or "Not specified")
        is_remote = bool(item.get("is_remote", False)) or ("remote" in loc_str.lower())

        # Location filter: Only accept India OR Remote roles
        if not is_valid_location(loc_str, is_remote=is_remote):
            continue

        terms = item.get("terms", [])
        term_str = ", ".join(terms) if isinstance(terms, list) else str(terms or "")
        description = " ".join(str(item.get(key) or "") for key in ("description", "job_description"))
        if item.get("stipend") is not None:
            description += " Stipend: " + str(item["stipend"])
        passed_stipend, stipend_str = parse_and_filter_stipend(
            item.get("salary_min"), item.get("salary_max"), item.get("salary_period"),
            description, min_stipend, currency=item.get("salary_currency"),
            currency_to_inr=currency_to_inr,
            default_currency="INR" if INDIA_REGEX.search(loc_str) else None)
        if not passed_stipend:
            continue

        is_india = bool(INDIA_REGEX.search(loc_str))

        # Register keys in current run to prevent duplicates within this batch
        current_run_keys.update(item_keys)

        new_matches.append({
            "id": job_id,
            "company": company,
            "title": title,
            "url": url,
            "location": loc_str,
            "term": term_str,
            "source": item.get("source", "Simplify"),
            "stipend": stipend_str,
            "posted_date": posted_date.isoformat(),
            "is_india": is_india,
            "keys": item_keys
        })

    print(f"[*] Skipped {date_rejections} listings with old, missing, invalid, or future posting dates.")
    print(f"[*] Found {len(new_matches)} new matching internship openings.")

    if not new_matches:
        print("[OK] No new postings since last check. All caught up!")
        return True

    # Partition matches into India and Remote
    india_matches = [m for m in new_matches if m["is_india"]]
    remote_matches = [m for m in new_matches if not m["is_india"]]

    print(f"[*] Pool breakdown: {len(india_matches)} Indian openings, {len(remote_matches)} Remote openings")

    # Select: up to min_indian_alerts (15) strictly for India, fill rest up to max_alerts (30) with Remote
    selected_india = india_matches[:min_indian_alerts]
    needed_remote = max_alerts - len(selected_india)
    selected_remote = remote_matches[:needed_remote]

    alerts_to_send = selected_india + selected_remote

    # Backfill with remaining Indian jobs if room exists
    if len(alerts_to_send) < max_alerts and len(india_matches) > len(selected_india):
        extra_india = india_matches[len(selected_india) : len(selected_india) + (max_alerts - len(alerts_to_send))]
        alerts_to_send.extend(extra_india)

    # Backfill with remaining Remote jobs if room exists
    if len(alerts_to_send) < max_alerts and len(remote_matches) > len(selected_remote):
        extra_rem = remote_matches[len(selected_remote) : len(selected_remote) + (max_alerts - len(alerts_to_send))]
        alerts_to_send.extend(extra_rem)

    india_count = len([m for m in alerts_to_send if m["is_india"]])
    remote_count = len([m for m in alerts_to_send if not m["is_india"]])
    print(f"[*] Dispatching {len(alerts_to_send)} total alerts: {india_count} strictly Indian openings + {remote_count} Remote openings.")

    # Prepare Discord embeds
    embeds = []
    for match in alerts_to_send:
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
            {"name": "Stipend", "value": match["stipend"], "inline": True},
            {"name": "Posted (IST)", "value": match["posted_date"], "inline": True},
        ]
        if match["term"]:
            fields.append({"name": "Term", "value": match["term"], "inline": True})
        if match["source"]:
            fields.append({"name": "Source", "value": match["source"], "inline": True})
        for field in fields:
            field["value"] = str(field["value"])[:1024] or "Not specified"

        embed = {
            "title": match["title"][:256],
            "url": match["url"] if match["url"].startswith("http") else "https://simplify.jobs",
            "description": f"**Category:** {role_type}\n[**Click Here to Apply Directly**]({match['url']})",
            "color": color,
            "fields": fields,
            "footer": {"text": f"Internship Alert Bot • Min Stipend ₹{min_stipend:,}"}
        }
        embeds.append(embed)

    if webhook_url and webhook_url.strip() and "discord.com/api/webhooks" in webhook_url:
        print(f"[*] Dispatching {len(embeds)} embeds to Discord...")
        def checkpoint(indexes):
            for index in indexes:
                seen_ids.update(alerts_to_send[index]["keys"])
            save_seen(seen_ids)

        delivered = send_discord_webhook(webhook_url, embeds, on_delivered=checkpoint)
        print(f"[*] Delivered {len(delivered)}/{len(embeds)} alerts. Undelivered jobs remain eligible for retry.")
        return len(delivered) == len(embeds)
    else:
        print("[!] No Discord Webhook configured yet (or URL is placeholder).")
        print("[*] Displaying top 5 new matches in console:")
        for m in alerts_to_send[:5]:
            print(f"  - [{m['company']}] {m['title']} ({m['location']}) - Stipend: {m['stipend']} -> {m['url']}")

    print("[*] Preview only; no jobs were marked as seen.")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)

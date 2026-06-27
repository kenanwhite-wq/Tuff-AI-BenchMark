"""News scanner for AI benchmark tracking.
Fetches items from RSS and scraped news sources, classifies them with Ollama,
and routes approved items into the feed_entries table.
"""

import sys
import traceback
import subprocess
from datetime import datetime
from urllib.parse import urljoin

# ============================================
# IMPORT WITH AUTO-INSTALL
# ============================================

try:
    import requests
except ImportError:
    print("📦 requests not found. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    import feedparser
except ImportError:
    print("📦 feedparser not found. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "feedparser"])
    import feedparser

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("📦 beautifulsoup4 not found. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4"])
    from bs4 import BeautifulSoup

try:
    from config import DB_NAME, FEED_TABLE, NEWS_ITEMS_TABLE, get_connection, init_database
except Exception as e:
    print(f"❌ Could not import config: {e}")
    raise

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3:8b"
MAX_ITEMS_PER_SOURCE = 10
OLLAMA_PROMPT_TEMPLATE = (
    "You are a classifier for an AI benchmark tracking website.\n"
    "Read the article title and summary below and classify it into exactly one of these categories:\n\n"
    "BENCHMARK - An exploit, contamination finding, saturation concern, new benchmark released, or methodology critique affecting a tracked benchmark\n"
    "MODEL_RELEASE - A new AI model announced or released by any lab\n"
    "PRICE_CHANGE - A change to API pricing, rate limits, or model availability\n"
    "RESEARCH_PAPER - A new academic paper about AI evaluation, capabilities, or safety\n"
    "GENERAL_NEWS - AI industry news worth surfacing: funding, leadership changes, regulatory actions, significant product launches\n"
    "DISCARD - Press releases, minor updates, marketing content, anything not worth surfacing\n\n"
    "Reply with ONLY the category name, nothing else.\n\n"
    "Title: {title}\n"
    "Summary: {summary}\n"
)
CATEGORIES = [
    "BENCHMARK",
    "MODEL_RELEASE",
    "PRICE_CHANGE",
    "RESEARCH_PAPER",
    "GENERAL_NEWS",
    "DISCARD",
]

RSS_SOURCES = [
    {"name": "OpenAI Blog", "url": "https://openai.com/news/rss.xml", "source_category": "rss"},
    {"name": "HuggingFace Blog", "url": "https://huggingface.co/blog/feed.xml", "source_category": "rss"},
    {"name": "DeepMind Blog", "url": "https://deepmind.google/discover/blog/rss.xml", "source_category": "rss"},
    {"name": "MarkTechPost", "url": "https://www.marktechpost.com/feed/", "source_category": "rss"},
    {"name": "The Gradient", "url": "https://thegradient.pub/rss/", "source_category": "rss"},
    {"name": "arXiv cs.AI", "url": "https://arxiv.org/rss/cs.AI", "source_category": "rss"},
    {"name": "arXiv cs.CL", "url": "https://arxiv.org/rss/cs.CL", "source_category": "rss"},
    {"name": "Reddit r/LocalLLaMA", "url": "https://www.reddit.com/r/LocalLLaMA.rss", "source_category": "rss"},
    {"name": "Reddit r/MachineLearning", "url": "https://www.reddit.com/r/MachineLearning.rss", "source_category": "rss"},
    {"name": "Hacker News", "url": "https://news.ycombinator.com/rss", "source_category": "rss"},
]

SCRAPE_SOURCES = [
    {"name": "Anthropic News", "url": "https://www.anthropic.com/news", "source_category": "scrape"},
    {"name": "Meta AI Blog", "url": "https://ai.meta.com/blog/", "source_category": "scrape"},
    {"name": "Mistral News", "url": "https://mistral.ai/news/", "source_category": "scrape"},
]


# ============================================
# UTILS
# ============================================

def clean_text(value):
    if not value:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(v) for v in value)
    if "<" in value and ">" in value:
        return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    return str(value).strip()


def truncate_summary(value, length=300):
    if not value:
        return ""
    text = clean_text(value)
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "..."


def extract_ollama_output(payload):
    if isinstance(payload, dict):
        if "results" in payload and isinstance(payload["results"], list):
            for result in payload["results"]:
                if isinstance(result, dict):
                    for key in ("output", "generated", "text", "response", "content"):
                        value = result.get(key)
                        if value:
                            return value
        for key in ("output", "generated", "text", "response", "content"):
            value = payload.get(key)
            if value:
                return value
    return None


def parse_classification(raw_response):
    if not raw_response:
        return "DISCARD"

    normalized = " ".join(str(raw_response).split()).strip().upper()
    if not normalized:
        return "DISCARD"

    # Prefer exact first line
    first_line = normalized.splitlines()[0].strip()
    if first_line in CATEGORIES:
        return first_line

    for category in CATEGORIES:
        if category in first_line:
            return category

    for category in CATEGORIES:
        if category in normalized:
            return category

    return "DISCARD"


def create_prompt(title, summary):
    return OLLAMA_PROMPT_TEMPLATE.format(title=title, summary=summary)


def classify_item(title, summary):
    prompt = create_prompt(title, truncate_summary(summary, 300))
    payload = {
        'model': OLLAMA_MODEL,
        'prompt': prompt,
        'stream': False,
        'think': False,
        'options': {
            'temperature': 0.1,
            'num_predict': 20
        }
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        response.raise_for_status()
        data = None
        try:
            data = response.json()
        except ValueError:
            pass

        raw_output = extract_ollama_output(data) if data is not None else None
        if raw_output is None:
            raw_output = response.text

        classification = parse_classification(raw_output)
        return classification
    except requests.exceptions.RequestException as exc:
        print(f"  ❌ Ollama request failed for '{title[:50]}': {exc}")
        return None
    except Exception as exc:
        print(f"  ❌ Error classifying '{title[:50]}': {exc}")
        return None


def fetch_rss_items(source):
    try:
        feed = feedparser.parse(source["url"])
        if getattr(feed, "bozo", False):
            print(f"  ⚠️ RSS parse issue for {source['name']}: {getattr(feed, 'bozo_exception', 'unknown')}")

        items = []
        for entry in getattr(feed, "entries", [])[:MAX_ITEMS_PER_SOURCE]:
            url = entry.get("link") or entry.get("id")
            title = entry.get("title") or entry.get("headline") or ""
            summary = entry.get("summary") or entry.get("description") or ""
            if not title or not url:
                continue
            items.append({
                "url": url.strip(),
                "title": clean_text(title),
                "summary": clean_text(summary) or clean_text(title),
                "source_name": source["name"],
                "source_category": source["source_category"],
            })
        return items
    except Exception as exc:
        print(f"  ❌ Failed to fetch RSS source {source['name']}: {exc}")
        return None


def find_scraped_items(soup, base_url):
    candidates = []

    for article in soup.find_all(["article", "section", "div"], recursive=True):
        link = article.find("a", href=True)
        if not link:
            continue
        title = link.get_text(strip=True)
        if not title or len(title) < 10:
            continue
        url = urljoin(base_url, link["href"])
        candidates.append((title, url))

    if not candidates:
        for link in soup.find_all("a", href=True):
            title = link.get_text(strip=True)
            href = link["href"].strip()
            if not title or len(title) < 15:
                continue
            if href.startswith("#"):
                continue
            if any(token in href.lower() for token in ["/news", "/blog", "/post", "/article"]):
                url = urljoin(base_url, href)
                candidates.append((title, url))

    unique = []
    seen = set()
    for title, url in candidates:
        normalized_url = url.split("#")[0].strip()
        if not normalized_url or normalized_url in seen:
            continue
        seen.add(normalized_url)
        unique.append((title, normalized_url))

    return unique


def fetch_scrape_items(source):
    try:
        response = requests.get(source["url"], timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        items = []
        for title, url in find_scraped_items(soup, source["url"])[:MAX_ITEMS_PER_SOURCE]:
            items.append({
                "url": url,
                "title": clean_text(title),
                "summary": clean_text(title),
                "source_name": source["name"],
                "source_category": source["source_category"],
            })
        return items
    except Exception as exc:
        print(f"  ❌ Failed to scrape source {source['name']}: {exc}")
        return None


def is_news_item_seen(conn, url):
    cursor = conn.cursor()
    cursor.execute(f"SELECT 1 FROM {NEWS_ITEMS_TABLE} WHERE url = ?", (url,))
    seen = cursor.fetchone() is not None
    cursor.close()
    return seen


def persist_news_item(conn, item, classification, status):
    now = datetime.now().isoformat()
    cursor = conn.cursor()
    cursor.execute(
        f"INSERT INTO {NEWS_ITEMS_TABLE} (url, title, summary, source_name, source_category, classification, created_at, status)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item["url"],
            item["title"],
            item["summary"],
            item["source_name"],
            item["source_category"],
            classification,
            now,
            status,
        ),
    )
    conn.commit()
    cursor.close()


def route_feed_entry(conn, item, classification, run_id):
    now = datetime.now().isoformat()
    if classification == "BENCHMARK":
        tier = "big"
        headline = f"Benchmark alert: {item['title']}"
    elif classification == "MODEL_RELEASE":
        tier = "moderate"
        headline = f"New model: {item['title']}"
    elif classification == "PRICE_CHANGE":
        tier = "moderate"
        headline = item["title"]
    elif classification == "RESEARCH_PAPER":
        tier = "small"
        headline = item["title"]
    elif classification == "GENERAL_NEWS":
        tier = "small"
        headline = item["title"]
    else:
        return

    cursor = conn.cursor()
    cursor.execute(
        f"INSERT INTO {FEED_TABLE} (model, source, tier, type, headline, body, status, created_at, run_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item["title"],
            item["source_name"],
            tier,
            "news_scanner",
            headline,
            item["url"],
            "approved",
            now,
            run_id,
        ),
    )
    conn.commit()
    cursor.close()


def process_source(conn, source, fetcher, run_id):
    print(f"\n📥 Fetching source: {source['name']}")
    items = fetcher(source)
    if items is None:
        return 0, 0, 0, 1

    fetched = len(items)
    new_count = 0
    seen_count = 0

    for item in items:
        if not item.get("url"):
            continue

        if is_news_item_seen(conn, item["url"]):
            seen_count += 1
            continue

        classification = classify_item(item["title"], item["summary"])
        if classification is None:
            print(f"  ⚠️ Skipping item due to classification failure: {item['title']}")
            continue

        status = "discarded" if classification == "DISCARD" else "active"
        try:
            persist_news_item(conn, item, classification, status)
        except Exception as exc:
            print(f"  ❌ Failed to save news item '{item['title']}': {exc}")
            continue

        if classification != "DISCARD":
            try:
                route_feed_entry(conn, item, classification, run_id)
            except Exception as exc:
                print(f"  ❌ Failed to route feed entry for '{item['title']}': {exc}")

        new_count += 1

    return fetched, new_count, seen_count, 0


def main():
    print("=" * 60)
    print("🔎 NEWS SCANNER")
    print("=" * 60)
    print(f"🕐 Started at: {datetime.now().isoformat()}")

    run_id = f"scanner_{datetime.now().isoformat()}"
    print(f"📌 Run ID: {run_id}")

    init_database()
    conn = get_connection()

    summary = {
        "sources": {},
        "classification": {category: 0 for category in CATEGORIES},
        "total_fetched": 0,
        "total_new": 0,
        "total_seen": 0,
        "total_errors": 0,
    }

    for source in RSS_SOURCES:
        summary["sources"][source["name"]] = {"fetched": 0, "new": 0, "seen": 0, "errors": 0}

    for source in SCRAPE_SOURCES:
        summary["sources"][source["name"]] = {"fetched": 0, "new": 0, "seen": 0, "errors": 0}

    try:
        for source in RSS_SOURCES:
            fetched, new_count, seen_count, errors = process_source(conn, source, fetch_rss_items, run_id)
            summary["sources"][source["name"]]["fetched"] = fetched
            summary["sources"][source["name"]]["new"] = new_count
            summary["sources"][source["name"]]["seen"] = seen_count
            summary["sources"][source["name"]]["errors"] = errors
            summary["total_fetched"] += fetched
            summary["total_new"] += new_count
            summary["total_seen"] += seen_count
            summary["total_errors"] += errors

        for source in SCRAPE_SOURCES:
            fetched, new_count, seen_count, errors = process_source(conn, source, fetch_scrape_items, run_id)
            summary["sources"][source["name"]]["fetched"] = fetched
            summary["sources"][source["name"]]["new"] = new_count
            summary["sources"][source["name"]]["seen"] = seen_count
            summary["sources"][source["name"]]["errors"] = errors
            summary["total_fetched"] += fetched
            summary["total_new"] += new_count
            summary["total_seen"] += seen_count
            summary["total_errors"] += errors
    except Exception as exc:
        print(f"❌ News scanner errored: {exc}")
        traceback.print_exc()
    finally:
        conn.close()

    print("\n" + "=" * 60)
    print("🧾 News scanner summary")
    print(f"Total items fetched: {summary['total_fetched']}")
    print(f"Total new items:    {summary['total_new']}")
    print(f"Total already seen: {summary['total_seen']}")
    print(f"Total source errors:{summary['total_errors']}")
    print("\nSource breakdown:")
    for source_name, stats in summary["sources"].items():
        print(f"  - {source_name}: fetched={stats['fetched']} new={stats['new']} seen={stats['seen']} errors={stats['errors']}")

    print("\nClassification counts:")
    for category in CATEGORIES:
        cursor = get_connection().cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {NEWS_ITEMS_TABLE} WHERE classification = ?", (category,))
        count = cursor.fetchone()[0]
        cursor.close()
        print(f"  - {category}: {count}")

    print("=" * 60)


if __name__ == "__main__":
    main()

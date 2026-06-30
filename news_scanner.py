"""News scanner for AI benchmark tracking.
Fetches items from RSS and scraped news sources, classifies them with the
configured LLM provider, and routes approved items into the feed_entries table.
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

MAX_ITEMS_PER_SOURCE = 10

SOURCE_LIMITS = {
    'Hacker News': 5,
    'Reddit r/LocalLLaMA': 5,
    'Reddit r/MachineLearning': 5,
    'default': 10,
}

NOISY_SOURCES = {'Hacker News', 'Reddit r/LocalLLaMA', 'Reddit r/MachineLearning'}

AI_KEYWORDS = [
    'ai', 'llm', 'model', 'gpt', 'claude', 'gemini', 'llama', 'mistral',
    'benchmark', 'transformer', 'neural', 'inference', 'training', 'fine-tun',
    'agent', 'reasoning', 'coding', 'deepseek', 'anthropic', 'openai', 'google',
    'meta ai', 'hugging', 'weights', 'parameter', 'token', 'context', 'prompt',
    'rag', 'embedding', 'diffusion', 'multimodal', 'vision', 'speech', 'alignment',
    'safety', 'rlhf', 'sft', 'quantiz', 'gguf', 'ollama', 'mlx', 'cuda',
    'dataset', 'eval', 'leaderboard', 'arxiv', 'paper', 'research',
]

CLASSIFY_PROMPT_TEMPLATE = (
    "You are a strict content filter for an AI model benchmark tracking website.\n"
    "Your audience cares ONLY about: AI model releases, AI benchmark results, \n"
    "AI research papers, AI company news, and AI safety/alignment topics.\n\n"
    "Classify this item into exactly one category. Be aggressive about DISCARD —\n"
    "when in doubt, discard.\n\n"
    "BENCHMARK - exploit, contamination, saturation, new benchmark released, methodology critique\n"
    "MODEL_RELEASE - new AI model announced or released\n"
    "PRICE_CHANGE - API pricing or availability change\n"
    "RESEARCH_PAPER - academic paper about AI evaluation, capabilities, or safety\n"
    "GENERAL_NEWS - significant AI industry news: major funding, leadership changes, \n"
    "               regulatory actions, important product launches. NOT hardware news, \n"
    "               NOT general tech news, NOT social media drama.\n"
    "DISCARD - hardware reviews, GPU mods, non-AI tech news, opinion pieces without \n"
    "          new information, reddit drama, cryptocurrency, anything not directly \n"
    "          about AI models or benchmarks\n\n"
    "Reply with ONLY the category name.\n\n"
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
    return CLASSIFY_PROMPT_TEMPLATE.format(title=title, summary=summary)


def classify_item(title, summary):
    from llm_client import generate_text

    prompt = create_prompt(title, truncate_summary(summary, 300))

    try:
        raw_output = generate_text(prompt, temperature=0.1, max_tokens=20, timeout=60)
        if raw_output is None:
            print(f"  ❌ LLM request failed for '{title[:50]}'")
            return None

        classification = parse_classification(raw_output)
        return classification
    except Exception as exc:
        print(f"  ❌ Error classifying '{title[:50]}': {exc}")
        return None


def fetch_rss_items(source):
    try:
        feed = feedparser.parse(source["url"])
        if getattr(feed, "bozo", False):
            print(f"  ⚠️ RSS parse issue for {source['name']}: {getattr(feed, 'bozo_exception', 'unknown')}")

        limit = SOURCE_LIMITS.get(source['name'], SOURCE_LIMITS['default'])
        items = []
        for entry in getattr(feed, "entries", [])[:limit]:
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
        limit = SOURCE_LIMITS.get(source['name'], SOURCE_LIMITS['default'])
        items = []
        for title, url in find_scraped_items(soup, source["url"])[:limit]:
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


def load_tracked_models(conn):
    """Return canonical model names from the DB, sorted longest-first so
    'GPT-4o-mini' matches before 'GPT-4o' when scanning text."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT canonical_name FROM name_normalizations WHERE canonical_name IS NOT NULL"
        )
        names = [row[0] for row in cursor.fetchall() if row[0]]
        names.sort(key=len, reverse=True)
        return names
    except Exception:
        return []


def detect_model_in_text(text, tracked_models):
    """Return the first tracked model name found in text (case-insensitive), or None.
    Names shorter than 5 chars require word boundaries to avoid false matches like
    'syn' matching 'Synergy'."""
    import re
    if not text or not tracked_models:
        return None
    text_lower = text.lower()
    for model in tracked_models:
        m_lower = model.lower()
        if len(m_lower) >= 4:
            if m_lower in text_lower:
                return model
        else:
            if re.search(r'(?<![a-zA-Z0-9])' + re.escape(m_lower) + r'(?![a-zA-Z0-9])', text_lower):
                return model
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


def route_feed_entry(conn, item, classification, run_id, detected_model=None):
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
            detected_model,
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


def process_source(conn, source, fetcher, run_id, tracked_models=None):
    print(f"\n📥 Fetching source: {source['name']}")
    items = fetcher(source)
    if items is None:
        return 0, 0, 0, 1, 0, 0, 0

    fetched = len(items)
    new_count = 0
    seen_count = 0
    prefilter_skipped = 0
    llm_discarded = 0
    published = 0

    for item in items:
        if not item.get("url"):
            continue

        title = item.get("title", "")

        if len(title) < 15:
            continue

        if is_news_item_seen(conn, item["url"]):
            seen_count += 1
            continue

        if source['name'] in NOISY_SOURCES:
            title_lower = title.lower()
            if not any(kw in title_lower for kw in AI_KEYWORDS):
                print(f"  ⏭️ Skipping non-AI item: {title[:50]}")
                prefilter_skipped += 1
                continue

        classification = classify_item(title, item["summary"])
        if classification is None:
            print(f"  ⚠️ Skipping item due to classification failure: {title}")
            continue

        status = "discarded" if classification == "DISCARD" else "active"
        try:
            persist_news_item(conn, item, classification, status)
        except Exception as exc:
            print(f"  ❌ Failed to save news item '{title}': {exc}")
            continue

        if classification == "DISCARD":
            llm_discarded += 1
        else:
            published += 1
            try:
                search_text = f"{item['title']} {item.get('summary', '')}"
                detected_model = detect_model_in_text(search_text, tracked_models or [])
                route_feed_entry(conn, item, classification, run_id, detected_model=detected_model)
            except Exception as exc:
                print(f"  ❌ Failed to route feed entry for '{title}': {exc}")

        new_count += 1

    return fetched, new_count, seen_count, 0, prefilter_skipped, llm_discarded, published


def main():
    from llm_client import validate_llm_config
    validate_llm_config()

    print("=" * 60)
    print("🔎 NEWS SCANNER")
    print("=" * 60)
    print(f"🕐 Started at: {datetime.now().isoformat()}")

    run_id = f"scanner_{datetime.now().isoformat()}"
    print(f"📌 Run ID: {run_id}")

    init_database()
    conn = get_connection()
    tracked_models = load_tracked_models(conn)
    print(f"🏷️  Loaded {len(tracked_models)} tracked models for article tagging")

    summary = {
        "sources": {},
        "classification": {category: 0 for category in CATEGORIES},
        "total_fetched": 0,
        "total_new": 0,
        "total_seen": 0,
        "total_errors": 0,
        "total_prefilter_skipped": 0,
        "total_llm_discarded": 0,
        "total_published": 0,
    }

    for source in RSS_SOURCES:
        summary["sources"][source["name"]] = {"fetched": 0, "new": 0, "seen": 0, "errors": 0}

    for source in SCRAPE_SOURCES:
        summary["sources"][source["name"]] = {"fetched": 0, "new": 0, "seen": 0, "errors": 0}

    try:
        for source in RSS_SOURCES:
            fetched, new_count, seen_count, errors, pre, disc, pub = process_source(conn, source, fetch_rss_items, run_id, tracked_models=tracked_models)
            summary["sources"][source["name"]]["fetched"] = fetched
            summary["sources"][source["name"]]["new"] = new_count
            summary["sources"][source["name"]]["seen"] = seen_count
            summary["sources"][source["name"]]["errors"] = errors
            summary["total_fetched"] += fetched
            summary["total_new"] += new_count
            summary["total_seen"] += seen_count
            summary["total_errors"] += errors
            summary["total_prefilter_skipped"] += pre
            summary["total_llm_discarded"] += disc
            summary["total_published"] += pub

        for source in SCRAPE_SOURCES:
            fetched, new_count, seen_count, errors, pre, disc, pub = process_source(conn, source, fetch_scrape_items, run_id, tracked_models=tracked_models)
            summary["sources"][source["name"]]["fetched"] = fetched
            summary["sources"][source["name"]]["new"] = new_count
            summary["sources"][source["name"]]["seen"] = seen_count
            summary["sources"][source["name"]]["errors"] = errors
            summary["total_fetched"] += fetched
            summary["total_new"] += new_count
            summary["total_seen"] += seen_count
            summary["total_errors"] += errors
            summary["total_prefilter_skipped"] += pre
            summary["total_llm_discarded"] += disc
            summary["total_published"] += pub
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

    print(f"\n📊 Pre-filter skipped: {summary['total_prefilter_skipped']} non-AI items")
    print(f"📊 LLM discarded: {summary['total_llm_discarded']} items")
    print(f"📊 Published to feed: {summary['total_published']} items")
    print("=" * 60)


if __name__ == "__main__":
    main()

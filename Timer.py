"""
SIMPLE SCHEDULER (No external libraries)
Runs the hourly fetcher automatically.
"""

import time
import subprocess
import sys
from datetime import datetime, timedelta

FETCHER_SCRIPT = "hourlyfetcher.py"
NEWS_SCRIPT = "news_scanner.py"
LOG_FILE = "fetcher.log"

FETCHER_TIMEOUT = 300   # 5 minutes
SCANNER_TIMEOUT = 120   # 2 minutes — previously no timeout; a hung fetch froze the whole scheduler


def run_fetcher():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"\n{'='*60}")
    print(f"⏰ Running hourly fetch at {timestamp}")
    print(f"{'='*60}")

    try:
        result = subprocess.run(
            [sys.executable, FETCHER_SCRIPT],
            capture_output=True,
            text=True,
            timeout=FETCHER_TIMEOUT
        )

        with open(LOG_FILE, 'a') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"RUN AT: {timestamp}\n")
            f.write(f"{'='*60}\n")
            f.write(result.stdout)
            if result.stderr:
                f.write(f"\nERRORS:\n{result.stderr}")
            f.write(f"\nEXIT CODE: {result.returncode}\n")

        if result.returncode != 0:
            print(f"⚠️  Fetcher exited {result.returncode} at {datetime.now().strftime('%H:%M:%S')}")
        else:
            print(f"✅ Fetcher completed at {datetime.now().strftime('%H:%M:%S')}")

    except subprocess.TimeoutExpired:
        print(f"⚠️  Fetcher timed out after {FETCHER_TIMEOUT}s — skipping this run")
        with open(LOG_FILE, 'a') as f:
            f.write(f"\n⚠️  TIMEOUT at {timestamp} (>{FETCHER_TIMEOUT}s)\n")
    except Exception as e:
        print(f"❌ Fetcher error: {e}")
        with open(LOG_FILE, 'a') as f:
            f.write(f"\n❌ ERROR at {timestamp}: {e}\n")


def run_news_scanner():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n🔎 Running news scanner at {timestamp}...")

    try:
        result = subprocess.run(
            [sys.executable, NEWS_SCRIPT],
            capture_output=True,
            text=True,
            timeout=SCANNER_TIMEOUT
        )

        if result.returncode != 0:
            print(f"⚠️  News scanner exited {result.returncode}")
        else:
            print(f"✅ News scanner completed at {datetime.now().strftime('%H:%M:%S')}")

        if result.stderr:
            # Only print first 300 chars of stderr to avoid log spam
            snippet = result.stderr.strip()[:300]
            if snippet:
                print(f"   stderr: {snippet}")

    except subprocess.TimeoutExpired:
        print(f"⚠️  News scanner timed out after {SCANNER_TIMEOUT}s — skipping")
    except Exception as e:
        print(f"❌ News scanner error: {e}")


def main():
    from llm_client import validate_llm_config
    validate_llm_config()

    print("=" * 60)
    print("🔄 HOURLY SCHEDULER")
    print("=" * 60)
    print(f"📁 Fetcher:      {FETCHER_SCRIPT}  (timeout {FETCHER_TIMEOUT}s)")
    print(f"📁 News scanner: {NEWS_SCRIPT}  (timeout {SCANNER_TIMEOUT}s)")
    print(f"📁 Log file:     {LOG_FILE}")
    print(f"🐍 Python:       {sys.executable}")
    print("=" * 60)
    print("Press Ctrl+C to stop\n")

    # Run once immediately on startup
    print("🚀 Running initial fetch...")
    run_fetcher()
    run_news_scanner()

    while True:
        now = datetime.now()
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        seconds_to_wait = max((next_hour - now).total_seconds(), 0)

        print(f"\n⏳ Next run at {next_hour.strftime('%H:%M:%S')} ({seconds_to_wait:.0f}s from now)")
        time.sleep(seconds_to_wait)

        run_fetcher()
        run_news_scanner()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Scheduler stopped by user")

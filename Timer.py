"""
SIMPLE SCHEDULER (No external libraries)
Runs the hourly fetcher automatically.
"""

import time
import subprocess
import sys
from datetime import datetime, timedelta
import os

FETCHER_SCRIPT = "hourlyfetcher.py"
LOG_FILE = "fetcher.log"

def run_fetcher():
    """Run the hourly fetcher"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"\n{'='*60}")
    print(f"⏰ Running hourly fetch at {timestamp}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(
            [sys.executable, FETCHER_SCRIPT],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        with open(LOG_FILE, 'a') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"RUN AT: {timestamp}\n")
            f.write(f"{'='*60}\n")
            f.write(result.stdout)
            if result.stderr:
                f.write(f"\nERRORS:\n{result.stderr}")
            f.write(f"\nEXIT CODE: {result.returncode}\n")
        
        print(f"✅ Fetcher completed at {datetime.now().strftime('%H:%M:%S')}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        with open(LOG_FILE, 'a') as f:
            f.write(f"\n❌ ERROR at {timestamp}: {e}\n")

def main():
    """Main scheduler loop"""
    print("=" * 60)
    print("🔄 HOURLY SCHEDULER (Simple)")
    print("=" * 60)
    print(f"📁 Fetcher: {FETCHER_SCRIPT}")
    print(f"📁 Log file: {LOG_FILE}")
    print("=" * 60)
    print("Press Ctrl+C to stop\n")
    
    # Run once immediately
    print("🚀 Running initial fetch...")
    run_fetcher()
    
    print("\n🔄 Waiting for next hour...")
    
    while True:
        # Calculate seconds until the next hour
        now = datetime.now()
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        seconds_to_wait = max((next_hour - now).total_seconds(), 0)
        
        print(f"⏳ Next run at {next_hour.strftime('%H:%M:%S')} ({seconds_to_wait:.0f} seconds from now)")
        
        # Wait until the next hour
        time.sleep(seconds_to_wait)
        
        # Run the fetcher
        run_fetcher()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Scheduler stopped by user")
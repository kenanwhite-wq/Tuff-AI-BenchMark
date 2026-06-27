"""
HOURLY LEADERBOARD FETCHER
Fetches all configured leaderboards, detects changes, saves snapshots,
and generates feed entries.

Imports everything from config.py - no duplicate code!
"""

import sys
import traceback
import datetime

print("🚀 Starting hourly fetcher...")
print(f"Python version: {sys.version}")

# ============================================
# IMPORT WITH ERROR HANDLING
# ============================================

print("\n📦 Attempting imports...")

try:
    import requests
    print("  ✅ requests imported")
except ImportError:
    print("  ❌ requests not found. Installing...")
    import subprocess
    subprocess.check_call(["pip3", "install", "requests"])
    import requests
    print("  ✅ requests installed")

try:
    import pandas as pd
    print("  ✅ pandas imported")
except ImportError:
    print("  ❌ pandas not found. Installing...")
    import subprocess
    subprocess.check_call(["pip", "install", "pandas"])
    import pandas as pd
    print("  ✅ pandas installed")

try:
    import numpy as np
    print("  ✅ numpy imported")
except ImportError:
    print("  ❌ numpy not found. Installing...")
    import subprocess
    subprocess.check_call(["pip", "install", "numpy"])
    import numpy as np
    print("  ✅ numpy installed")

try:
    from huggingface_hub import HfApi, hf_hub_download
    print("  ✅ huggingface_hub imported")
except ImportError:
    print("  ❌ huggingface_hub not found. Installing...")
    import subprocess
    subprocess.check_call(["pip", "install", "huggingface-hub"])
    from huggingface_hub import HfApi, hf_hub_download
    print("  ✅ huggingface_hub installed")

# ============================================
# IMPORT CONFIG
# ============================================

print("\n📋 Importing config...")

try:
    from config import (
        SOURCES,
        PARSER_MAP,
        DB_NAME,
        SNAPSHOTS_TABLE,
        FEED_TABLE,
        RANK_CHANGE_BIG,
        SCORE_SHIFT_THRESHOLD,
        get_connection,
        get_previous_snapshot,
        save_snapshot,
        save_feed_entries,
        detect_changes,
        init_database
    )
    print(f"  ✅ config loaded: {len(SOURCES)} sources, {len(PARSER_MAP)} parsers")
except Exception as e:
    print(f"  ❌ Error importing config: {e}")
    print("\nFull error:")
    traceback.print_exc()
    sys.exit(1)

# ============================================
# FETCH FUNCTION
# ============================================

def fetch_source(source_config):
    """
    Fetch a single source using its configured parser.
    Returns DataFrame or None if error.
    """
    name = source_config["name"]
    url = source_config.get("url")
    parser_name = source_config["parser_name"]
    description = source_config.get("description", "")
    
    # Get the parser function from the map
    parser = PARSER_MAP.get(parser_name)
    
    if parser is None:
        print(f"  ❌ Unknown parser: {parser_name}")
        return None
    
    try:
        # If url is None or the parser handles its own authenticated requests,
        # call the parser directly with no response argument
        if url is None or source_config.get('self_fetch', False):
            df = parser()
        else:
            # Fetch from URL
            print(f"  📥 Fetching: {url}")
            response = requests.get(url, timeout=15)

            if response.status_code != 200:
                print(f"  ❌ Error {response.status_code}: {response.text[:100]}")
                return None

            # Parse the response
            df = parser(response)
        
        if df is None or df.empty:
            print(f"  ❌ Parser returned no data")
            return None
        
        # Ensure we have required columns
        if 'model' not in df.columns:
            print(f"  ❌ No 'model' column found")
            print(f"  Available columns: {df.columns.tolist()}")
            return None
        
        if 'score' not in df.columns:
            print(f"  ❌ No 'score' column found")
            print(f"  Available columns: {df.columns.tolist()}")
            return None
        
        print(f"  ✅ Fetched {len(df)} models")
        return df
        
    except requests.exceptions.Timeout:
        print(f"  ❌ Timeout error")
        return None
    except requests.exceptions.ConnectionError:
        print(f"  ❌ Connection error")
        return None
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None

# ============================================
# PROCESS SOURCE
# ============================================

def process_source(source_config):
    """
    Process a single source:
    1. Fetch data
    2. Compare with previous snapshot
    3. Detect changes
    4. Save feed entries
    5. Save new snapshot
    """
    name = source_config["name"]
    description = source_config.get("description", "")
    
    print(f"\n📊 Processing: {name}")
    print(f"   Description: {description}")
    
    # Step 1: Fetch data
    df = fetch_source(source_config)
    if df is None or df.empty:
        print(f"  ⚠️ Skipping {name} - no data")
        return False
    
    # Step 2: Get previous snapshot
    try:
        previous_df = get_previous_snapshot(name)
    except Exception as e:
        print(f"  ⚠️ Could not get previous snapshot: {e}")
        previous_df = None
    
    # Step 3: Detect changes
    if previous_df is not None and not previous_df.empty:
        try:
            changes = detect_changes(df, previous_df, name)
        except Exception as e:
            print(f"  ⚠️ Error detecting changes: {e}")
            changes = []
        
        if changes:
            print(f"  🔍 Detected {len(changes)} changes:")
            for change in changes:
                tier_emoji = "🔴" if change.get('tier') == 'big' else "🟡" if change.get('tier') == 'moderate' else "🟢"
                headline = change.get('headline', 'Unknown change')
                print(f"     {tier_emoji} {headline}")
            
            # Step 4: Save feed entries
            try:
                save_feed_entries(changes)
            except Exception as e:
                print(f"  ⚠️ Error saving feed entries: {e}")
        else:
            print(f"  ✅ No changes detected")
    else:
        print(f"  ℹ️ First run - no previous snapshot to compare")
    
    # Step 5: Save snapshot (always save)
    try:
        save_snapshot(name, df)
    except Exception as e:
        print(f"  ⚠️ Error saving snapshot: {e}")
        return False
    
    return True

# ============================================
# MAIN
# ============================================

def main():
    """Main execution"""
    print("=" * 60)
    print("🔄 HOURLY LEADERBOARD FETCHER")
    print("=" * 60)
    print(f"🕐 Started at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Database: {DB_NAME}")
    print(f"📋 Sources to fetch: {len(SOURCES)}")
    
    # Ensure database is initialized
    try:
        init_database()
        print("✅ Database initialized")
    except Exception as e:
        print(f"⚠️ Database init warning: {e}")
    
    # Process each source
    successful = 0
    for source in SOURCES:
        if process_source(source):
            successful += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ COMPLETE!")
    print(f"   ✅ Successful: {successful}/{len(SOURCES)}")
    print(f"   📁 Database: {DB_NAME}")
    print("=" * 60)
    
    # Show recent feed entries
    try:
        conn = get_connection()
        df_feed = pd.read_sql_query(
            f"""
            SELECT id, source, model, tier, headline, status, created_at 
            FROM {FEED_TABLE} 
            ORDER BY created_at DESC 
            LIMIT 5
            """,
            conn
        )
        conn.close()
        
        if not df_feed.empty:
            print("\n📰 Most recent feed entries:")
            for _, row in df_feed.iterrows():
                tier_emoji = "🔴" if row['tier'] == 'big' else "🟡" if row['tier'] == 'moderate' else "🟢"
                status_str = "✅" if row['status'] == 'approved' else "📝" if row['status'] == 'draft' else "❌"
                print(f"   {tier_emoji} [{status_str}] {row['headline'][:60]}...")
        else:
            print("\n📰 No feed entries yet.")
            
    except Exception as e:
        print(f"\n⚠️ Could not preview feed: {e}")

# ============================================
# RUN THE SCRIPT
# ============================================

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        traceback.print_exc()
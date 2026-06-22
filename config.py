"""
CONFIGURATION AND PARSERS
Single source of truth for all scripts.
Everything imports from here.
"""

import pandas as pd
import sqlite3
import requests
import numpy as np
from datetime import datetime, timedelta
import time
import os
import json

# ============================================
# DATABASE CONFIGURATION
# ============================================

DB_NAME = "benchmark.db"

# Table names
SNAPSHOTS_TABLE = "snapshots"
FEED_TABLE = "feed_entries"
CHANGELOG_TABLE = "changelog"
COMPOSITE_TABLE = "composite_scores"

# ============================================
# THRESHOLDS
# ============================================

RANK_CHANGE_BIG = 5          # 5+ rank change = big tier
SCORE_SHIFT_THRESHOLD = 5.0  # 5+ point shift = small tier
STALENESS_DAYS = 7           # Days without update = stale
SATURATION_MARGIN = 5.0      # Points difference for saturation

# ============================================
# Hugging Face Hub (auto-install if missing)
# ============================================

try:
    from huggingface_hub import HfApi, hf_hub_download
except ImportError:
    print("📦 huggingface-hub not found. Installing...")
    import subprocess
    subprocess.check_call(["pip", "install", "huggingface-hub"])
    from huggingface_hub import HfApi, hf_hub_download

# ============================================
# PARSER FUNCTIONS
# ============================================

def parse_lmaena_format(response):
    """
    Parser for LMArena API (wulong format)
    Returns DataFrame with 'model' and 'score' columns
    """
    try:
        data = response.json()
        models = data.get("models", [])
        if not models:
            return None
        
        df = pd.DataFrame(models)
        
        # Standardize column names
        if 'score' not in df.columns and 'elo' in df.columns:
            df = df.rename(columns={'elo': 'score'})
        if 'rank' not in df.columns and 'rank' in data:
            df['rank'] = range(1, len(df) + 1)
        
        # Ensure we have the required columns
        if 'model' not in df.columns or 'score' not in df.columns:
            print(f"  ❌ Missing required columns. Found: {df.columns.tolist()}")
            return None
        
        # Keep only the columns we need
        keep_cols = ['model', 'score']
        if 'rank' in df.columns:
            keep_cols.append('rank')
        if 'vendor' in df.columns:
            keep_cols.append('vendor')
        if 'votes' in df.columns:
            keep_cols.append('votes')
        if 'ci' in df.columns:
            keep_cols.append('ci')
        
        df = df[keep_cols]
        
        return df
    except Exception as e:
        print(f"  ❌ Error parsing LMArena data: {e}")
        return None

def parse_mmlu_pro_leaderboard(response=None):
    """
    Parser for MMLU-Pro leaderboard from Hugging Face dataset
    Returns DataFrame with 'model' and 'score' columns
    """
    print("  📥 Fetching MMLU-Pro leaderboard from Hugging Face...")
    
    try:
        # Download the CSV from the dataset that powers the official leaderboard
        csv_path = hf_hub_download(
            repo_id="TIGER-Lab/mmlu_pro_leaderboard_submission",
            filename="results.csv",
            repo_type="dataset"
        )
        
        # Read the CSV
        df = pd.read_csv(csv_path)
        print(f"  ✅ Read CSV with {len(df)} rows")
        
        # Find the right columns
        model_col = None
        score_col = None
        
        # Try to find the model column
        for col in ['Models', 'Model', 'model', 'Model Name', 'name', 'model_name']:
            if col in df.columns:
                model_col = col
                break
        
        # Try to find the score column (Overall score is the main one)
        for col in ['Overall', 'Score', 'score', 'Accuracy', 'acc', 'average']:
            if col in df.columns:
                score_col = col
                break
        
        if model_col is None or score_col is None:
            print(f"  ❌ Could not find required columns. Available: {df.columns.tolist()}")
            return None
        
        print(f"  📊 Using columns: model='{model_col}', score='{score_col}'")
        
        # Create a clean DataFrame
        df_clean = pd.DataFrame({
            'model': df[model_col],
            'score': df[score_col]
        })
        
        # Remove any rows with missing values
        df_clean = df_clean.dropna()
        
        # Convert score to float (handle percentages and decimals)
        def convert_score(val):
            if isinstance(val, (int, float)):
                if 0 <= val <= 1:
                    return val * 100
                return val
            elif isinstance(val, str):
                val = val.replace('%', '').strip()
                try:
                    num = float(val)
                    if 0 <= num <= 1:
                        return num * 100
                    return num
                except:
                    return None
            return None
        
        df_clean['score'] = df_clean['score'].apply(convert_score)
        df_clean = df_clean.dropna()
        
        # Add rank
        df_clean = df_clean.sort_values('score', ascending=False)
        df_clean['rank'] = range(1, len(df_clean) + 1)
        
        print(f"  ✅ Parsed {len(df_clean)} models with valid scores")
        print(f"  📊 Score range: {df_clean['score'].min():.1f} - {df_clean['score'].max():.1f}")
        
        return df_clean
        
    except Exception as e:
        print(f"  ❌ Error fetching MMLU-Pro data: {e}")
        return None

def parse_swebench_format(response=None):
    """
    Parser for SWE-bench Verified leaderboard using Hugging Face Hub API
    Returns DataFrame with 'model' and 'score' columns
    """
    print("  📥 Fetching SWE-bench Verified leaderboard from Hugging Face...")
    
    try:
        api = HfApi()
        
        # Get the leaderboard entries for the SWE-bench Verified dataset
        leaderboard_entries = api.get_dataset_leaderboard("SWE-bench/SWE-bench_Verified")
        
        if not leaderboard_entries:
            print("  ❌ No leaderboard entries found")
            return None
        
        # Convert to a list of dictionaries
        data = []
        for entry in leaderboard_entries:
            # The entry object has these attributes:
            # - model_id: Full model ID (e.g., "Qwen/Qwen2.5-Coder-7B")
            # - value: The benchmark score (as a float)
            # - rank: Position on the leaderboard
            # - verified: Whether the result has been independently verified
            # - source: Where the result was submitted from
            
            # The value is typically a decimal (e.g., 0.62 for 62% pass rate)
            # Multiply by 100 to put it on a 0-100 scale
            score = float(entry.value) * 100 if hasattr(entry, 'value') else None
            
            if score is None:
                continue
                
            data.append({
                'model': entry.model_id if hasattr(entry, 'model_id') else 'Unknown',
                'score': score,
                'rank': entry.rank if hasattr(entry, 'rank') else len(data) + 1,
                'verified': entry.verified if hasattr(entry, 'verified') else None,
                'source': entry.source if hasattr(entry, 'source') else None
            })
        
        if not data:
            print("  ❌ No valid entries found")
            return None
        
        df = pd.DataFrame(data)
        print(f"  ✅ Fetched {len(df)} models")
        print(f"  📊 Score range: {df['score'].min():.1f} - {df['score'].max():.1f}")
        
        # Sort by score descending (highest first) for consistency
        df = df.sort_values('score', ascending=False)
        
        # Return only the columns needed for normalization
        return df[['model', 'score', 'rank']]
        
    except AttributeError as e:
        # This might happen if the API structure is different than expected
        print(f"  ❌ API structure error: {e}")
        print("  🔄 Trying fallback method...")
        return parse_swebench_fallback()
        
    except Exception as e:
        print(f"  ❌ Error fetching SWE-bench data: {e}")
        return None

def parse_swebench_fallback():
    """
    Fallback parser for SWE-bench using the Hugging Face dataset directly.
    Used if the Hub API method fails.
    """
    try:
        # Alternative method: Download the dataset's leaderboard file
        csv_path = hf_hub_download(
            repo_id="SWE-bench/SWE-bench_Verified",
            filename="leaderboard.csv",
            repo_type="dataset"
        )
        
        df = pd.read_csv(csv_path)
        print(f"  ✅ Read CSV with {len(df)} rows")
        
        # Find the right columns
        model_col = None
        score_col = None
        
        for col in ['model', 'model_id', 'model_name', 'Name', 'Model']:
            if col in df.columns:
                model_col = col
                break
        
        for col in ['score', 'value', 'accuracy', 'pass_rate', 'resolved']:
            if col in df.columns:
                score_col = col
                break
        
        if model_col is None or score_col is None:
            print(f"  ❌ Could not find required columns. Available: {df.columns.tolist()}")
            return None
        
        # Clean up
        df_clean = pd.DataFrame({
            'model': df[model_col],
            'score': df[score_col]
        })
        
        df_clean = df_clean.dropna()
        
        # Convert to 0-100 if needed
        if df_clean['score'].max() <= 1:
            df_clean['score'] = df_clean['score'] * 100
        
        df_clean = df_clean.sort_values('score', ascending=False)
        df_clean['rank'] = range(1, len(df_clean) + 1)
        
        print(f"  ✅ Parsed {len(df_clean)} models")
        print(f"  📊 Score range: {df_clean['score'].min():.1f} - {df_clean['score'].max():.1f}")
        
        return df_clean[['model', 'score', 'rank']]
        
    except Exception as e:
        print(f"  ❌ Fallback method also failed: {e}")
        return None

def parse_gaia_format(response=None):
    """
    Parser for GAIA leaderboard
    Placeholder - to be implemented when data source is found
    """
    print("  ⚠️ GAIA parser not yet implemented")
    return None

def parse_gpqa_format(response=None):
    """
    Parser for GPQA Diamond leaderboard
    Placeholder - to be implemented when data source is found
    """
    print("  ⚠️ GPQA parser not yet implemented")
    return None

def parse_humanitys_last_exam_format(response=None):
    """
    Parser for Humanity's Last Exam leaderboard
    Placeholder - to be implemented when data source is found
    """
    print("  ⚠️ Humanity's Last Exam parser not yet implemented")
    return None

def parse_aime_format(response=None):
    """
    Parser for AIME 2025 leaderboard
    Placeholder - to be implemented when data source is found
    """
    print("  ⚠️ AIME parser not yet implemented")
    return None

def parse_livecodebench_format(response=None):
    """
    Parser for LiveCodeBench leaderboard
    Placeholder - to be implemented when data source is found
    """
    print("  ⚠️ LiveCodeBench parser not yet implemented")
    return None

def parse_aider_polyglot_format(response=None):
    """
    Parser for Aider Polyglot leaderboard
    Placeholder - to be implemented when data source is found
    """
    print("  ⚠️ Aider Polyglot parser not yet implemented")
    return None

def parse_terminal_bench_format(response=None):
    """
    Parser for Terminal-Bench leaderboard
    Placeholder - to be implemented when data source is found
    """
    print("  ⚠️ Terminal-Bench parser not yet implemented")
    return None

def parse_osworld_format(response=None):
    """
    Parser for OSWorld leaderboard
    Placeholder - to be implemented when data source is found
    """
    print("  ⚠️ OSWorld parser not yet implemented")
    return None

def parse_webarena_format(response=None):
    """
    Parser for WebArena leaderboard
    Placeholder - to be implemented when data source is found
    """
    print("  ⚠️ WebArena parser not yet implemented")
    return None

def parse_tau2_bench_format(response=None):
    """
    Parser for Tau2-bench leaderboard
    Placeholder - to be implemented when data source is found
    """
    print("  ⚠️ Tau2-bench parser not yet implemented")
    return None

# ============================================
# NORMALIZATION FUNCTIONS
# ============================================

def normalize_minmax(df, score_col='score'):
    """Method 1: Min-Max scaling (0-100)"""
    min_val = df[score_col].min()
    max_val = df[score_col].max()
    if max_val == min_val:
        return pd.Series([50] * len(df), index=df.index)
    return (df[score_col] - min_val) / (max_val - min_val) * 100

def normalize_percentile(df, score_col='score'):
    """Method 2: Percentile ranking (0-100)"""
    scores = df[score_col].values
    def get_percentile(x):
        lower_count = np.sum(scores < x)
        tie_count = np.sum(scores == x)
        return (lower_count + 0.5 * tie_count) / len(scores) * 100
    return df[score_col].apply(get_percentile)

def normalize_zscore(df, score_col='score'):
    """Method 3: Z-score mapped to 0-100"""
    scores = df[score_col].values
    mean = np.mean(scores)
    std = np.std(scores)
    if std == 0:
        return pd.Series([50] * len(df), index=df.index)
    z_scores = (scores - mean) / std
    return np.clip((z_scores + 3) / 6 * 100, 0, 100)

def apply_all_normalizations(df, score_col='score'):
    """Apply all three normalization methods"""
    df['norm_minmax'] = normalize_minmax(df, score_col)
    df['norm_percentile'] = normalize_percentile(df, score_col)
    df['norm_zscore'] = normalize_zscore(df, score_col)
    df['norm_combined'] = (df['norm_minmax'] + df['norm_percentile'] + df['norm_zscore']) / 3
    return df

# ============================================
# THE ONE SOURCE LIST
# Add new sources here and they'll be available
# to ALL scripts that import this config
# ============================================

SOURCES = [
    {
        "name": "lmaena_text",
        "url": "https://api.wulong.dev/arena-ai-leaderboards/v1/leaderboard?name=text",
        "description": "LMArena Text Leaderboard (Overall)",
        "category": "human_preference",
        "parser_name": "parse_lmaena_format"
    },
    {
        "name": "mmlu_pro",
        "url": None,
        "description": "MMLU-Pro Leaderboard (Reasoning/Knowledge)",
        "category": "reasoning_knowledge",
        "parser_name": "parse_mmlu_pro_leaderboard"
    },
    {
        "name": "swe_bench",
        "url": None,
        "description": "SWE-bench Verified Leaderboard (Coding)",
        "category": "coding",
        "parser_name": "parse_swebench_format"
    },
    # ============================================
    # LMArena Sub-Categories (already working)
    # ============================================
    # Uncomment these to add them:
    # {
    #     "name": "lmaena_code",
    #     "url": "https://api.wulong.dev/arena-ai-leaderboards/v1/leaderboard?name=code",
    #     "description": "LMArena Coding Leaderboard",
    #     "category": "coding",
    #     "parser_name": "parse_lmaena_format"
    # },
    # {
    #     "name": "lmaena_vision",
    #     "url": "https://api.wulong.dev/arena-ai-leaderboards/v1/leaderboard?name=vision",
    #     "description": "LMArena Vision Leaderboard",
    #     "category": "vision",
    #     "parser_name": "parse_lmaena_format"
    # },
    # {
    #     "name": "lmaena_hard",
    #     "url": "https://api.wulong.dev/arena-ai-leaderboards/v1/leaderboard?name=hard",
    #     "description": "LMArena Hard Prompts Leaderboard",
    #     "category": "human_preference",
    #     "parser_name": "parse_lmaena_format"
    # },
    # ============================================
    # Future Sources (parsers placeholders above)
    # ============================================
    # {
    #     "name": "gaia",
    #     "url": None,
    #     "description": "GAIA Leaderboard (Agentic/Tool-Use)",
    #     "category": "agentic",
    #     "parser_name": "parse_gaia_format"
    # },
    # {
    #     "name": "gpqa_diamond",
    #     "url": None,
    #     "description": "GPQA Diamond Leaderboard (Reasoning/Knowledge)",
    #     "category": "reasoning_knowledge",
    #     "parser_name": "parse_gpqa_format"
    # },
    # {
    #     "name": "humanitys_last_exam",
    #     "url": None,
    #     "description": "Humanity's Last Exam Leaderboard (Reasoning/Knowledge)",
    #     "category": "reasoning_knowledge",
    #     "parser_name": "parse_humanitys_last_exam_format"
    # },
    # {
    #     "name": "aime_2025",
    #     "url": None,
    #     "description": "AIME 2025 Leaderboard (Reasoning/Knowledge)",
    #     "category": "reasoning_knowledge",
    #     "parser_name": "parse_aime_format"
    # },
    # {
    #     "name": "livecodebench",
    #     "url": None,
    #     "description": "LiveCodeBench Leaderboard (Coding)",
    #     "category": "coding",
    #     "parser_name": "parse_livecodebench_format"
    # },
    # {
    #     "name": "aider_polyglot",
    #     "url": None,
    #     "description": "Aider Polyglot Leaderboard (Coding)",
    #     "category": "coding",
    #     "parser_name": "parse_aider_polyglot_format"
    # },
    # {
    #     "name": "terminal_bench",
    #     "url": None,
    #     "description": "Terminal-Bench Leaderboard (Coding)",
    #     "category": "coding",
    #     "parser_name": "parse_terminal_bench_format"
    # },
    # {
    #     "name": "osworld",
    #     "url": None,
    #     "description": "OSWorld Leaderboard (Agentic/Tool-Use)",
    #     "category": "agentic",
    #     "parser_name": "parse_osworld_format"
    # },
    # {
    #     "name": "webarena",
    #     "url": None,
    #     "description": "WebArena Leaderboard (Agentic/Tool-Use)",
    #     "category": "agentic",
    #     "parser_name": "parse_webarena_format"
    # },
    # {
    #     "name": "tau2_bench",
    #     "url": None,
    #     "description": "Tau2-bench Leaderboard (Agentic/Tool-Use)",
    #     "category": "agentic",
    #     "parser_name": "parse_tau2_bench_format"
    # },
]

# ============================================
# PARSER MAP (lookup table for dynamic loading)
# ============================================

PARSER_MAP = {
    'parse_lmaena_format': parse_lmaena_format,
    'parse_mmlu_pro_leaderboard': parse_mmlu_pro_leaderboard,
    'parse_swebench_format': parse_swebench_format,
    'parse_swebench_fallback': parse_swebench_fallback,
    'parse_gaia_format': parse_gaia_format,
    'parse_gpqa_format': parse_gpqa_format,
    'parse_humanitys_last_exam_format': parse_humanitys_last_exam_format,
    'parse_aime_format': parse_aime_format,
    'parse_livecodebench_format': parse_livecodebench_format,
    'parse_aider_polyglot_format': parse_aider_polyglot_format,
    'parse_terminal_bench_format': parse_terminal_bench_format,
    'parse_osworld_format': parse_osworld_format,
    'parse_webarena_format': parse_webarena_format,
    'parse_tau2_bench_format': parse_tau2_bench_format,
}

# ============================================
# DATABASE UTILITIES (UPDATED - Option 1)
# ============================================

def get_connection():
    """Get database connection"""
    return sqlite3.connect(DB_NAME)

def get_previous_snapshot(source_name):
    """Get the most recent snapshot for a source"""
    conn = get_connection()
    try:
        df = pd.read_sql_query(
            f"SELECT * FROM {SNAPSHOTS_TABLE} WHERE source = '{source_name}' ORDER BY snapshot_timestamp DESC LIMIT 1",
            conn
        )
        conn.close()
        return df if not df.empty else None
    except Exception as e:
        conn.close()
        return None

# ============================================
# CHANGED: save_snapshot() now includes normalization
# ============================================

def save_snapshot(source_name, df):
    """
    Save a snapshot with timestamp AND normalized scores.
    This is the single source of truth for all normalized data.
    Applies all three normalization methods before saving.
    """
    conn = get_connection()
    df_copy = df.copy()
    
    # ← NEW: Apply normalizations before saving
    df_copy = apply_all_normalizations(df_copy, 'score')
    
    # Add metadata
    df_copy['snapshot_timestamp'] = datetime.now().isoformat()
    df_copy['source'] = source_name
    
    # Save to snapshots table
    df_copy.to_sql(SNAPSHOTS_TABLE, conn, if_exists='append', index=False)
    conn.close()
    print(f"  💾 Saved snapshot to {SNAPSHOTS_TABLE} (raw + normalized)")

# ============================================
# NEW: get_latest_normalized() - Easy access to normalized data
# ============================================

def get_latest_normalized(source_name=None, limit=100):
    """
    Get the most recent normalized scores for a source.
    If source_name is None, returns all sources.
    """
    conn = get_connection()
    
    if source_name:
        query = f"""
            SELECT source, model, score, rank, 
                   norm_minmax, norm_percentile, norm_zscore, norm_combined,
                   snapshot_timestamp
            FROM {SNAPSHOTS_TABLE} 
            WHERE source = '{source_name}'
            ORDER BY snapshot_timestamp DESC 
            LIMIT {limit}
        """
    else:
        query = f"""
            SELECT source, model, score, rank, 
                   norm_minmax, norm_percentile, norm_zscore, norm_combined,
                   snapshot_timestamp
            FROM {SNAPSHOTS_TABLE} 
            ORDER BY snapshot_timestamp DESC 
            LIMIT {limit}
        """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# ============================================
# NEW: get_composite_scores() - Calculate composite across sources
# ============================================

def get_composite_scores(weights=None):
    """
    Calculate composite scores across all sources.
    weights: dict like {'lmaena_text': 0.4, 'mmlu_pro': 0.3, 'swe_bench': 0.3}
    If None, uses equal weights.
    """
    if weights is None:
        # Default: equal weights for all active sources
        active_sources = [s['name'] for s in SOURCES]
        equal_weight = 1.0 / len(active_sources)
        weights = {source: equal_weight for source in active_sources}
    
    conn = get_connection()
    
    # Get latest snapshot for each source
    all_scores = {}
    for source in weights.keys():
        df = pd.read_sql_query(
            f"""
            SELECT model, norm_combined as score
            FROM {SNAPSHOTS_TABLE}
            WHERE source = '{source}'
            ORDER BY snapshot_timestamp DESC
            LIMIT 100
            """,
            conn
        )
        if not df.empty:
            all_scores[source] = df
    
    conn.close()
    
    if not all_scores:
        return pd.DataFrame()
    
    # Get all unique models
    all_models = set()
    for df in all_scores.values():
        all_models.update(df['model'].tolist())
    
    composites = []
    for model in all_models:
        total = 0
        weight_sum = 0
        sources_found = []
        
        for source, df in all_scores.items():
            score_row = df[df['model'] == model]
            if not score_row.empty:
                total += score_row.iloc[0]['score'] * weights[source]
                weight_sum += weights[source]
                sources_found.append(source)
        
        if weight_sum > 0:
            composites.append({
                'model': model,
                'composite_score': total / weight_sum,
                'sources_available': len(sources_found),
                'sources_list': ', '.join(sources_found)
            })
    
    return pd.DataFrame(composites).sort_values('composite_score', ascending=False)

# ============================================
# EXISTING FUNCTIONS (unchanged)
# ============================================

def save_feed_entries(changes):
    """Save feed entries to database"""
    if not changes:
        return
    
    conn = get_connection()
    df = pd.DataFrame(changes)
    df['status'] = 'draft'
    df['created_at'] = datetime.now().isoformat()
    
    cols = ['model', 'source', 'tier', 'type', 'headline', 'body', 'status', 'created_at']
    for col in cols:
        if col not in df.columns:
            df[col] = None
    
    df[cols].to_sql(FEED_TABLE, conn, if_exists='append', index=False)
    conn.close()
    print(f"  💾 Saved {len(changes)} feed entries to {FEED_TABLE}")

def get_unapproved_feed_entries():
    """Get all draft feed entries"""
    conn = get_connection()
    df = pd.read_sql_query(
        f"SELECT * FROM {FEED_TABLE} WHERE status = 'draft' ORDER BY created_at DESC",
        conn
    )
    conn.close()
    return df

def approve_feed_entry(entry_id):
    """Approve a feed entry"""
    conn = get_connection()
    conn.execute(
        f"UPDATE {FEED_TABLE} SET status = 'approved', approved_at = ? WHERE id = ?",
        (datetime.now().isoformat(), entry_id)
    )
    conn.commit()
    conn.close()

def save_changelog_entry(entry):
    """Save a methodology changelog entry"""
    conn = get_connection()
    df = pd.DataFrame([entry])
    df['created_at'] = datetime.now().isoformat()
    df.to_sql(CHANGELOG_TABLE, conn, if_exists='append', index=False)
    conn.close()

def init_database():
    """Initialize all tables if they don't exist"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Snapshots table (now with normalized columns)
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {SNAPSHOTS_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            model TEXT,
            score REAL,
            rank INTEGER,
            vendor TEXT,
            votes INTEGER,
            ci TEXT,
            norm_minmax REAL,
            norm_percentile REAL,
            norm_zscore REAL,
            norm_combined REAL,
            snapshot_timestamp TEXT,
            source_name TEXT
        )
    ''')
    
    # Feed entries table
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {FEED_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model TEXT,
            source TEXT,
            tier TEXT,
            type TEXT,
            headline TEXT,
            body TEXT,
            status TEXT,
            created_at TEXT,
            approved_at TEXT
        )
    ''')
    
    # Changelog table
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {CHANGELOG_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            type TEXT,
            reason TEXT,
            status TEXT,
            created_at TEXT
        )
    ''')
    
    # Composite scores table
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {COMPOSITE_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model TEXT,
            composite_score REAL,
            norm_minmax REAL,
            norm_percentile REAL,
            norm_zscore REAL,
            norm_combined REAL,
            updated_at TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized with all tables")

# ============================================
# CHANGE DETECTION (unchanged)
# ============================================

def detect_changes(current_df, previous_df, source_name):
    """
    Detect changes between two snapshots.
    Returns list of changes.
    """
    if previous_df is None or previous_df.empty:
        # First run - no changes to detect
        return []
    
    changes = []
    
    # Create dictionaries for easy lookup
    current_models = set(current_df['model'])
    previous_models = set(previous_df['model'])
    
    # 1. Check for new models
    new_models = current_models - previous_models
    for model in new_models:
        changes.append({
            'type': 'new_model',
            'model': model,
            'source': source_name,
            'tier': 'moderate',
            'headline': f"New model appears on {source_name}: {model}",
            'body': f"{model} has been added to the {source_name} leaderboard."
        })
    
    # 2. Check for rank changes (if rank column exists)
    if 'rank' in current_df.columns and 'rank' in previous_df.columns:
        current_rank = dict(zip(current_df['model'], current_df['rank']))
        previous_rank = dict(zip(previous_df['model'], previous_df['rank']))
        
        for model in current_models.intersection(previous_models):
            rank_change = previous_rank.get(model, 0) - current_rank.get(model, 0)
            if rank_change != 0:
                tier = 'big' if abs(rank_change) >= RANK_CHANGE_BIG else 'moderate'
                direction = "up" if rank_change > 0 else "down"
                changes.append({
                    'type': 'rank_change',
                    'model': model,
                    'source': source_name,
                    'tier': tier,
                    'change': rank_change,
                    'old_rank': previous_rank.get(model),
                    'new_rank': current_rank.get(model),
                    'headline': f"{model} moves {direction} {abs(rank_change)} spots on {source_name}",
                    'body': f"{model} moved from #{previous_rank.get(model)} to #{current_rank.get(model)} on the {source_name} leaderboard."
                })
    
    # 3. Check for score shifts (small tier)
    current_score = dict(zip(current_df['model'], current_df['score']))
    previous_score = dict(zip(previous_df['model'], previous_df['score']))
    
    for model in current_models.intersection(previous_models):
        score_shift = current_score.get(model, 0) - previous_score.get(model, 0)
        # If it's a significant shift but no rank change (or we already have a rank change)
        if abs(score_shift) > SCORE_SHIFT_THRESHOLD:
            # Check if we already have a rank change for this model
            has_rank_change = any(c['model'] == model and c['type'] == 'rank_change' for c in changes)
            if not has_rank_change:
                direction = "up" if score_shift > 0 else "down"
                changes.append({
                    'type': 'score_shift',
                    'model': model,
                    'source': source_name,
                    'tier': 'small',
                    'change': score_shift,
                    'old_score': previous_score.get(model),
                    'new_score': current_score.get(model),
                    'headline': f"{model} score changes by {abs(score_shift):.1f} points on {source_name}",
                    'body': f"{model}'s score on {source_name} shifted from {previous_score.get(model, 0):.1f} to {current_score.get(model, 0):.1f}."
                })
    
    return changes

# ============================================
# PRINT SUMMARY
# ============================================

print("=" * 60)
print("📋 CONFIG LOADED")
print("=" * 60)
print(f"   Database: {DB_NAME}")
print(f"   Sources: {len(SOURCES)} configured")
print(f"   Parsers: {len(PARSER_MAP)} available")
print(f"   Tables: {SNAPSHOTS_TABLE}, {FEED_TABLE}, {CHANGELOG_TABLE}, {COMPOSITE_TABLE}")
print("   ✅ Normalization enabled on snapshots (Option 1)")
print("=" * 60)
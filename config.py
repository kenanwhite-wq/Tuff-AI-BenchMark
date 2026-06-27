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
import re

# ============================================
# DATABASE CONFIGURATION
# ============================================

DB_NAME = "benchmark.db"

# Table names
SNAPSHOTS_TABLE = "snapshots"
FEED_TABLE = "feed_entries"
NEWS_ITEMS_TABLE = "news_items"
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
# MODEL NAME NORMALIZATION
# ============================================

def normalize_model_name(name):
    if not name or not isinstance(name, str):
        return name
    
    original = name.strip()
    name = name.lower().strip()

    # Strip owner prefixes like 'openai/' or 'qwen/' so normalization is consistent.
    if '/' in name:
        name = name.split('/')[-1]
    
    # Explicit mappings - if we recognize it, return clean canonical name
    mappings = {
        'GPT-4o':              ['gpt-4o', 'gpt4o', 'gpt-4o-2024'],
        'GPT-4 Turbo':         ['gpt-4-turbo', 'gpt4-turbo'],
        'GPT-4.5':             ['gpt-4.5', 'gpt-4.5-preview'],
        'GPT-5':               ['gpt-5', 'gpt5'],
        'GPT-3.5 Turbo':       ['gpt-3.5-turbo', 'gpt-35-turbo'],
        'o1':                  ['openai o1', 'o1-preview', 'o1-mini'],
        'o3':                  ['openai o3', 'o3-mini'],
        'o4-mini':             ['o4-mini', 'openai o4-mini'],

        'Claude 3.5 Sonnet':   ['claude-3.5-sonnet', 'claude-3-5-sonnet', 'claude-3.5-sonnet-2024'],
        'Claude 3.5 Haiku':    ['claude-3.5-haiku', 'claude-3-5-haiku'],
        'Claude 3 Opus':       ['claude-3-opus', 'claude-3.0-opus'],
        'Claude 3 Sonnet':     ['claude-3-sonnet', 'claude-3.0-sonnet'],
        'Claude 3 Haiku':      ['claude-3-haiku', 'claude-3.0-haiku'],
        'Claude 3.7 Sonnet':   ['claude-3.7-sonnet', 'claude-3-7-sonnet'],
        'Claude 4 Sonnet':     ['claude-sonnet-4', 'claude-4-sonnet'],
        'Claude 4 Opus':       ['claude-opus-4', 'claude-4-opus'],

        'Gemini 2.5 Pro':      ['gemini-2.5-pro', 'gemini2.5-pro'],
        'Gemini 2.5 Flash':    ['gemini-2.5-flash', 'gemini2.5-flash'],
        'Gemini 2.0 Flash':    ['gemini-2.0-flash', 'gemini-2.0-flash-exp'],
        'Gemini 1.5 Pro':      ['gemini-1.5-pro', 'gemini-1.5-pro-002'],
        'Gemini 1.5 Flash':    ['gemini-1.5-flash', 'gemini-1.5-flash-002'],

        'DeepSeek-V3':         ['deepseek-v3', 'deepseek v3'],
        'DeepSeek-R1':         ['deepseek-r1', 'deepseek r1'],
        'DeepSeek-V2':         ['deepseek-v2', 'deepseek v2'],

        'Llama 3.1 405B':      ['llama-3.1-405b', 'meta-llama-3.1-405b'],
        'Llama 3.1 70B':       ['llama-3.1-70b', 'meta-llama-3.1-70b'],
        'Llama 3.1 8B':        ['llama-3.1-8b', 'meta-llama-3.1-8b'],
        'Llama 3 70B':         ['llama-3-70b', 'meta-llama-3-70b'],
        'Llama 3 8B':          ['llama-3-8b', 'meta-llama-3-8b'],
        'Llama 4 Scout':       ['llama-4-scout', 'llama4-scout'],
        'Llama 4 Maverick':    ['llama-4-maverick', 'llama4-maverick'],

        'Qwen3':               ['qwen3', 'qwen-3'],
        'Qwen2.5':             ['qwen2.5', 'qwen-2.5'],
        'Qwen2':               ['qwen2', 'qwen-2'],
        'QwQ':                 ['qwq', 'qwq-32b'],

        'Mistral Large':       ['mistral-large', 'mistral large'],
        'Mistral Small':       ['mistral-small', 'mistral small'],
        'Mixtral 8x7B':        ['mixtral-8x7b', 'mixtral 8x7b'],
        'Mixtral 8x22B':       ['mixtral-8x22b', 'mixtral 8x22b'],

        'Grok 3':              ['grok-3', 'grok3'],
        'Grok 2':              ['grok-2', 'grok2'],

        'Command R+':          ['command-r-plus', 'command r+'],
        'Command R':           ['command-r', 'command r'],
    }

    def variant_matches(normalized_name, variant_value):
        if normalized_name == variant_value:
            return True
        if normalized_name.startswith(variant_value + '-') or normalized_name.startswith(variant_value + '_'):
            return True
        if normalized_name.startswith(variant_value + ' '):
            return True
        if normalized_name.endswith('-' + variant_value) or normalized_name.endswith('_' + variant_value):
            return True
        if re.search(rf'(?:^|[\s\-_\/]){re.escape(variant_value)}(?:$|[\s\-_\/])', normalized_name):
            return True
        return False

    # Check mappings first - exact and partial
    for canonical, variants in mappings.items():
        for variant in variants:
            if variant_matches(name, variant):
                return canonical

    # Not in mappings - do light cleanup only, preserve the name
    # Just remove date suffixes and clean separators, nothing aggressive
    cleaned = name
    cleaned = re.sub(r'\s*\([^)]*\)', '', cleaned)
    cleaned = re.sub(r'[-_](20\d{2}[-_]?(0[1-9]|1[0-2])[-_]?(0[1-9]|[12][0-9]|3[01]))', '', cleaned)
    cleaned = re.sub(r'[-_]20\d{6}', '', cleaned)
    cleaned = re.sub(r'[-_]20\d{4}', '', cleaned)
    cleaned = re.sub(r'[-_]', ' ', cleaned)
    cleaned = cleaned.strip().title()

    return cleaned if cleaned else original

# ============================================
# DATABASE UTILITIES
# ============================================

def get_connection():
    """Get database connection"""
    return sqlite3.connect(DB_NAME)

def get_previous_snapshot(source_name):
    """
    Get the most recent FULL snapshot for a source.
    Returns ALL models from the most recent timestamp.
    FIXED: Now returns all rows, not just one.
    """
    conn = get_connection()
    try:
        # Use parameterized query to prevent SQL injection
        cursor = conn.cursor()
        
        # First, get the most recent timestamp
        timestamp_query = f"""
            SELECT MAX(snapshot_timestamp) as latest_ts
            FROM {SNAPSHOTS_TABLE}
            WHERE source = ?
        """
        cursor.execute(timestamp_query, (source_name,))
        result = cursor.fetchone()
        
        if result is None or result[0] is None:
            conn.close()
            return None
        
        latest_ts = result[0]
        
        # Then, get ALL rows for that timestamp
        query = f"""
            SELECT * FROM {SNAPSHOTS_TABLE}
            WHERE source = ? AND snapshot_timestamp = ?
        """
        df = pd.read_sql_query(query, conn, params=(source_name, latest_ts))
        conn.close()
        return df if not df.empty else None
    except Exception as e:
        conn.close()
        return None

def save_snapshot(source_name, df):
    """
    Save a snapshot with timestamp AND normalized scores.
    This is the single source of truth for all normalized data.
    Applies all three normalization methods before saving.
    """
    conn = get_connection()
    df_copy = df.copy()
    
    # Apply normalizations before saving
    df_copy = apply_all_normalizations(df_copy, 'score')
    
    # Add metadata
    df_copy['snapshot_timestamp'] = datetime.now().isoformat()
    df_copy['source'] = source_name
    
    # Save to snapshots table
    df_copy.to_sql(SNAPSHOTS_TABLE, conn, if_exists='append', index=False)
    conn.close()
    print(f"  💾 Saved snapshot to {SNAPSHOTS_TABLE} (raw + normalized)")

def get_latest_normalized(source_name=None, limit=100):
    """
    Get the most recent normalized scores for a source.
    If source_name is None, returns all sources.
    """
    conn = get_connection()
    
    if source_name:
        # Use parameterized query
        query = f"""
            SELECT source, model, score, rank, 
                   norm_minmax, norm_percentile, norm_zscore, norm_combined,
                   snapshot_timestamp
            FROM {SNAPSHOTS_TABLE} 
            WHERE source = ?
            ORDER BY snapshot_timestamp DESC 
            LIMIT ?
        """
        df = pd.read_sql_query(query, conn, params=(source_name, limit))
    else:
        query = f"""
            SELECT source, model, score, rank, 
                   norm_minmax, norm_percentile, norm_zscore, norm_combined,
                   snapshot_timestamp
            FROM {SNAPSHOTS_TABLE} 
            ORDER BY snapshot_timestamp DESC 
            LIMIT ?
        """
        df = pd.read_sql_query(query, conn, params=(limit,))
    
    conn.close()
    return df

def get_composite_scores(weights=None):
    """
    Calculate composite scores across all sources.
    Uses model name normalization to match models across different leaderboards.
    FIXED: Now uses normalized_model for matching.
    """
    if weights is None:
        active_sources = [s['name'] for s in SOURCES]
        equal_weight = 1.0 / len(active_sources)
        weights = {source: equal_weight for source in active_sources}
    
    conn = get_connection()
    
    # Get latest snapshot for each source
    all_scores = {}
    for source in weights.keys():
        # Use parameterized query to get most recent timestamp
        cursor = conn.cursor()
        timestamp_query = f"""
            SELECT MAX(snapshot_timestamp) as latest_ts
            FROM {SNAPSHOTS_TABLE}
            WHERE source = ?
        """
        cursor.execute(timestamp_query, (source,))
        result = cursor.fetchone()
        
        if result is None or result[0] is None:
            continue
            
        latest_ts = result[0]
        
        df = pd.read_sql_query(
            f"""
            SELECT model, norm_combined as score
            FROM {SNAPSHOTS_TABLE}
            WHERE source = ? AND snapshot_timestamp = ?
            """,
            conn,
            params=(source, latest_ts)
        )
        
        if not df.empty:
            # Apply model name normalization
            df['normalized_model'] = df['model'].apply(normalize_model_name)
            all_scores[source] = df
    
    conn.close()
    
    if not all_scores:
        return pd.DataFrame()
    
    # Get all unique normalized model names
    all_models = set()
    for df in all_scores.values():
        all_models.update(df['normalized_model'].tolist())
    
    composites = []
    for model in all_models:
        total = 0
        weight_sum = 0
        sources_found = []
        raw_names = []
        
        for source, df in all_scores.items():
            # Match by normalized model name
            score_row = df[df['normalized_model'] == model]
            if not score_row.empty:
                total += score_row.iloc[0]['score'] * weights[source]
                weight_sum += weights[source]
                sources_found.append(source)
                raw_names.append(f"{source}: {score_row.iloc[0]['model']}")
        
        if weight_sum > 0:
            composites.append({
                'model': model,
                'composite_score': total / weight_sum,
                'sources_available': len(sources_found),
                'sources_list': ', '.join(sources_found),
                'raw_names': ' | '.join(raw_names)
            })
    
    return pd.DataFrame(composites).sort_values('composite_score', ascending=False)

def save_feed_entries(changes):
    """Save feed entries to database"""
    if not changes:
        return
    
    conn = get_connection()
    df = pd.DataFrame(changes)
    df['status'] = 'approved'
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

# ============================================
# COMMUNITY VOTING FUNCTIONS
# ============================================

def get_elo_rating(model):
    """Get the current Elo rating for a model"""
    model = normalize_model_name(model)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT rating FROM elo_ratings WHERE model = ?", (model,))
    result = cursor.fetchone()
    conn.close()

    if result:
        return float(result[0])
    return 1200.0


def update_elo_winner(winner, loser):
    """
    Update Elo ratings after a vote.
    Standard Elo formula with K=32.
    """
    winner = normalize_model_name(winner)
    loser = normalize_model_name(loser)
    winner_rating = get_elo_rating(winner)
    loser_rating = get_elo_rating(loser)

    expected_winner = 1 / (1 + 10 ** ((loser_rating - winner_rating) / 400))
    expected_loser = 1 / (1 + 10 ** ((winner_rating - loser_rating) / 400))

    K = 32
    new_winner_rating = winner_rating + K * (1 - expected_winner)
    new_loser_rating = loser_rating + K * (0 - expected_loser)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO elo_ratings (model, rating, votes_won, votes_total, updated_at)
        VALUES (?, ?, 1, 1, ?)
        ON CONFLICT(model) DO UPDATE SET
            rating = ?,
            votes_won = votes_won + 1,
            votes_total = votes_total + 1,
            updated_at = ?
    ''', (winner, new_winner_rating, datetime.now().isoformat(), new_winner_rating, datetime.now().isoformat()))

    cursor.execute('''
        INSERT INTO elo_ratings (model, rating, votes_lost, votes_total, updated_at)
        VALUES (?, ?, 1, 1, ?)
        ON CONFLICT(model) DO UPDATE SET
            rating = ?,
            votes_lost = votes_lost + 1,
            votes_total = votes_total + 1,
            updated_at = ?
    ''', (loser, new_loser_rating, datetime.now().isoformat(), new_loser_rating, datetime.now().isoformat()))

    conn.commit()
    conn.close()

    return {
        'winner': {'model': winner, 'rating': new_winner_rating},
        'loser': {'model': loser, 'rating': new_loser_rating}
    }


def record_vote(model_a, model_b, winner, session_id=None):
    """
    Record a vote and update Elo ratings.
    Returns the updated ratings.
    """
    conn = get_connection()
    cursor = conn.cursor()
    loser = model_b if winner == model_a else model_a

    cursor.execute('''
        INSERT INTO votes (model_a, model_b, winner, session_id, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (model_a, model_b, winner, session_id, datetime.now().isoformat()))

    conn.commit()
    conn.close()

    return update_elo_winner(winner, loser)


def get_vote_pair():
    """
    Get two models to compare.
    Returns a tuple of (model_a, model_b).
    Uses the latest snapshot models and biases selection toward models with fewer votes.
    """
    conn = get_connection()
    df = pd.read_sql_query('''
        SELECT DISTINCT model
        FROM snapshots
        WHERE snapshot_timestamp = (
            SELECT MAX(snapshot_timestamp) FROM snapshots
        )
        ORDER BY model
        LIMIT 100
    ''', conn)

    if len(df) < 2:
        df = pd.read_sql_query('''
            SELECT DISTINCT model FROM snapshots
            ORDER BY snapshot_timestamp DESC
            LIMIT 100
        ''', conn)

    if len(df) < 2:
        conn.close()
        return None, None

    models = df['model'].tolist()

    cursor = conn.cursor()
    weights = []
    for model in models:
        cursor.execute("SELECT votes_total FROM elo_ratings WHERE model = ?", (model,))
        row = cursor.fetchone()
        votes_total = int(row[0]) if row else 0
        # Bias toward models with fewer votes; avoid zero weight.
        weights.append(1.0 / (votes_total + 1))

    conn.close()

    import random
    try:
        model_a = random.choices(models, weights=weights, k=1)[0]
        remaining = [m for m in models if m != model_a]
        remaining_weights = [w for m, w in zip(models, weights) if m != model_a]
        model_b = random.choices(remaining, weights=remaining_weights, k=1)[0]
    except Exception:
        model_a, model_b = random.sample(models, 2)

    return model_a, model_b


def get_community_rankings(limit=20):
    """Get the top models by community Elo rating"""
    conn = get_connection()
    df = pd.read_sql_query('''
        SELECT model, rating, votes_won, votes_lost, votes_total, updated_at
        FROM elo_ratings
        WHERE votes_total > 0
        ORDER BY rating DESC
        LIMIT ?
    ''', conn, params=(limit,))
    conn.close()
    return df


def get_vote_stats():
    """Get voting statistics"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM votes")
    total_votes = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT model) FROM elo_ratings WHERE votes_total > 0")
    total_models = cursor.fetchone()[0]
    conn.close()

    return {
        'total_votes': total_votes,
        'total_models': total_models
    }


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
    
    # Snapshots table (with normalized columns)
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

    # News items table
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {NEWS_ITEMS_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            summary TEXT,
            source_name TEXT,
            source_category TEXT,
            classification TEXT,
            created_at TEXT,
            status TEXT DEFAULT 'active'
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

    # NEW: Votes table for community voting
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_a TEXT NOT NULL,
            model_b TEXT NOT NULL,
            winner TEXT NOT NULL,
            voter_id TEXT,
            session_id TEXT,
            created_at TEXT
        )
    ''')

    # NEW: Elo ratings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS elo_ratings (
            model TEXT PRIMARY KEY,
            rating REAL DEFAULT 1200,
            votes_won INTEGER DEFAULT 0,
            votes_lost INTEGER DEFAULT 0,
            votes_total INTEGER DEFAULT 0,
            updated_at TEXT
        )
    ''')

    # NEW: Model comments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS model_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model TEXT NOT NULL,
            comment TEXT NOT NULL,
            username TEXT,
            session_id TEXT,
            parent_id INTEGER,
            likes INTEGER DEFAULT 0,
            is_approved INTEGER DEFAULT 1,
            created_at TEXT
        )
    ''')

    # NEW: Comment likes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comment_likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comment_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            created_at TEXT,
            UNIQUE(comment_id, session_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized with all tables")


def add_comment(model, comment, username=None, session_id=None, parent_id=None):
    """Add a comment to a model."""
    if not comment or len(comment.strip()) < 2:
        return {'error': 'Comment too short (minimum 2 characters)'}

    if len(comment) > 1000:
        return {'error': 'Comment too long (maximum 1000 characters)'}

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO model_comments (model, comment, username, session_id, parent_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (model, comment.strip(), username, session_id, parent_id, datetime.now().isoformat()))
    comment_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        'id': comment_id,
        'model': model,
        'comment': comment.strip(),
        'username': username or 'Anonymous',
        'created_at': datetime.now().isoformat(),
    }


def get_comments(model, limit=50):
    """Get comments for a model."""
    conn = get_connection()
    df = pd.read_sql_query('''
        SELECT id, model, comment, username, parent_id, likes, is_approved, created_at
        FROM model_comments
        WHERE model = ? AND is_approved = 1
        ORDER BY created_at DESC
        LIMIT ?
    ''', conn, params=(model, limit))
    conn.close()
    return df


def build_comment_tree(model, limit=100):
    """Build a nested comment tree for a model."""
    comments = get_comments(model, limit=limit)
    if comments.empty:
        return []

    comments = comments.copy()
    comments['replies'] = [[] for _ in range(len(comments))]
    by_id = {}
    roots = []

    for _, row in comments.iterrows():
        item = {
            'id': int(row['id']),
            'model': row['model'],
            'comment': row['comment'],
            'username': row['username'],
            'parent_id': int(row['parent_id']) if pd.notna(row['parent_id']) else None,
            'likes': int(row['likes']) if pd.notna(row['likes']) else 0,
            'is_approved': int(row['is_approved']) if pd.notna(row['is_approved']) else 1,
            'created_at': row['created_at'],
            'replies': []
        }
        by_id[item['id']] = item

    for item in by_id.values():
        if item['parent_id'] and item['parent_id'] in by_id:
            by_id[item['parent_id']]['replies'].append(item)
        else:
            roots.append(item)

    roots.sort(key=lambda item: item['created_at'], reverse=True)
    for root in roots:
        root['replies'].sort(key=lambda item: item['created_at'])

    return roots


def like_comment(comment_id, session_id):
    """Like a comment once per session."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO comment_likes (comment_id, session_id, created_at)
            VALUES (?, ?, ?)
        ''', (comment_id, session_id, datetime.now().isoformat()))
        cursor.execute('''
            UPDATE model_comments SET likes = likes + 1 WHERE id = ?
        ''', (comment_id,))
        conn.commit()
        conn.close()
        return {'success': True}
    except sqlite3.IntegrityError:
        conn.close()
        return {'error': 'Already liked'}


def unlike_comment(comment_id, session_id):
    """Remove a like from a comment."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM comment_likes WHERE comment_id = ? AND session_id = ?
    ''', (comment_id, session_id))
    cursor.execute('''
        UPDATE model_comments SET likes = likes - 1 WHERE id = ? AND likes > 0
    ''', (comment_id,))
    conn.commit()
    conn.close()
    return {'success': True}


def delete_comment(comment_id, session_id=None):
    """Delete a comment (soft delete)."""
    conn = get_connection()
    cursor = conn.cursor()
    if session_id:
        cursor.execute('''
            UPDATE model_comments SET is_approved = 0 WHERE id = ? AND session_id = ?
        ''', (comment_id, session_id))
    else:
        cursor.execute('''
            UPDATE model_comments SET is_approved = 0 WHERE id = ?
        ''', (comment_id,))
    conn.commit()
    conn.close()
    return {'success': True}

# ============================================
# CHANGE DETECTION
# ============================================

def detect_changes(current_df, previous_df, source_name):
    """
    Detect changes between two snapshots.
    Returns list of changes.
    FIXED: Now properly cleans DataFrames before comparison.
    """
    if previous_df is None or previous_df.empty:
        return []
    
    # Make copies to avoid modifying originals
    current = current_df.copy()
    previous = previous_df.copy()
    
    # Keep ONLY the columns we need for comparison
    keep_cols = ['model', 'score', 'rank']
    
    # Only keep columns that exist
    current_cols = [c for c in keep_cols if c in current.columns]
    previous_cols = [c for c in keep_cols if c in previous.columns]
    
    current = current[current_cols].copy()
    previous = previous[previous_cols].copy()
    
    # Ensure rank column exists (add if missing)
    if 'rank' not in current.columns:
        current['rank'] = range(1, len(current) + 1)
    if 'rank' not in previous.columns:
        previous['rank'] = range(1, len(previous) + 1)
    
    # Drop any rows with missing values
    current = current.dropna(subset=['model', 'score'])
    previous = previous.dropna(subset=['model', 'score'])
    
    # Ensure score is numeric
    current['score'] = pd.to_numeric(current['score'], errors='coerce')
    previous['score'] = pd.to_numeric(previous['score'], errors='coerce')
    
    # Drop rows where score conversion failed
    current = current.dropna(subset=['score'])
    previous = previous.dropna(subset=['score'])
    
    # Now do the actual detection
    changes = []
    current_models = set(current['model'])
    previous_models = set(previous['model'])
    
    # 1. New models
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
    
    # 2. Rank changes
    if 'rank' in current.columns and 'rank' in previous.columns:
        current_rank = dict(zip(current['model'], current['rank']))
        previous_rank = dict(zip(previous['model'], previous['rank']))
        
        for model in current_models.intersection(previous_models):
            if model in current_rank and model in previous_rank:
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
    
    # 3. Score shifts
    current_score = dict(zip(current['model'], current['score']))
    previous_score = dict(zip(previous['model'], previous['score']))
    
    for model in current_models.intersection(previous_models):
        if model in current_score and model in previous_score:
            score_shift = current_score.get(model, 0) - previous_score.get(model, 0)
            if abs(score_shift) > SCORE_SHIFT_THRESHOLD:
                has_rank_change = any(c['model'] == model and c['type'] == 'rank_change' for c in changes)
                if not has_rank_change:
                    direction = "up" if score_shift > 0 else "down"
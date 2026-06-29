"""
CONFIGURATION AND PARSERS
Single source of truth for all scripts.
Everything imports from here.
"""
from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
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

        # Strip trailing parenthetical suffixes: dates like (11/25), modes like
        # (Thinking), variants like (high), (BF16) — they confuse name normalization
        # and cause duplicate rows that should be the same model.
        df_clean['model'] = (
            df_clean['model']
            .str.replace(r'\s*\([^)]*\)\s*$', '', regex=True)
            .str.strip()
        )

        # After stripping, keep only the best score per model name
        df_clean = df_clean.sort_values('score', ascending=False)
        df_clean = df_clean.drop_duplicates(subset=['model'], keep='first')

        # Final rank
        df_clean = df_clean.reset_index(drop=True)
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
    Parser for Aider Polyglot leaderboard (https://aider.chat/docs/leaderboards/).
    Scrapes the HTML table, extracts model name and percent score (0-100 float).
    """
    from bs4 import BeautifulSoup

    if response is None:
        print("  ❌ Aider Polyglot parser requires an HTTP response")
        return None

    print("  📥 Parsing Aider Polyglot leaderboard HTML...")
    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = []

        for table in soup.find_all('table'):
            headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
            if not headers:
                continue

            # Locate model and score columns
            model_idx = next(
                (i for i, h in enumerate(headers) if 'model' in h or 'assistant' in h),
                None,
            )
            score_idx = next(
                (i for i, h in enumerate(headers)
                 if '%' in h or 'score' in h or 'correct' in h or 'polyglot' in h or 'percent' in h),
                None,
            )
            if model_idx is None or score_idx is None:
                continue

            for tr in table.find_all('tr')[1:]:
                cells = tr.find_all(['td', 'th'])
                if len(cells) <= max(model_idx, score_idx):
                    continue
                model_name = cells[model_idx].get_text(strip=True)
                raw_score = cells[score_idx].get_text(strip=True).replace('%', '').strip()
                try:
                    score = float(raw_score)
                    if 0.0 <= score <= 1.0:
                        score *= 100
                    rows.append({'model': model_name, 'score': score})
                except (ValueError, TypeError):
                    continue

            if rows:
                break

        if not rows:
            print("  ❌ No rows parsed from Aider Polyglot table")
            return None

        df = pd.DataFrame(rows).sort_values('score', ascending=False).reset_index(drop=True)
        df['rank'] = range(1, len(df) + 1)
        print(f"  ✅ Parsed {len(df)} models from Aider Polyglot")
        print(f"  📊 Score range: {df['score'].min():.1f} – {df['score'].max():.1f}")
        return df

    except Exception as e:
        print(f"  ❌ Error parsing Aider Polyglot: {e}")
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


def _parse_artificial_analysis_impl(field, response=None):
    """
    Fetches and parses the Artificial Analysis LLM models API.
    field: 'gpqa' | 'hle' | 'livecodebench' | 'mmlu_pro' | 'aime' | 'speed'
    Benchmark fields are on a 0-1 scale and are multiplied by 100.
    The 'speed' field uses median_output_tokens_per_second directly.
    """
    api_key = os.environ.get('ARTIFICIAL_ANALYSIS_API_KEY')
    if not api_key:
        print("  ❌ ARTIFICIAL_ANALYSIS_API_KEY not set")
        return None

    print(f"  📥 Fetching Artificial Analysis data (field: {field})...")

    try:
        resp = requests.get(
            'https://artificialanalysis.ai/api/v2/data/llms/models',
            headers={'x-api-key': api_key},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  ❌ Error fetching Artificial Analysis data: {e}")
        return None

    models_list = data.get('data', [])
    if not models_list:
        print("  ❌ No models found in Artificial Analysis response")
        return None

    rows = []
    for model in models_list:
        model_name = model.get('name') or model.get('model') or model.get('id')
        if not model_name:
            continue

        if field == 'speed':
            score = model.get('median_output_tokens_per_second')
        else:
            evaluations = model.get('evaluations', {}) or {}
            score = evaluations.get(field)

        if score is None:
            continue

        score = float(score) * 100 if field != 'speed' else float(score)
        rows.append({'model': model_name, 'score': score})

    if not rows:
        print(f"  ❌ No models with valid '{field}' scores")
        return None

    df = pd.DataFrame(rows).sort_values('score', ascending=False).reset_index(drop=True)
    df['rank'] = range(1, len(df) + 1)

    print(f"  ✅ Parsed {len(df)} models for '{field}'")
    print(f"  📊 Score range: {df['score'].min():.2f} – {df['score'].max():.2f}")
    return df


def parse_artificial_analysis_factory(field):
    """Returns a single-argument parser bound to the given evaluation field."""
    def parser(response=None):
        return _parse_artificial_analysis_impl(field, response)
    parser.__name__ = f'parse_aa_{field}'
    return parser

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
    {
        "name": "gpqa_diamond",
        "url": "https://artificialanalysis.ai/api/v2/data/llms/models",
        "description": "GPQA Diamond (Reasoning/Knowledge) via Artificial Analysis",
        "category": "reasoning_knowledge",
        "parser_name": "parse_aa_gpqa",
        "field": "gpqa",
        "self_fetch": True,
    },
    {
        "name": "humanity_last_exam",
        "url": "https://artificialanalysis.ai/api/v2/data/llms/models",
        "description": "Humanity Last Exam (Reasoning/Knowledge) via Artificial Analysis",
        "category": "reasoning_knowledge",
        "parser_name": "parse_aa_hle",
        "field": "hle",
        "self_fetch": True,
    },
    {
        "name": "aime_2025",
        "url": "https://artificialanalysis.ai/api/v2/data/llms/models",
        "description": "AIME 2025 (Reasoning/Knowledge) via Artificial Analysis",
        "category": "reasoning_knowledge",
        "parser_name": "parse_aa_aime",
        "field": "aime",
        "self_fetch": True,
    },
    {
        "name": "livecodebench",
        "url": "https://artificialanalysis.ai/api/v2/data/llms/models",
        "description": "LiveCodeBench (Coding) via Artificial Analysis",
        "category": "coding",
        "parser_name": "parse_aa_livecodebench",
        "field": "livecodebench",
        "self_fetch": True,
    },
    {
        "name": "artificial_analysis_speed",
        "url": "https://artificialanalysis.ai/api/v2/data/llms/models",
        "description": "Speed and Cost (Cost/Speed) via Artificial Analysis",
        "category": "cost_speed",
        "parser_name": "parse_aa_speed",
        "field": "speed",
        "self_fetch": True,
    },
    {
        "name": "lmaena_code",
        "url": "https://api.wulong.dev/arena-ai-leaderboards/v1/leaderboard?name=code",
        "description": "LMArena Coding Leaderboard",
        "category": "coding",
        "parser_name": "parse_lmaena_format",
    },
    {
        "name": "aider_polyglot",
        "url": "https://aider.chat/docs/leaderboards/",
        "description": "Aider Polyglot Leaderboard (Coding)",
        "category": "coding",
        "parser_name": "parse_aider_polyglot_format",
    },
    {
        "name": "terminal_bench",
        "url": "https://artificialanalysis.ai/api/v2/data/llms/models",
        "description": "Terminal-Bench Hard (Agentic) via Artificial Analysis",
        "category": "agentic",
        "parser_name": "parse_aa_terminal_bench",
        "self_fetch": True,
        "weight": 0.5,
    },
    {
        "name": "scicode",
        "url": "https://artificialanalysis.ai/api/v2/data/llms/models",
        "description": "SciCode (Coding) via Artificial Analysis",
        "category": "coding",
        "parser_name": "parse_aa_scicode",
        "self_fetch": True,
        "weight": 1.0,
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
    # Artificial Analysis factory-bound parsers
    'parse_aa_gpqa': parse_artificial_analysis_factory('gpqa'),
    'parse_aa_hle': parse_artificial_analysis_factory('hle'),
    'parse_aa_aime': parse_artificial_analysis_factory('aime'),
    'parse_aa_livecodebench': parse_artificial_analysis_factory('livecodebench'),
    'parse_aa_speed': parse_artificial_analysis_factory('speed'),
    'parse_aa_terminal_bench': parse_artificial_analysis_factory('terminalbench_hard'),
    'parse_aa_scicode': parse_artificial_analysis_factory('scicode'),
}

# ============================================
# COMPOSITE SCORE WEIGHTS
# ============================================

# Category-equal weighting: 25% each across Human Preference, Reasoning,
# Coding, and Agentic. Cost/Speed is excluded from the base composite
# (weight 0.0) and only added when the toggle is on.
DEFAULT_WEIGHTS = {
    # Human Preference — 25% total
    'lmaena_text':             0.125,
    'lmaena_code':             0.125,
    # Reasoning & Knowledge — 25% total
    'mmlu_pro':                0.0625,
    'gpqa_diamond':            0.0625,
    'humanity_last_exam':      0.0625,
    'aime_2025':               0.0625,
    # Coding — 25% total
    'swe_bench':               0.0625,
    'livecodebench':           0.0625,
    'aider_polyglot':          0.0625,
    'scicode':                 0.0625,
    # Agentic — 25% total (down-weighted: documented reward-hacking exploit)
    'terminal_bench':          0.25,
    # Cost/Speed — excluded from base composite; only included via toggle
    'artificial_analysis_speed': 0.0,
}

# When cost/speed is toggled on: scale all base weights to 80% and give
# speed a 20% share (treating it as a fifth 25%-equivalent category).
SPEED_WEIGHTS = {src: round(w * 0.8, 6) for src, w in DEFAULT_WEIGHTS.items()
                 if src != 'artificial_analysis_speed'}
SPEED_WEIGHTS['artificial_analysis_speed'] = 0.2

# ============================================
# MODEL NAME NORMALIZATION
# ============================================

def preclean_model_name(name):
    """Stage 1: Light string-only pre-cleaning. No AI, no database."""
    if not name or not isinstance(name, str):
        return name

    name = name.strip()

    # Remove HuggingFace org prefix if the part after the slash is >= 3 chars
    if '/' in name:
        after_slash = name.split('/', 1)[1]
        if len(after_slash) >= 3:
            name = after_slash

    # Remove date suffixes at end of string only
    name = re.sub(r'-\d{4}-\d{2}-\d{2}$', '', name)  # -YYYY-MM-DD
    name = re.sub(r'-\d{8}$', '', name)                # -YYYYMMDD
    name = re.sub(r'-\d{6}$', '', name)                # -YYYYMM

    # Normalize runs of spaces or underscores to a single space
    name = re.sub(r'[ _]+', ' ', name)

    return name.strip()


_OLLAMA_NORMALIZE_PROMPT = (
    "Given this AI model name from a benchmark leaderboard, return the canonical short name "
    "that would match the same model across different leaderboard sources. Return ONLY the "
    "canonical name, nothing else, no punctuation, no explanation.\n\n"
    "Examples:\n"
    "gpt-4o-2024-11-20 → GPT-4o\n"
    "claude-3-5-sonnet-20241022 → Claude 3.5 Sonnet\n"
    "meta-llama/Llama-3.1-70B-Instruct → Llama 3.1 70B\n"
    "gemini-2.5-pro-exp-03-25 → Gemini 2.5 Pro\n"
    "deepseek-v3-0324 → DeepSeek-V3\n"
    "Qwen/Qwen2.5-72B-Instruct → Qwen2.5 72B\n\n"
    "Model name: {precleaned_name}\n"
    "Canonical name:"
)


def _ollama_normalize(precleaned_name):
    """Call Ollama to get a canonical name for one precleaned model name."""
    prompt = _OLLAMA_NORMALIZE_PROMPT.format(precleaned_name=precleaned_name)
    try:
        resp = requests.post(
            'http://localhost:11434/api/generate',
            json={
                'model': 'qwen3:8b',
                'prompt': prompt,
                'think': False,
                'num_predict': 20,
                'temperature': 0.1,
                'stream': False,
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json().get('response', '').strip()
        first_line = text.splitlines()[0].strip().rstrip('.,;:!?')
        return first_line if first_line else None
    except Exception as e:
        print(f"  ⚠️ Ollama normalization failed for '{precleaned_name}': {e}")
        return None


def find_canonical_match(name):
    """
    Check whether `name` is close enough to an already-cached canonical name
    to be considered the same model.  Uses an 80% word-overlap threshold
    (case-insensitive) so word-order variants like 'Claude 4.5 Opus' and
    'Claude Opus 4.5' collapse to whichever was cached first.
    Returns the matching canonical name if found, otherwise returns name unchanged.
    """
    words_new = set(name.lower().split())
    if not words_new:
        return name

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT canonical_name FROM name_normalizations')
        existing = [row[0] for row in cursor.fetchall() if row[0]]
        conn.close()
    except Exception:
        return name

    for candidate in existing:
        words_candidate = set(candidate.lower().split())
        if not words_candidate:
            continue
        overlap = len(words_new & words_candidate)
        ratio = overlap / max(len(words_new), len(words_candidate))
        if ratio >= 0.8:
            return candidate

    return name


def normalize_model_name(name):
    """
    Cache-only lookup — safe to call from anywhere, including web requests.
    Precleans the name, checks the name_normalizations table, and returns
    the cached canonical name if found, otherwise the precleaned name.
    Never calls Ollama. For Ollama-backed normalization use
    bulk_normalize_model_names(), which is called only inside save_snapshot().
    """
    if not name or not isinstance(name, str):
        return name

    precleaned = preclean_model_name(name)

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT canonical_name FROM name_normalizations WHERE raw_name = ?',
            (precleaned,),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception:
        pass

    return precleaned


def bulk_normalize_model_names(names_list):
    """
    Normalize a list of raw model names.
    Checks the DB cache for all names in a single query, then calls Ollama only
    for those not already cached. Use this instead of calling normalize_model_name
    in a loop when processing a full leaderboard snapshot.
    Returns a dict mapping each original name to its canonical name.
    """
    if not names_list:
        return {}

    precleaned = {name: preclean_model_name(name) for name in names_list}
    unique_precleaned = list(set(precleaned.values()))

    # Batch cache lookup
    conn = get_connection()
    placeholders = ','.join('?' * len(unique_precleaned))
    cursor = conn.cursor()
    cursor.execute(
        f'SELECT raw_name, canonical_name FROM name_normalizations WHERE raw_name IN ({placeholders})',
        unique_precleaned,
    )
    cached = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()

    # Ollama + fuzzy dedup for uncached names.
    # Write each result to DB immediately so that later names in the same batch
    # can match against canonicals resolved earlier in this loop.
    newly_cached = {}
    for p in unique_precleaned:
        if p in cached:
            continue
        raw_canonical = _ollama_normalize(p) or p
        canonical = find_canonical_match(raw_canonical)
        newly_cached[p] = canonical
        conn = get_connection()
        try:
            conn.execute(
                'INSERT OR REPLACE INTO name_normalizations (raw_name, canonical_name, created_at) '
                'VALUES (?, ?, ?)',
                (p, canonical, datetime.now().isoformat()),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    canonical_map = {**cached, **newly_cached}
    return {name: canonical_map.get(precleaned[name], precleaned[name]) for name in names_list}

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
    Save a snapshot with score normalizations and normalized model names.
    This is the only place in the codebase that calls Ollama (via
    bulk_normalize_model_names). Web requests never touch Ollama.
    """
    conn = get_connection()
    df_copy = df.copy()

    # Apply score normalizations
    df_copy = apply_all_normalizations(df_copy, 'score')

    # Normalize model names via Ollama (cached; only uncached names hit Ollama)
    name_map = bulk_normalize_model_names(df_copy['model'].tolist())
    df_copy['normalized_model'] = df_copy['model'].map(name_map)

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

def get_composite_scores(weights=None, excluded_sources=None):
    """
    Calculate composite scores across all sources.
    Reads pre-normalized model names directly from the normalized_model column
    populated by save_snapshot(). Zero Ollama calls — instant for web requests.

    excluded_sources: optional list of source names to omit from the calculation.
    """
    excluded = set(excluded_sources or [])
    if weights is None:
        # Use category-equal DEFAULT_WEIGHTS; drop zero-weight and excluded sources
        effective = {src: w for src, w in DEFAULT_WEIGHTS.items()
                     if w > 0 and src not in excluded}
        total = sum(effective.values())
        weights = {src: w / total for src, w in effective.items()} if total else {}
    elif excluded:
        for src in excluded:
            weights.pop(src, None)
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

    conn = get_connection()

    # Read pre-normalized names + scores from each source's latest snapshot
    all_scores = {}
    for source in weights.keys():
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT MAX(snapshot_timestamp) FROM {SNAPSHOTS_TABLE} WHERE source = ?",
            (source,),
        )
        result = cursor.fetchone()
        if result is None or result[0] is None:
            continue
        latest_ts = result[0]
        df = pd.read_sql_query(
            f"SELECT model, normalized_model, norm_combined as score "
            f"FROM {SNAPSHOTS_TABLE} WHERE source = ? AND snapshot_timestamp = ?",
            conn,
            params=(source, latest_ts),
        )
        if df.empty:
            continue
        # Use normalized_model when populated; fall back to raw model name
        df['normalized_model'] = df['normalized_model'].where(
            df['normalized_model'].notna() & (df['normalized_model'].str.strip() != ''),
            df['model'],
        )
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
            normalized_model TEXT,
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

    # Migration: add normalized_model to existing snapshots tables
    try:
        cursor.execute(f'ALTER TABLE {SNAPSHOTS_TABLE} ADD COLUMN normalized_model TEXT')
    except Exception:
        pass  # column already exists
    
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
            approved_at TEXT,
            run_id TEXT
        )
    ''')

    # Add run_id column to existing feed_entries table if it doesn't have it
    try:
        cursor.execute(f"PRAGMA table_info({FEED_TABLE})")
        columns = [col[1] for col in cursor.fetchall()]
        if 'run_id' not in columns:
            cursor.execute(f"ALTER TABLE {FEED_TABLE} ADD COLUMN run_id TEXT")
    except:
        pass

    # Migration: add ai_summary column to feed_entries
    try:
        cursor.execute(f'ALTER TABLE {FEED_TABLE} ADD COLUMN ai_summary TEXT')
    except:
        pass  # column already exists

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

    # Item likes (articles and models)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS item_likes (
            item_type TEXT NOT NULL,
            item_id   TEXT NOT NULL,
            session_id TEXT NOT NULL,
            created_at TEXT,
            PRIMARY KEY (item_type, item_id, session_id)
        )
    ''')

    # Model name normalization cache
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS name_normalizations (
            raw_name TEXT PRIMARY KEY,
            canonical_name TEXT,
            created_at TEXT
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


def like_item(item_type, item_id, session_id):
    """Like an article or model once per session."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO item_likes (item_type, item_id, session_id, created_at) VALUES (?, ?, ?, ?)',
            (item_type, str(item_id), session_id, datetime.now().isoformat())
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    count = cursor.execute(
        'SELECT COUNT(*) FROM item_likes WHERE item_type=? AND item_id=?',
        (item_type, str(item_id))
    ).fetchone()[0]
    conn.close()
    return {'likes': count, 'liked': True}


def unlike_item(item_type, item_id, session_id):
    """Remove a like from an article or model."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'DELETE FROM item_likes WHERE item_type=? AND item_id=? AND session_id=?',
        (item_type, str(item_id), session_id)
    )
    conn.commit()
    count = cursor.execute(
        'SELECT COUNT(*) FROM item_likes WHERE item_type=? AND item_id=?',
        (item_type, str(item_id))
    ).fetchone()[0]
    conn.close()
    return {'likes': count, 'liked': False}


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
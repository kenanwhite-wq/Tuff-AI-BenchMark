import sqlite3
import pandas as pd

conn = sqlite3.connect('benchmark.db')

# Check latest snapshot with normalized values
df = pd.read_sql_query("""
    SELECT source, model, score, 
           norm_minmax, norm_percentile, norm_zscore, norm_combined,
           snapshot_timestamp
    FROM snapshots 
    ORDER BY snapshot_timestamp DESC 
    LIMIT 10
""", conn)

print("📊 Latest snapshots with normalized scores:")
print(df.round(2))

# Also check feed entries
df_feed = pd.read_sql_query("""
    SELECT source, model, tier, headline, status, created_at
    FROM feed_entries 
    ORDER BY created_at DESC 
    LIMIT 10
""", conn)

print("\n📰 Latest feed entries:")
print(df_feed.to_string())

conn.close()
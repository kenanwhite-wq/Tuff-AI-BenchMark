import sqlite3

DB_NAME = "benchmark.db"

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# Check if columns exist, add them if they don't
try:
    cursor.execute("ALTER TABLE snapshots ADD COLUMN norm_minmax REAL")
    print("✅ Added norm_minmax column")
except sqlite3.OperationalError:
    print("ℹ️ norm_minmax already exists")

try:
    cursor.execute("ALTER TABLE snapshots ADD COLUMN norm_percentile REAL")
    print("✅ Added norm_percentile column")
except sqlite3.OperationalError:
    print("ℹ️ norm_percentile already exists")

try:
    cursor.execute("ALTER TABLE snapshots ADD COLUMN norm_zscore REAL")
    print("✅ Added norm_zscore column")
except sqlite3.OperationalError:
    print("ℹ️ norm_zscore already exists")

try:
    cursor.execute("ALTER TABLE snapshots ADD COLUMN norm_combined REAL")
    print("✅ Added norm_combined column")
except sqlite3.OperationalError:
    print("ℹ️ norm_combined already exists")

conn.commit()
conn.close()

print("\n✅ Database updated! You can now run the hourly fetcher again.")
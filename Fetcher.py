import pandas as pd
import sqlite3
import requests
import os

print("=" * 50)
print("FETCHING LMArena (LMSYS Chatbot Arena) DATA")
print("=" * 50)

# Replace the `name=text` line with this:
url = "https://api.wulong.dev/arena-ai-leaderboards/v1/leaderboard?name=code"

print("📥 Downloading from Arena AI leaderboards API...")
response = requests.get(url)

if response.status_code != 200:
    print(f"❌ Error {response.status_code}: {response.text}")
    print("\nTrying fallback: raw GitHub JSON...")
    fallback_url = "https://raw.githubusercontent.com/oolong-tea-2026/arena-ai-leaderboards/main/data/latest.json"
    response = requests.get(fallback_url)

if response.status_code != 200:
    print(f"❌ Still failing: {response.status_code}")
    exit()

data = response.json()

# The API returns models in a 'models' array
models = data.get("models", [])

if not models:
    print("❌ No models found in the response")
    exit()

df = pd.DataFrame(models)

print(f"✅ Downloaded data for {len(df)} models!")
print()
print("Top 5 models on LMArena (Text leaderboard):")
print(df[["rank", "model", "vendor", "score"]].head(5))
print()

print("=" * 50)
print("SAVING TO DATABASE")
print("=" * 50)

if os.path.exists('benchmark.db'):
    print("🗑️  Removing old benchmark.db...")
    os.remove('benchmark.db')

conn = sqlite3.connect('benchmark.db')
df.to_sql('models', conn, if_exists='replace', index=False)
conn.close()

print("✅ Data saved to 'benchmark.db'!")

conn = sqlite3.connect('benchmark.db')
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM models")
count = cursor.fetchone()[0]
print(f"✅ Verified: 'models' table has {count} rows.")
conn.close()

print()
print("=" * 50)
print("🎉 ALL DONE!")
print("=" * 50)
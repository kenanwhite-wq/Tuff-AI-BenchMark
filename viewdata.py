import sqlite3
import pandas as pd

conn = sqlite3.connect('benchmark.db')

# Show all columns
df = pd.read_sql_query("SELECT * FROM models", conn)
print("All columns:", df.columns.tolist())
print()
print("Top 10 models:")
print(df[["rank", "model", "vendor", "score"]].head(10))

conn.close()

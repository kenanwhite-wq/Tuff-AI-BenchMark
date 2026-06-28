# Tuff AI Benchmark
The open-source AI benchmark aggregator. Tracks model performance across 12 benchmark sources, updated hourly, with a live news feed covering everything happening in AI.

🌐 aibenchmark.com — live site (coming soon)


What it does
Most AI benchmark sites either run their own evaluations (expensive, slow) or show you one leaderboard at a time. Tuff AI aggregates across 12 independent sources into a single weighted composite score — so instead of checking LMArena, then SWE-bench, then GPQA separately, you see one honest number that reflects a model's performance across reasoning, coding, human preference, and agentic benchmarks.

Alongside the composite score, an automated news scanner watches 13 AI news sources hourly, classifies each item using a locally-running AI model (no data leaves your server), and surfaces what's actually worth knowing — model releases, benchmark alerts, research papers, and industry news — in a tiered feed.

Everything is open source, the methodology is public, and the weights are visible. No black-box scoring.


Features
Composite score across 12 sources, equally weighted by category (reasoning 25%, coding 25%, human preference 25%, agentic 25%)
Cost/speed toggle — include or exclude speed and pricing from the composite score
Live feed of leaderboard changes, model releases, benchmark alerts, and AI news — updated hourly
Feed filters — filter by category (leaderboard changes, model releases, research papers, general news, benchmark alerts)
Model detail pages — full source breakdown, score history chart, and recent activity per model
Article pages with threaded comments on every news item
Community voting — pairwise model preference voting with Elo ratings, separate from the composite score
News scanner — watches 13 sources hourly, classifies items with local Ollama AI
Incomplete data badges — models missing coverage on some sources are flagged rather than hidden
Methodology page — full source list, weights, and integrity concerns publicly documented
Mobile responsive — works on iPhone and Android


Benchmark sources
Human Preference (25%)
Source
Weight
LMArena Overall Elo
12.5%
LMArena Coding Elo
12.5%

Reasoning & Knowledge (25%)
Source
Weight
MMLU-Pro
6.25%
GPQA Diamond
6.25%
Humanity's Last Exam
6.25%
AIME 2025
6.25%

Coding (25%)
Source
Weight
SWE-bench Verified
6.25%
LiveCodeBench
6.25%
Aider Polyglot
6.25%
SciCode
6.25%

Agentic (25%)
Source
Weight
Notes
Terminal-Bench
25%
Down-weighted — documented reward-hacking exploit

Cost & Speed (toggle-only)
Source
Notes
Artificial Analysis
Excluded from base composite, opt-in via toggle



News sources
RSS feeds and scraped sources watched hourly:

Lab blogs: OpenAI, Anthropic, Google DeepMind, Meta AI, Mistral, HuggingFace

Research: arXiv cs.AI, arXiv cs.CL, Papers With Code

News: MarkTechPost, The Gradient, Hacker News

Community: Reddit r/LocalLLaMA, Reddit r/MachineLearning


Tech stack
Layer
Technology
Frontend
React
Backend
Flask + Gunicorn
Database
SQLite
AI normalization
Ollama (Qwen3 8B, local)
News classification
Ollama (Qwen3 8B, local)
Scheduler
Python (Timer.py)
Deployment
DigitalOcean + Nginx



Running locally
Prerequisites: Python 3.9+, Node.js 18+, Ollama

1. Clone the repo

git clone https://github.com/kenanwhite-wq/Tuff-AI-BenchMark.git

cd Tuff-AI-BenchMark

2. Set up Python environment

python3 -m venv .venv-1

source .venv-1/bin/activate

pip install -r requirements.txt

3. Set up environment variables

Copy .env.example to .env and fill in your values:

cp .env.example .env

Required:

ARTIFICIAL_ANALYSIS_API_KEY=your_key_here   # free at artificialanalysis.ai

ADMIN_TOKEN=your_random_secret              # generate with: python3 -c 'import secrets; print(secrets.token_hex(32))'

4. Install Ollama and pull the model

# Install from ollama.com, then:

ollama pull qwen3:8b

5. Install frontend dependencies

cd frontend

npm install

cd ..

6. Initialize the database and run the first fetch

python3 hourlyfetcher.py

7. Start all services

chmod +x start.sh stop.sh

./start.sh

Visit http://localhost:3000


Project structure
Tuff-AI-BenchMark/

├── config.py              # Database, parsers, normalization, composite scoring

├── hourlyfetcher.py       # Fetches all benchmark sources, detects changes

├── news_scanner.py        # Fetches and classifies AI news from 13 sources

├── Timer.py               # Scheduler — runs fetcher + scanner hourly

├── SimpleWeb              # Flask API (all /api/* routes)

├── frontend/              # React app

│   ├── src/

│   │   ├── App.js         # Home page, methodology, privacy

│   │   ├── ModelPage.js   # Model detail pages

│   │   └── ArticlePage.js # Article pages with comments

│   └── public/

│       └── robots.txt

├── start.sh               # Start all services

├── stop.sh                # Stop all services

├── .env.example           # Environment variable template

└── benchmark.db           # SQLite database (gitignored)


Contributing
Pull requests welcome. The most valuable contributions right now:

New benchmark parsers — add a parser in config.py for any benchmark source not currently tracked. GAIA, OSWorld, WebArena, and Tau2-bench are high priority. See existing parsers for the pattern.
Bug fixes — model name normalization still has edge cases, especially for lesser-known models
Frontend improvements — the mobile layout and model detail page chart could both use polish

To add a new benchmark source:

Add a parser function in config.py following the existing pattern — return a DataFrame with model and score columns
Add the source to the SOURCES list with name, url, description, category, and parser_name
Add the parser to PARSER_MAP
Update DEFAULT_WEIGHTS with the new source's weight
Update the methodology table in App.js


Methodology
The composite score is a weighted average across four equal categories. Within each category, sources are equally weighted. Weights are fixed and publicly documented — there is no secret formula.

Sources with documented integrity issues (reward-hacking exploits, gold-answer leaks) are retained but down-weighted, with the concern disclosed publicly on the methodology page.

Model name normalization across sources uses a locally-running Qwen3 8B model with database caching — the same raw name is only normalized once, then reused from cache. This ensures the same model is matched correctly across sources even when named differently (e.g. "gpt-4o-2024-11-20" and "GPT-4o" resolve to the same entry).

Full methodology: aibenchmark.com/methodology


Data attribution
Benchmark scores sourced from:

LMArena / LMSYS Chatbot Arena
TIGER-Lab — MMLU-Pro
Princeton NLP — SWE-bench Verified
Artificial Analysis — GPQA Diamond, HLE, AIME 2025, LiveCodeBench, Terminal-Bench, SciCode
aider.chat — Aider Polyglot
Hugging Face — MMLU-Pro dataset hosting


License
MIT — see LICENSE



Built by @kenanwhite-wq. Not affiliated with any AI lab.


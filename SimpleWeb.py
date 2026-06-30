"""
WEB INTERFACE - MERGED VERSION
Reliable data display + feed approval
"""

from flask import Flask, render_template_string, jsonify, request
from urllib.parse import unquote
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import os
import re
from functools import wraps
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import (
    DB_NAME,
    SOURCES,
    get_composite_scores,
    approve_feed_entry,
    normalize_model_name,
    COMPOSITE_TABLE,
    get_vote_pair,
    record_vote,
    get_community_rankings,
    get_vote_stats,
    add_comment,
    get_comments,
    build_comment_tree,
    like_comment,
    unlike_comment,
    delete_comment,
    init_database,
    SPEED_WEIGHTS,
    like_item,
    unlike_item,
    get_model_prices,
    fetch_and_store_prices,
)
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
init_database()

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[],
    storage_uri='memory://'
)

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        admin_token = os.environ.get('ADMIN_TOKEN')
        if not admin_token:
            return jsonify({'error': 'Admin token not configured'}), 500
        provided = request.headers.get('X-Admin-Token') or request.args.get('admin_token')
        if provided != admin_token:
            return jsonify({'error': 'Unauthorized'}), 403
        return f(*args, **kwargs)
    return decorated

@app.errorhandler(429)
def rate_limit_handler(e):
    return jsonify({'error': 'Too many requests. Please slow down.'}), 429

def convert_pandas_types(obj):
    if isinstance(obj, dict):
        return {k: convert_pandas_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_pandas_types(v) for v in obj]
    elif hasattr(obj, 'item'):
        return obj.item()
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    elif isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    else:
        return obj

def get_latest_snapshot_for_source(source_name, conn, limit=50):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(snapshot_timestamp) FROM snapshots WHERE source = ?", (source_name,))
        result = cursor.fetchone()
        if result is None or result[0] is None:
            return None
        latest_ts = result[0]
        df = pd.read_sql_query("""
            SELECT * FROM snapshots
            WHERE source = ? AND snapshot_timestamp = ?
            ORDER BY rank ASC
            LIMIT ?
        """, conn, params=(source_name, latest_ts, limit))
        return df if not df.empty else None
    except Exception as e:
        print(f"⚠️ Error: {e}")
        return None

# ============================================
# HTML TEMPLATE (with feed approval)
# ============================================

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>AI Benchmark Aggregator</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 20px auto;
            padding: 0 20px;
            background: #f5f5f5;
            color: #1a1a1a;
        }
        .header {
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .header h1 { font-size: 28px; margin-bottom: 5px; }
        .header .subtitle { color: #666; font-size: 14px; }
        .header .stats { display: flex; gap: 20px; margin-top: 10px; font-size: 13px; color: #666; flex-wrap: wrap; }
        .header .stats span { background: #f0f0f0; padding: 4px 12px; border-radius: 12px; }
        .composite-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px;
            margin-top: 20px;
        }
        .composite-card {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            border: 1px solid #e5e7eb;
            transition: transform 0.2s;
        }
        .composite-card:hover { transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.05); }
        .composite-card .rank { font-size: 11px; color: #888; font-weight: 600; }
        .composite-card .model { font-weight: 600; font-size: 14px; margin: 5px 0 2px; word-break: break-word; }
        .composite-card .score { font-size: 24px; font-weight: 700; color: #2563eb; }
        .composite-card .sources { font-size: 11px; color: #888; }
        .section {
            background: white;
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .section h2 { font-size: 20px; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; margin-bottom: 15px; }
        .tabs { display: flex; gap: 5px; margin-bottom: 15px; flex-wrap: wrap; }
        .tab { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; background: #e5e7eb; font-weight: 500; font-size: 14px; }
        .tab.active { background: #2563eb; color: white; }
        .tab:hover { opacity: 0.8; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }
        th { background: #f8f9fa; font-weight: 600; position: sticky; top: 0; }
        tr:hover { background: #fafafa; }
        .table-wrap { max-height: 400px; overflow-y: auto; }
        .feed-item {
            padding: 12px 15px;
            border-left: 4px solid #2563eb;
            margin-bottom: 10px;
            background: #fafafa;
            border-radius: 4px;
        }
        .feed-item.tier-big { border-left-color: #dc2626; }
        .feed-item.tier-moderate { border-left-color: #f59e0b; }
        .feed-item.tier-small { border-left-color: #22c55e; }
        .feed-item .headline { font-weight: 500; font-size: 15px; }
        .feed-item .body { font-size: 14px; color: #555; margin-top: 4px; }
        .feed-item .meta { font-size: 12px; color: #888; margin-top: 4px; }
        .feed-item .actions { margin-top: 8px; display: flex; gap: 8px; }
        .btn { padding: 4px 14px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .btn-approve { background: #22c55e; color: white; }
        .btn-approve:hover { background: #16a34a; }
        .btn-reject { background: #ef4444; color: white; }
        .btn-reject:hover { background: #dc2626; }
        .badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; margin-right: 6px; }
        .badge-big { background: #fecaca; color: #991b1b; }
        .badge-moderate { background: #fde68a; color: #92400e; }
        .badge-small { background: #bbf7d0; color: #166534; }
        .badge-source { background: #e5e7eb; color: #374151; font-weight: 400; }
        .empty-state { color: #888; text-align: center; padding: 30px; }
        .empty-state .icon { font-size: 40px; margin-bottom: 10px; }
        .refresh-btn { background: #2563eb; color: white; border: none; padding: 8px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; }
        .refresh-btn:hover { background: #1d4ed8; }
        .footer { text-align: center; color: #888; font-size: 12px; padding: 20px; }
        @media (max-width: 700px) {
            .composite-grid { grid-template-columns: 1fr 1fr; }
            .header { padding: 20px; }
            .section { padding: 15px; }
            table { font-size: 12px; }
            th, td { padding: 6px 8px; }
        }
    </style>
</head>
<body>

<div class="header">
    <h1>🤖 AI Benchmark Aggregator</h1>
    <div class="subtitle">Real-time leaderboard aggregation</div>
    <div class="stats">
        <span>🕐 Updated: {{ now }}</span>
        <span>📊 {{ composites|length }} models</span>
        <span>📁 {{ sources|length }} sources</span>
        <span>📰 {{ feed_total }} entries</span>
        <button class="refresh-btn" onclick="location.reload()">↻ Refresh</button>
    </div>

    <div class="composite-grid">
        {% for item in composites[:12] %}
        <div class="composite-card">
            <div class="rank">#{{ loop.index }}</div>
            <div class="model">{{ item.model[:25] }}</div>
            <div class="score">{{ item.composite_score|round(1) }}</div>
            <div class="sources">{{ item.sources_available }}/{{ sources|length }} sources</div>
        </div>
        {% else %}
        <div class="composite-card"><div class="model">No data yet</div><div class="score">-</div></div>
        {% endfor %}
    </div>
</div>

<div class="section">
    <h2>📊 Source Breakdown</h2>
    <div class="tabs">
        {% for source in sources %}
        <button class="tab {% if loop.first %}active{% endif %}" onclick="showTab('{{ source.name }}')">{{ source.name }}</button>
        {% endfor %}
    </div>
    {% for source in sources %}
    <div id="tab-{{ source.name }}" class="tab-content {% if loop.first %}active{% endif %}">
        {% set df = source_data[source.name] %}
        {% if df is not none and not df.empty %}
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Model</th>
                        <th>Score</th>
                        <th>Min-Max</th>
                        <th>Percentile</th>
                        <th>Z-Score</th>
                        <th>Combined</th>
                    </tr>
                </thead>
                <tbody>
                    {% for _, row in df.iterrows() %}
                    <tr>
                        <td>{{ row.rank|int if row.rank else '-' }}</td>
                        <td>{{ row.model[:40] }}</td>
                        <td>{{ row.score|round(1) }}</td>
                        <td>{{ row.norm_minmax|round(1) if row.norm_minmax else '-' }}</td>
                        <td>{{ row.norm_percentile|round(1) if row.norm_percentile else '-' }}</td>
                        <td>{{ row.norm_zscore|round(1) if row.norm_zscore else '-' }}</td>
                        <td><strong>{{ row.norm_combined|round(1) if row.norm_combined else '-' }}</strong></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <div class="empty-state"><div class="icon">📭</div><p>No data for {{ source.name }}</p></div>
        {% endif %}
    </div>
    {% endfor %}
</div>

<div class="section">
    <h2>📰 Feed <span style="font-size:14px;color:#888;font-weight:400;">({{ feed_drafts|length }} drafts waiting)</span></h2>
    <div class="tabs">
        <button class="tab active" onclick="showFeed('approved')">✅ Approved</button>
        <button class="tab" onclick="showFeed('draft')">📝 Drafts ({{ feed_drafts|length }})</button>
    </div>
    <div id="feed-approved">
        {% if feed_approved %}
            {% for item in feed_approved[:20] %}
            <div class="feed-item tier-{{ item.tier }}">
                <div class="headline">
                    <span class="badge badge-{{ item.tier }}">{{ item.tier }}</span>
                    <span class="badge badge-source">{{ item.source }}</span>
                    {{ item.headline }}
                </div>
                {% if item.body %}<div class="body">{{ item.body }}</div>{% endif %}
                <div class="meta">{{ item.created_at[:16] }}</div>
            </div>
            {% endfor %}
        {% else %}
        <div class="empty-state"><div class="icon">✅</div><p>No approved entries yet.</p></div>
        {% endif %}
    </div>
    <div id="feed-draft" style="display:none;">
        {% if feed_drafts %}
            {% for item in feed_drafts[:30] %}
            <div class="feed-item tier-{{ item.tier }}">
                <div class="headline">
                    <span class="badge badge-{{ item.tier }}">{{ item.tier }}</span>
                    <span class="badge badge-source">{{ item.source }}</span>
                    {{ item.headline }}
                </div>
                {% if item.body %}<div class="body">{{ item.body }}</div>{% endif %}
                <div class="meta">
                    {{ item.created_at[:16] }}
                    <div class="actions">
                        <button class="btn btn-approve" onclick="approveEntry({{ item.id }})">✅ Approve</button>
                        <button class="btn btn-reject" onclick="rejectEntry({{ item.id }})">❌ Reject</button>
                    </div>
                </div>
            </div>
            {% endfor %}
        {% else %}
        <div class="empty-state"><div class="icon">📝</div><p>No draft entries.</p></div>
        {% endif %}
    </div>
</div>

<div class="footer">Data updates hourly • Built with ❤️</div>

<script>
function showTab(name) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tabs .tab').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    document.querySelectorAll('.tabs .tab').forEach(el => {
        if (el.textContent.trim() === name) el.classList.add('active');
    });
}
function showFeed(type) {
    document.getElementById('feed-approved').style.display = type === 'approved' ? 'block' : 'none';
    document.getElementById('feed-draft').style.display = type === 'draft' ? 'block' : 'none';
    document.querySelectorAll('.tabs .tab').forEach(el => el.classList.remove('active'));
    event.target.classList.add('active');
}
function approveEntry(id) {
    if (confirm('Approve this entry?')) {
        fetch('/api/approve/' + id, {method: 'POST'})
            .then(r => r.json())
            .then(data => { if (data.status === 'approved') location.reload(); });
    }
}
function rejectEntry(id) {
    if (confirm('Reject this entry?')) {
        fetch('/api/reject/' + id, {method: 'POST'})
            .then(r => r.json())
            .then(data => { if (data.status === 'rejected') location.reload(); });
    }
}
setTimeout(() => location.reload(), 60000);
</script>

</body>
</html>
"""

# ============================================
# ROUTES
# ============================================

@app.route('/')
def index():
    composites = get_composite_scores()
    if composites.empty:
        composites = pd.DataFrame({'model': ['No data'], 'composite_score': [0], 'sources_available': [0]})

    conn = sqlite3.connect(DB_NAME)

    try:
        feed_approved = pd.read_sql_query("SELECT * FROM feed_entries WHERE status = 'approved' ORDER BY created_at DESC LIMIT 20", conn)
        feed_drafts = pd.read_sql_query("SELECT * FROM feed_entries WHERE status = 'draft' ORDER BY created_at DESC LIMIT 30", conn)
        feed_total = pd.read_sql_query("SELECT COUNT(*) as count FROM feed_entries", conn).iloc[0]['count']
    except:
        feed_approved = pd.DataFrame()
        feed_drafts = pd.DataFrame()
        feed_total = 0

    source_data = {}
    for source in SOURCES:
        name = source['name']
        df = get_latest_snapshot_for_source(name, conn, limit=50)
        source_data[name] = df if df is not None else pd.DataFrame()

    conn.close()

    return render_template_string(
        HTML,
        composites=composites.head(12).to_dict('records'),
        feed_approved=feed_approved.to_dict('records'),
        feed_drafts=feed_drafts.to_dict('records'),
        feed_total=feed_total,
        sources=SOURCES,
        source_data=source_data,
        now=datetime.now().strftime('%Y-%m-%d %H:%M'),
    )


@app.route('/debug')
def debug():
    conn = sqlite3.connect(DB_NAME)
    results = {}
    for source in SOURCES:
        name = source['name']
        count = pd.read_sql_query("SELECT COUNT(*) FROM snapshots WHERE source = ?", conn, params=(name,)).iloc[0][0]
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(snapshot_timestamp) FROM snapshots WHERE source = ?", (name,))
        latest = cursor.fetchone()[0]
        df = pd.read_sql_query("SELECT * FROM snapshots WHERE source = ? LIMIT 3", conn, params=(name,))
        results[name] = {
            'count': int(count),
            'latest_timestamp': latest,
            'sample': convert_pandas_types(df.to_dict('records')) if not df.empty else []
        }
    conn.close()
    return jsonify(results)


@app.route('/api/approve/<int:entry_id>', methods=['POST'])
@require_admin
def api_approve(entry_id):
    try:
        approve_feed_entry(entry_id)
        return jsonify({'status': 'approved'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/reject/<int:entry_id>', methods=['POST'])
@require_admin
def api_reject(entry_id):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM feed_entries WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'rejected'})


@app.route('/api/comments/<path:model_name>', methods=['GET'])
def api_get_comments(model_name):
    """Get comments for a model."""
    decoded_name = unquote(model_name)
    if request.args.get('tree') == '1':
        return jsonify(convert_pandas_types(build_comment_tree(decoded_name, limit=request.args.get('limit', 100, type=int))))

    df = get_comments(decoded_name, limit=request.args.get('limit', 50, type=int))
    if df.empty:
        return jsonify([])
    return jsonify(convert_pandas_types(df.to_dict('records')))


@app.route('/api/comments', methods=['POST'])
@limiter.limit('10 per minute; 50 per hour')
def api_add_comment():
    """Create a comment for a model."""
    data = request.json or {}
    model = data.get('model')
    comment = data.get('comment')
    username = data.get('username')
    parent_id = data.get('parent_id')
    session_id = data.get('session_id')

    if not model or not comment:
        return jsonify({'error': 'Model and comment are required'}), 400

    comment = re.sub(r'<[^>]+>', '', comment).strip()
    if not comment:
        return jsonify({'error': 'Comment cannot be empty'}), 400

    if not session_id:
        session_id = request.headers.get('X-Session-ID')

    if parent_id is not None and parent_id != '':
        try:
            parent_id = int(parent_id)
        except (TypeError, ValueError):
            return jsonify({'error': 'parent_id must be an integer'}), 400

    result = add_comment(model, comment, username, session_id, parent_id)
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result), 201


@app.route('/api/items/like', methods=['POST'])
def api_like_item():
    data = request.json or {}
    item_type = data.get('item_type')
    item_id = data.get('item_id')
    session_id = data.get('session_id') or request.headers.get('X-Session-ID') or 'anonymous'
    if not item_type or item_id is None:
        return jsonify({'error': 'item_type and item_id required'}), 400
    return jsonify(like_item(item_type, item_id, session_id))


@app.route('/api/items/unlike', methods=['POST'])
def api_unlike_item():
    data = request.json or {}
    item_type = data.get('item_type')
    item_id = data.get('item_id')
    session_id = data.get('session_id') or request.headers.get('X-Session-ID') or 'anonymous'
    if not item_type or item_id is None:
        return jsonify({'error': 'item_type and item_id required'}), 400
    return jsonify(unlike_item(item_type, item_id, session_id))


@app.route('/api/comments/<int:comment_id>/like', methods=['POST'])
@limiter.limit('60 per minute')
def api_like_comment(comment_id):
    """Like a comment."""
    data = request.json or {}
    session_id = data.get('session_id') or request.headers.get('X-Session-ID') or 'anonymous'
    return jsonify(like_comment(comment_id, session_id))


@app.route('/api/comments/<int:comment_id>/unlike', methods=['POST'])
def api_unlike_comment(comment_id):
    """Unlike a comment."""
    data = request.json or {}
    session_id = data.get('session_id') or request.headers.get('X-Session-ID') or 'anonymous'
    return jsonify(unlike_comment(comment_id, session_id))


@app.route('/api/comments/<int:comment_id>', methods=['DELETE'])
def api_delete_comment(comment_id):
    """Delete a comment."""
    data = request.json or {}
    session_id = data.get('session_id') or request.headers.get('X-Session-ID')
    return jsonify(delete_comment(comment_id, session_id))


@app.route('/api/models')
def api_models():
    include_speed = request.args.get('include_speed', 'false').lower() == 'true'
    view = request.args.get('view', 'composite')

    def get_confidence(sources_available):
        if sources_available >= 5:
            return 'high'
        elif sources_available >= 3:
            return 'medium'
        else:
            return 'low'

    if view != 'composite':
        source_names = [s['name'] for s in SOURCES]
        if view in source_names:
            conn = sqlite3.connect(DB_NAME)
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT MAX(snapshot_timestamp) FROM snapshots WHERE source = ?', (view,))
                result = cursor.fetchone()
                if result and result[0]:
                    latest_ts = result[0]
                    source_df = pd.read_sql_query('''
                        SELECT model, normalized_model, score, rank, norm_combined
                        FROM snapshots
                        WHERE source = ? AND snapshot_timestamp = ?
                        ORDER BY rank ASC
                    ''', conn, params=(view, latest_ts))
                    source_data = source_df.to_dict('records')
                    for i, item in enumerate(source_data):
                        item['composite_score'] = item.get('norm_combined')
                        item['composite_score_display'] = item.get('norm_combined')
                        item['sources_available'] = 1
                        item['confidence'] = 'source'
                        item['show_composite'] = True
                        item['rank'] = i + 1
                        item['raw_score'] = item.get('score')
                    return jsonify(convert_pandas_types(source_data))
            except Exception as e:
                print(f"Error fetching source view: {e}")
            finally:
                conn.close()

    composites = get_composite_scores(weights=dict(SPEED_WEIGHTS) if include_speed else None)
    results = []
    if not composites.empty:
        df = composites.sort_values('composite_score', ascending=False).reset_index(drop=True)
        results = df[['model', 'composite_score', 'sources_available']].copy().to_dict('records')
        for i, item in enumerate(results):
            item['rank'] = i + 1
            item['confidence'] = get_confidence(item['sources_available'])
            if item['sources_available'] < 3:
                item['composite_score_display'] = None
                item['show_composite'] = False
            else:
                item['composite_score_display'] = item['composite_score']
                item['show_composite'] = True

    # Append Elo-only models not already in results.
    conn = sqlite3.connect(DB_NAME)
    try:
        elo_df = pd.read_sql_query("SELECT model, rating, votes_total FROM elo_ratings", conn)
        if not elo_df.empty:
            existing = {normalize_model_name(item['model']).lower() for item in results}
            for _, row in elo_df.iterrows():
                raw_model = row['model']
                normalized = normalize_model_name(raw_model)
                if normalized.lower() not in existing:
                    results.append({
                        'model': normalized,
                        'composite_score': None,
                        'composite_score_display': None,
                        'show_composite': False,
                        'sources_available': 0,
                        'confidence': 'low',
                        'rank': None,
                        'community_elo': float(row['rating']),
                        'votes_total': int(row['votes_total'] or 0),
                        'raw_names': raw_model,
                    })
                    existing.add(normalized.lower())
                else:
                    for item in results:
                        if normalize_model_name(item['model']).lower() == normalized.lower():
                            if item.get('raw_names') and raw_model not in item['raw_names']:
                                item['raw_names'] = f"{item['raw_names']} | {raw_model}"
                            else:
                                item['raw_names'] = raw_model
                            break
        # Attach likes counts for all models
        if results:
            model_names = [str(item['model']) for item in results]
            placeholders = ','.join(['?'] * len(model_names))
            likes_df = pd.read_sql_query(
                f"SELECT item_id, COUNT(*) as likes FROM item_likes "
                f"WHERE item_type='model' AND item_id IN ({placeholders}) GROUP BY item_id",
                conn, params=model_names
            )
            likes_map = dict(zip(likes_df['item_id'].astype(str), likes_df['likes'].astype(int)))
            for item in results:
                item['likes'] = likes_map.get(str(item['model']), 0)
    finally:
        conn.close()

    return jsonify(convert_pandas_types(results))


# ============================================
# COMMUNITY VOTING API ENDPOINTS
# ============================================

@app.route('/api/vote/pair')
def api_vote_pair():
    """Get a pair of models to vote on"""
    model_a, model_b = get_vote_pair()

    if model_a is None or model_b is None:
        return jsonify({'error': 'Not enough models'}), 404

    return jsonify({'model_a': model_a, 'model_b': model_b})


@app.route('/api/vote/submit', methods=['POST'])
@limiter.limit('30 per minute; 200 per hour')
def api_vote_submit():
    """Submit a vote"""
    data = request.json or {}
    model_a = data.get('model_a')
    model_b = data.get('model_b')
    winner = data.get('winner')
    session_id = data.get('session_id', 'anonymous')

    if not model_a or not model_b or not winner:
        return jsonify({'error': 'Missing required fields'}), 400

    if winner not in [model_a, model_b]:
        return jsonify({'error': 'Winner must be one of the models'}), 400

    result = record_vote(model_a, model_b, winner, session_id)
    return jsonify(result)


@app.route('/api/vote/rankings')
def api_vote_rankings():
    """Get community rankings"""
    limit = request.args.get('limit', 20, type=int)
    df = get_community_rankings(limit)

    if df.empty:
        return jsonify([])

    return jsonify(convert_pandas_types(df.to_dict('records')))


@app.route('/api/vote/stats')
def api_vote_stats():
    """Get voting statistics"""
    return jsonify(get_vote_stats())


@app.route('/api/model/<path:model_name>')
def api_model(model_name):
    decoded_name = unquote(model_name)
    norm_name = normalize_model_name(decoded_name)

    conn = sqlite3.connect(DB_NAME)

    # overall composite and rank
    composite_score = None
    rank = None
    sources_available = 0
    try:
        comps = get_composite_scores()
        if not comps.empty:
            comps = comps.reset_index(drop=True)
            comps['rank'] = range(1, len(comps) + 1)

            # try normalized name first, then decoded, then raw source names
            match = comps[comps['model'].str.lower() == norm_name.lower()]
            if match.empty:
                match = comps[comps['model'].str.lower() == decoded_name.lower()]

            if match.empty and 'raw_names' in comps.columns:
                search_term = decoded_name.lower()
                norm_term = norm_name.lower()
                match = comps[comps['raw_names'].str.lower().str.contains(search_term, na=False) |
                              comps['raw_names'].str.lower().str.contains(norm_term, na=False)]

            if not match.empty:
                composite_score = float(match.iloc[0]['composite_score'])
                rank = int(match.iloc[0]['rank'])
                sources_available = int(match.iloc[0].get('sources_available', 0) or 0)
    except Exception as e:
        print('Error computing composite:', e)

    # per-source scores
    source_scores = []
    for src in SOURCES:
        name = src.get('name')
        category = src.get('category')
        try:
            df = get_latest_snapshot_for_source(name, conn, limit=200)
        except Exception:
            df = None

        if df is None or df.empty:
            source_scores.append({
                'source_name': name,
                'category': category,
                'raw_score': None,
                'rank': None,
                'total_in_source': 0,
                'normalized_score': None,
                'has_data': False
            })
            continue

        try:
            df['normalized_model'] = df['model'].apply(normalize_model_name)
        except Exception:
            df['normalized_model'] = df['model']

        total = len(df)

        # try normalized name first, then decoded, then case-insensitive
        row = df[df['normalized_model'].str.lower() == norm_name.lower()]
        if row.empty:
            row = df[df['normalized_model'].str.lower() == decoded_name.lower()]
        if row.empty:
            row = df[df['model'].str.lower() == decoded_name.lower()]

        if row.empty:
            source_scores.append({
                'source_name': name,
                'category': category,
                'raw_score': None,
                'rank': None,
                'total_in_source': total,
                'normalized_score': None,
                'has_data': False
            })
        else:
            r = row.iloc[0]
            source_scores.append({
                'source_name': name,
                'category': category,
                'raw_score': r.get('score'),
                'rank': int(r.get('rank')) if r.get('rank') is not None else None,
                'total_in_source': int(total),
                'normalized_score': float(r.get('norm_combined')) if r.get('norm_combined') is not None else None,
                'has_data': True
            })

    # community Elo stats
    community_elo = None
    votes_won = 0
    votes_lost = 0
    votes_total = 0
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT model, rating, votes_won, votes_lost, votes_total FROM elo_ratings "
            "WHERE LOWER(model) = LOWER(?) OR LOWER(model) = LOWER(?)",
            (decoded_name, norm_name)
        )
        row = cur.fetchone()
        if row:
            community_elo = float(row[1])
            votes_won = int(row[2] or 0)
            votes_lost = int(row[3] or 0)
            votes_total = int(row[4] or 0)
    except Exception:
        community_elo = None

    # category composite scores
    category_scores = {}
    mapping = {
        'reasoning': ['reasoning_knowledge'],
        'coding': ['coding'],
        'human_preference': ['human_preference'],
        'agentic': ['agentic', 'tool_use', 'agentic_tool_use']
    }
    for key, cats in mapping.items():
        vals = [s['normalized_score'] for s in source_scores if s['category'] in cats and s['normalized_score'] is not None]
        category_scores[key] = sum(vals) / len(vals) if vals else None

    # history
    history = []
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT composite_score, updated_at FROM {COMPOSITE_TABLE} WHERE model = ? ORDER BY updated_at DESC LIMIT 30",
            (norm_name,)
        )
        for r in cur.fetchall():
            history.append({'timestamp': r[1], 'composite_score': r[0]})
    except Exception:
        history = []

    # feed entries
    feed_entries = []
    try:
        df_feed = pd.read_sql_query("SELECT * FROM feed_entries ORDER BY created_at DESC LIMIT 200", conn)
        if not df_feed.empty:
            df_feed['normalized_model'] = df_feed['model'].apply(normalize_model_name)
            matched = df_feed[
                (df_feed['normalized_model'].str.lower() == norm_name.lower()) |
                (df_feed['normalized_model'].str.lower() == decoded_name.lower())
            ]
            feed_entries = matched.to_dict('records')
    except Exception:
        feed_entries = []

    # model likes count
    model_likes = 0
    try:
        conn2 = sqlite3.connect(DB_NAME)
        likes_row = conn2.execute(
            "SELECT COUNT(*) FROM item_likes WHERE item_type='model' AND item_id=?",
            (decoded_name,)
        ).fetchone()
        model_likes = likes_row[0] if likes_row else 0
        conn2.close()
    except Exception:
        pass

    conn.close()

    if composite_score is None and community_elo is None and not any(s['has_data'] for s in source_scores):
        return jsonify({'error': 'Model not found'}), 404

    return jsonify(convert_pandas_types({
        'model': decoded_name,
        'composite_score': composite_score,
        'rank': rank,
        'sources_available': sources_available,
        'community_elo': community_elo,
        'votes_won': votes_won,
        'votes_lost': votes_lost,
        'votes_total': votes_total,
        'category_scores': category_scores,
        'source_scores': source_scores,
        'history': history,
        'feed_entries': feed_entries,
        'likes': model_likes,
        'last_updated': datetime.now().isoformat()
    }))


@app.route('/api/feed/entry/<int:entry_id>/summary')
def api_entry_summary(entry_id):
    conn = sqlite3.connect(DB_NAME)
    try:
        row = pd.read_sql_query(
            'SELECT headline, body, source, ai_summary FROM feed_entries WHERE id = ?',
            conn, params=(entry_id,)
        )
        if row.empty:
            conn.close()
            return jsonify({'error': 'Entry not found'}), 404

        item = row.iloc[0]

        if item['ai_summary'] and len(str(item['ai_summary'])) > 20:
            conn.close()
            return jsonify({'summary': item['ai_summary'], 'cached': True})

        from llm_client import generate_text

        headline = item['headline'] or ''
        body = item['body'] or ''
        source = item['source'] or ''

        is_url = body.strip().startswith('http')
        content = headline if is_url else f"{headline}. {body}"

        prompt = (
            "Write a 2-3 sentence summary of this AI news item for readers of an AI benchmark tracking site.\n"
            "Be factual, concise, and explain why this matters to someone following AI model performance.\n"
            "Do not start with 'This article' or 'This post'. Write in present tense.\n"
            "Do not make up information — only summarize what is provided.\n\n"
            f"Source: {source}\n"
            f"Content: {content}\n\n"
            "Summary:"
        )

        summary = generate_text(prompt, temperature=0.3, max_tokens=120, timeout=30) or ''

        for prefix in ['Summary:', "Here is a summary:", "Here's a summary:"]:
            if summary.startswith(prefix):
                summary = summary[len(prefix):].strip()

        if summary and len(summary) > 20:
            conn.execute(
                'UPDATE feed_entries SET ai_summary = ? WHERE id = ?',
                (summary, entry_id)
            )
            conn.commit()
            conn.close()
            return jsonify({'summary': summary, 'cached': False})
        else:
            conn.close()
            return jsonify({'summary': None})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@app.route('/api/feed/entry/<int:entry_id>')
def api_feed_entry(entry_id):
    conn = sqlite3.connect(DB_NAME)
    try:
        df = pd.read_sql_query(
            "SELECT * FROM feed_entries WHERE id = ? LIMIT 1",
            conn, params=(entry_id,)
        )
        if df.empty:
            conn.close()
            return jsonify({'error': 'Entry not found'}), 404
        record = convert_pandas_types(df.to_dict('records')[0])
        likes_row = conn.execute(
            "SELECT COUNT(*) FROM item_likes WHERE item_type='article' AND item_id=?",
            (str(entry_id),)
        ).fetchone()
        record['likes'] = likes_row[0] if likes_row else 0
        conn.close()
        return jsonify(record)
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@app.route('/api/feed')
def api_feed():
    batch_limit = int(request.args.get('batch_limit', 12))
    batch_offset = int(request.args.get('batch_offset', 0))
    q = request.args.get('q', '').strip()
    conn = sqlite3.connect(DB_NAME)
    try:
        if q:
            df = pd.read_sql_query(
                "SELECT * FROM feed_entries WHERE status = 'approved' "
                "AND (headline LIKE ? OR source LIKE ?) "
                "ORDER BY created_at DESC LIMIT 100",
                conn, params=(f'%{q}%', f'%{q}%')
            )
            records = convert_pandas_types(df.to_dict('records'))
            if records:
                ids = [str(r['id']) for r in records]
                placeholders = ','.join(['?'] * len(ids))
                likes_df = pd.read_sql_query(
                    f"SELECT item_id, COUNT(*) as likes FROM item_likes "
                    f"WHERE item_type='article' AND item_id IN ({placeholders}) GROUP BY item_id",
                    conn, params=ids
                )
                likes_map = dict(zip(likes_df['item_id'].astype(str), likes_df['likes'].astype(int)))
                for r in records:
                    r['likes'] = likes_map.get(str(r['id']), 0)
            conn.close()
            return jsonify(records)

        all_runs = pd.read_sql_query(
            "SELECT DISTINCT run_id FROM feed_entries WHERE status = 'approved' "
            "ORDER BY run_id DESC",
            conn
        )
        if all_runs.empty:
            conn.close()
            return jsonify([])
        run_ids = all_runs['run_id'].tolist()[batch_offset:batch_offset + batch_limit]
        if not run_ids:
            conn.close()
            return jsonify([])
        placeholders_runs = ','.join(['?'] * len(run_ids))
        df = pd.read_sql_query(
            f"SELECT * FROM feed_entries WHERE status = 'approved' AND run_id IN ({placeholders_runs}) "
            "ORDER BY run_id DESC, "
            "CASE tier WHEN 'big' THEN 1 WHEN 'moderate' THEN 2 WHEN 'small' THEN 3 END ASC, "
            "created_at DESC",
            conn, params=run_ids
        )
        records = convert_pandas_types(df.to_dict('records'))
        if records:
            ids = [str(r['id']) for r in records]
            placeholders = ','.join(['?'] * len(ids))
            likes_df = pd.read_sql_query(
                f"SELECT item_id, COUNT(*) as likes FROM item_likes "
                f"WHERE item_type='article' AND item_id IN ({placeholders}) GROUP BY item_id",
                conn, params=ids
            )
            likes_map = dict(zip(likes_df['item_id'].astype(str), likes_df['likes'].astype(int)))
            for r in records:
                r['likes'] = likes_map.get(str(r['id']), 0)
        conn.close()
        return jsonify(records)
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)})


@app.route('/api/admin/retag-models')
def retag_models():
    """Retroactively tag existing news_scanner articles with detected model names."""
    conn = sqlite3.connect(DB_NAME)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT canonical_name FROM name_normalizations WHERE canonical_name IS NOT NULL"
        )
        tracked_models = sorted([r[0] for r in cursor.fetchall() if r[0]], key=len, reverse=True)

        if not tracked_models:
            conn.close()
            return jsonify({'tagged': 0, 'message': 'No tracked models in DB yet'})

        df = pd.read_sql_query(
            "SELECT id, headline, body FROM feed_entries WHERE type = 'news_scanner'",
            conn
        )

        import re as _re

        def _detect(text_lower, models):
            for m in models:
                m_lower = m.lower()
                if len(m_lower) >= 4:
                    if m_lower in text_lower:
                        return m
                else:
                    if _re.search(r'(?<![a-zA-Z0-9])' + _re.escape(m_lower) + r'(?![a-zA-Z0-9])', text_lower):
                        return m
            return None

        tagged = 0
        for _, row in df.iterrows():
            text_lower = (str(row['headline'] or '') + ' ' + str(row['body'] or '')).lower()
            detected = _detect(text_lower, tracked_models)
            conn.execute("UPDATE feed_entries SET model = ? WHERE id = ?", (detected, int(row['id'])))
            if detected:
                tagged += 1

        conn.commit()
        conn.close()
        return jsonify({'tagged': tagged, 'total': len(df), 'tracked_models': len(tracked_models)})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@app.route('/api/sources')
def api_sources():
    source_count = len(SOURCES)
    if source_count == 0:
        return jsonify([])
    base_weight = round(100.0 / source_count)
    weights = [base_weight] * source_count
    weights[-1] = 100 - sum(weights[:-1])
    response = []
    for source, weight in zip(SOURCES, weights):
        name = source.get('name', '')
        label = source.get('label') or name.replace('_', ' ').replace('-', ' ').title()
        item = dict(source)
        item['weight'] = int(weight)
        item['label'] = label
        response.append(item)
    return jsonify(convert_pandas_types(response))


@app.route('/api/stats')
def api_stats():
    conn = sqlite3.connect(DB_NAME)
    try:
        models_count = pd.read_sql_query("SELECT COUNT(DISTINCT model) as count FROM snapshots", conn).iloc[0]['count']
        feed_count = pd.read_sql_query("SELECT COUNT(*) as count FROM feed_entries", conn).iloc[0]['count']
        last_update = pd.read_sql_query("SELECT MAX(snapshot_timestamp) as last FROM snapshots", conn).iloc[0]['last']
        conn.close()
        return jsonify({
            'models': int(models_count),
            'feed_entries': int(feed_count),
            'sources': len(SOURCES),
            'last_update': last_update
        })
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)})


@app.route('/api/stats/weekly')
def api_weekly_stats():
    conn = sqlite3.connect(DB_NAME)
    try:
        from datetime import datetime, timedelta
        seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()

        rank_changes = pd.read_sql_query('''
            SELECT COUNT(*) as count FROM feed_entries
            WHERE type = 'rank_change'
            AND created_at > ?
            AND status = 'approved'
        ''', conn, params=(seven_days_ago,)).iloc[0]['count']

        new_models = pd.read_sql_query('''
            SELECT COUNT(*) as count FROM feed_entries
            WHERE type = 'new_model'
            AND created_at > ?
            AND status = 'approved'
        ''', conn, params=(seven_days_ago,)).iloc[0]['count']

        feed_entries = pd.read_sql_query('''
            SELECT COUNT(*) as count FROM feed_entries
            WHERE created_at > ?
            AND status = 'approved'
        ''', conn, params=(seven_days_ago,)).iloc[0]['count']

        news_items = pd.read_sql_query('''
            SELECT COUNT(*) as count FROM news_items
            WHERE created_at > ?
            AND status != 'discarded'
        ''', conn, params=(seven_days_ago,)).iloc[0]['count']

        models_tracked = pd.read_sql_query('''
            SELECT COUNT(DISTINCT normalized_model) as count
            FROM snapshots
            WHERE snapshot_timestamp > ?
        ''', conn, params=(seven_days_ago,)).iloc[0]['count']

        twenty_five_hours_ago = (datetime.now() - timedelta(hours=25)).isoformat()
        sources_live = pd.read_sql_query('''
            SELECT COUNT(DISTINCT source) as count FROM snapshots
            WHERE snapshot_timestamp > ?
        ''', conn, params=(twenty_five_hours_ago,)).iloc[0]['count']

        conn.close()
        return jsonify({
            'rank_changes': int(rank_changes),
            'new_models': int(new_models),
            'feed_entries': int(feed_entries),
            'news_items': int(news_items),
            'models_tracked': int(models_tracked),
            'sources_live': int(sources_live),
            'total_sources': len(SOURCES),
        })
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


# ============================================
# RSS FEED
# ============================================

@app.route('/feed.rss')
@app.route('/rss')
@app.route('/feed.xml')
def rss_feed():
    from flask import Response
    import email.utils

    models_param = request.args.get('models', '')
    watchlist_models = [m.strip() for m in models_param.split(',') if m.strip()]

    conn = sqlite3.connect(DB_NAME)
    try:
        df = pd.read_sql_query('''
            SELECT id, headline, body, source, tier, type, created_at, model
            FROM feed_entries
            WHERE status = 'approved'
            ORDER BY created_at DESC
            LIMIT 100
        ''', conn)
        conn.close()
    except Exception as e:
        conn.close()
        return Response('Error generating feed', status=500)

    if watchlist_models:
        def matches_watchlist(row):
            model_field = str(row.get('model', '') or '').lower()
            headline = str(row.get('headline', '') or '').lower()
            return any(
                w.lower() in model_field or w.lower() in headline
                for w in watchlist_models
            )
        df = df[df.apply(matches_watchlist, axis=1)]

    df = df.head(50)

    if watchlist_models:
        models_str = ', '.join(watchlist_models[:3])
        ellipsis = '...' if len(watchlist_models) > 3 else ''
        feed_title = f'AIBenchmark Watchlist — {models_str}{ellipsis}'
        feed_desc = f'Personalized AI benchmark feed tracking: {", ".join(watchlist_models)}'
    else:
        feed_title = 'AIBenchmark — AI Model Rankings & News'
        feed_desc = 'Live AI benchmark aggregator tracking model performance across 12 sources. Hourly updates on leaderboard changes, model releases, and AI news.'

    def format_rss_date(iso_string):
        try:
            dt = datetime.fromisoformat(str(iso_string).replace('Z', '+00:00'))
            return email.utils.format_datetime(dt)
        except Exception:
            return email.utils.format_datetime(datetime.now())

    def clean_description(headline, body, source):
        body_str = str(body or '')
        if body_str.strip().startswith('http'):
            return f'{headline} — via {source}'
        return f'{body_str[:300]}...' if len(body_str) > 300 else body_str or headline

    def tier_prefix(tier):
        prefixes = {'big': '[BIG MOVE] ', 'moderate': '[UPDATE] ', 'small': '[SHIFT] '}
        return prefixes.get(tier, '')

    def escape_xml(s):
        return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&apos;')

    items_xml = ''
    for _, row in df.iterrows():
        title = f"{tier_prefix(row['tier'])}{row['headline']}"
        description = clean_description(row['headline'], row['body'], row['source'])
        pub_date = format_rss_date(row['created_at'])
        link = f"https://aibenchmark.com/article/{row['id']}"
        source_label = str(row['source'] or 'AIBenchmark')

        items_xml += f'''
        <item>
            <title>{escape_xml(title)}</title>
            <description>{escape_xml(description)}</description>
            <link>{escape_xml(link)}</link>
            <guid isPermaLink="true">{escape_xml(link)}</guid>
            <pubDate>{pub_date}</pubDate>
            <source url="https://aibenchmark.com/feed.rss">{escape_xml(source_label)}</source>
            <category>{escape_xml(row['tier'] or 'update')}</category>
        </item>'''

    last_build = format_rss_date(df.iloc[0]['created_at']) if not df.empty else email.utils.format_datetime(datetime.now())

    rss_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
    <channel>
        <title>{escape_xml(feed_title)}</title>
        <link>https://aibenchmark.com</link>
        <description>{escape_xml(feed_desc)}</description>
        <language>en-us</language>
        <lastBuildDate>{last_build}</lastBuildDate>
        <ttl>60</ttl>
        <image>
            <url>https://aibenchmark.com/favicon.svg</url>
            <title>AIBenchmark</title>
            <link>https://aibenchmark.com</link>
        </image>
        <atom:link href="https://aibenchmark.com/feed.rss" rel="self" type="application/rss+xml"/>
        {items_xml}
    </channel>
</rss>'''

    return Response(
        rss_xml,
        mimetype='application/rss+xml',
        headers={
            'Cache-Control': 'public, max-age=3600',
            'X-Content-Type-Options': 'nosniff'
        }
    )


# ============================================
# DATA EXPLORER API ENDPOINTS
# ============================================

@app.route('/api/data/full')
def api_data_full():
    conn = sqlite3.connect(DB_NAME)
    try:
        source_data = {}
        for source in SOURCES:
            name = source['name']
            cursor = conn.cursor()
            cursor.execute(
                'SELECT MAX(snapshot_timestamp) FROM snapshots WHERE source = ?',
                (name,)
            )
            result = cursor.fetchone()
            if result and result[0]:
                latest_ts = result[0]
                df = pd.read_sql_query('''
                    SELECT model, normalized_model, score, rank, norm_combined,
                           snapshot_timestamp
                    FROM snapshots
                    WHERE source = ? AND snapshot_timestamp = ?
                ''', conn, params=(name, latest_ts))
                source_data[name] = {
                    'models': df.to_dict('records'),
                    'last_updated': latest_ts,
                    'model_count': len(df)
                }

        composites = get_composite_scores()
        prices = get_model_prices()

        conn.close()
        return jsonify(convert_pandas_types({
            'composites': composites.to_dict('records'),
            'sources': source_data,
            'source_list': SOURCES,
            'prices': prices,
            'generated_at': datetime.now().isoformat()
        }))
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@app.route('/api/data/prices')
def api_data_prices():
    prices = get_model_prices()
    if not prices:
        try:
            fetch_and_store_prices()
            prices = get_model_prices()
        except Exception:
            pass
    return jsonify(prices)


@app.route('/api/data/history/<path:model_name>')
def api_data_history(model_name):
    from urllib.parse import unquote
    decoded = unquote(model_name)
    conn = sqlite3.connect(DB_NAME)
    try:
        history = {}
        for source in SOURCES:
            name = source['name']
            df = pd.read_sql_query('''
                SELECT snapshot_timestamp, score, norm_combined, rank
                FROM snapshots
                WHERE source = ?
                AND (normalized_model = ? OR normalized_model LIKE ?)
                ORDER BY snapshot_timestamp ASC
                LIMIT 100
            ''', conn, params=(name, decoded, f'%{decoded}%'))
            if not df.empty:
                history[name] = df.to_dict('records')
        conn.close()
        return jsonify(convert_pandas_types(history))
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


# ============================================
# RUN
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print("=" * 60)
    print("🚀 Starting Web Interface")
    print("=" * 60)
    print(f"📁 Database: {DB_NAME}")
    print(f"📋 Sources: {len(SOURCES)}")
    print(f"🌐 Visit: http://localhost:{port}")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=port)
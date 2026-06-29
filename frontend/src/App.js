import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';
import { BrowserRouter, Routes, Route, useNavigate, Link } from 'react-router-dom';
import ModelPage from './ModelPage';
import ArticlePage from './ArticlePage';
import DataPage from './DataPage';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:5001/api';

const MAX_WIDTH = 2200;

function getSessionId() {
  let id = localStorage.getItem('tuff-session-id');
  if (!id) { id = `s-${Math.random().toString(36).slice(2, 10)}`; localStorage.setItem('tuff-session-id', id); }
  return id;
}

function getLikedItems() {
  try { return new Set(JSON.parse(localStorage.getItem('tuff-liked-items') || '[]')); } catch { return new Set(); }
}

function saveLikedItems(set) {
  localStorage.setItem('tuff-liked-items', JSON.stringify([...set]));
}

const API = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

function formatRelativeTime(date) {
  const seconds = Math.floor((new Date() - date) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)} days ago`;
  return date.toLocaleDateString();
}

function Home() {
  const navigate = useNavigate();
  const [models, setModels] = useState([]);
  const [feed, setFeed] = useState([]);
  const [sources, setSources] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [priceToggle, setPriceToggle] = useState(false);
  const [toggleLoading, setToggleLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [feedSearchQuery, setFeedSearchQuery] = useState('');
  const [votePair, setVotePair] = useState(null);
  const [voteLoading, setVoteLoading] = useState(false);
  const [communityRankings, setCommunityRankings] = useState([]);
  const [voteStats, setVoteStats] = useState({});
  const [weeklyStats, setWeeklyStats] = useState({});
  const [showRankings, setShowRankings] = useState(false);
  const [likedItems, setLikedItems] = useState(() => getLikedItems());
  const [likeCounts, setLikeCounts] = useState({});
  const [expandedFeed, setExpandedFeed] = useState([]);
  const [expandOffset, setExpandOffset] = useState(12);
  const [expandHasMore, setExpandHasMore] = useState(true);
  const [expandLoading, setExpandLoading] = useState(false);
  const [filters, setFilters] = useState({
    leaderboard: true,
    model_release: true,
    research_paper: true,
    general_news: true,
    benchmark: true,
  });
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);

  const [lastVisit, setLastVisit] = useState(null);
  const [newCount, setNewCount] = useState(0);

  useEffect(() => {
    const stored = localStorage.getItem('aibenchmark_last_visit');
    if (stored) {
      setLastVisit(new Date(stored));
    }
    localStorage.setItem('aibenchmark_last_visit', new Date().toISOString());
  }, []);

  const [watchlist, setWatchlist] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('aibenchmark_watchlist') || '[]');
    } catch {
      return [];
    }
  });
  const [watchlistOnly, setWatchlistOnly] = useState(false);
  const [searchResults, setSearchResults] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);

  const toggleWatchlist = (modelName) => {
    setWatchlist(prev => {
      const next = prev.includes(modelName)
        ? prev.filter(m => m !== modelName)
        : [...prev, modelName];
      localStorage.setItem('aibenchmark_watchlist', JSON.stringify(next));
      return next;
    });
  };

  useEffect(() => {
    const q = feedSearchQuery.trim();
    if (!q) { setSearchResults(null); setSearchLoading(false); return; }
    setSearchLoading(true);
    const timer = setTimeout(() => {
      API.get(`/feed?q=${encodeURIComponent(q)}`)
        .then(res => setSearchResults(Array.isArray(res.data) ? res.data : []))
        .catch(() => setSearchResults([]))
        .finally(() => setSearchLoading(false));
    }, 300);
    return () => clearTimeout(timer);
  }, [feedSearchQuery]);

  const mapFeedItemToFilter = (item) => {
    if (!item.type) return null;
    if (item.type === 'rank_change' || item.type === 'score_shift' || item.type === 'new_model') return 'leaderboard';
    if (item.type === 'news_scanner') {
      if (item.headline && item.headline.startsWith('New model:')) return 'model_release';
      if (item.headline && item.headline.startsWith('Benchmark alert:')) return 'benchmark';
      if (item.tier === 'small') {
        if (item.source && item.source.includes('arXiv')) return 'research_paper';
        return 'general_news';
      }
    }
    return null;
  };

  const filteredFeed = feed.filter(item => {
    const filterKey = mapFeedItemToFilter(item);
    return filterKey && filters[filterKey];
  });

  const sortedFeed = [...filteredFeed].sort((a, b) => {
    const aIsNew = lastVisit && new Date(a.created_at) > lastVisit;
    const bIsNew = lastVisit && new Date(b.created_at) > lastVisit;
    if (aIsNew && !bIsNew) return -1;
    if (!aIsNew && bIsNew) return 1;
    return new Date(b.created_at) - new Date(a.created_at);
  });

  const displayFeed = watchlistOnly && watchlist.length > 0
    ? sortedFeed.filter(item =>
        watchlist.some(w =>
          (item.model && item.model.toLowerCase().includes(w.toLowerCase())) ||
          (item.headline && item.headline.toLowerCase().includes(w.toLowerCase()))
        )
      )
    : sortedFeed;

  const filteredModels = (() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return models;
    return models.filter(m => {
      const modelName = (m.model || '').toLowerCase();
      const raw = (m.raw_names || '').toLowerCase();
      if (modelName.includes(q)) return true;
      if (raw && raw.includes(q)) return true;
      if (q.includes('/')) {
        const last = q.split('/').pop();
        if (modelName.includes(last)) return true;
        if (raw && raw.includes(last)) return true;
      }
      return false;
    });
  })();

  const handlePriceToggle = async () => {
    if (toggleLoading) return;
    const next = !priceToggle;
    setPriceToggle(next);
    setToggleLoading(true);
    try {
      const res = await API.get(`/models?include_speed=${next}`);
      setModels(res.data.slice(0, 50));
    } catch (err) {
      console.error('Error fetching models with speed toggle:', err);
    } finally {
      setToggleLoading(false);
    }
  };

  const fetchVotePair = async () => {
    try {
      const response = await API.get('/vote/pair');
      setVotePair(response.data);
      setShowRankings(false);
    } catch (err) {
      console.error('Error fetching vote pair:', err);
    }
  };

  const submitVote = async (winner) => {
    if (!votePair || voteLoading) return;
    setVoteLoading(true);
    try {
      await API.post('/vote/submit', { model_a: votePair.model_a, model_b: votePair.model_b, winner });
      await fetchVotePair();
    } catch (err) {
      console.error('Error submitting vote:', err);
    } finally {
      setVoteLoading(false);
    }
  };

  const toggleLike = async (itemType, itemId, e) => {
    e.stopPropagation();
    const key = `${itemType}_${itemId}`;
    const liked = likedItems.has(key);
    const endpoint = liked ? '/items/unlike' : '/items/like';
    try {
      const res = await API.post(endpoint, { item_type: itemType, item_id: String(itemId), session_id: getSessionId() });
      const newSet = new Set(likedItems);
      if (liked) newSet.delete(key); else newSet.add(key);
      setLikedItems(newSet);
      saveLikedItems(newSet);
      setLikeCounts(prev => ({ ...prev, [key]: res.data.likes }));
    } catch (err) {
      console.error('Like error:', err);
    }
  };

  const fetchRankings = async () => {
    try {
      const response = await API.get('/vote/rankings?limit=10');
      setCommunityRankings(response.data);
      setShowRankings(true);
    } catch (err) {
      console.error('Error fetching rankings:', err);
    }
  };

  const handleExpand = async () => {
    setExpandLoading(true);
    try {
      const res = await API.get(`/feed?batch_limit=12&batch_offset=${expandOffset}`);
      const items = res.data.filter(item => item.status === 'approved');
      if (items.length === 0) {
        setExpandHasMore(false);
      } else {
        const counts = { ...likeCounts };
        items.forEach(item => { counts[`article_${item.id}`] = item.likes || 0; });
        setLikeCounts(counts);
        setExpandedFeed(prev => [...prev, ...items]);
        setExpandOffset(prev => prev + 12);
        if (items.length < 1) setExpandHasMore(false);
      }
    } catch (err) {
      console.error('Expand error:', err);
    } finally {
      setExpandLoading(false);
    }
  };

  useEffect(() => {
    Promise.all([
      API.get('/models'),
      API.get('/feed'),
      API.get('/sources'),
      API.get('/stats'),
      API.get('/vote/stats'),
      API.get('/stats/weekly'),
    ])
      .then(([modelsRes, feedRes, sourcesRes, statsRes, voteStatsRes, weeklyRes]) => {
        setModels(modelsRes.data.slice(0, 50));
        const feedItems = feedRes.data.filter(item => item.status === 'approved');
        setFeed(feedItems);
        const stored = localStorage.getItem('aibenchmark_last_visit');
        if (stored) {
          const lastVisitDate = new Date(stored);
          const newItems = feedRes.data.filter(item =>
            item.status === 'approved' &&
            new Date(item.created_at) > lastVisitDate
          );
          setNewCount(newItems.length);
        }
        const counts = {};
        feedItems.forEach(item => { counts[`article_${item.id}`] = item.likes || 0; });
        modelsRes.data.slice(0, 50).forEach(m => { counts[`model_${m.model}`] = m.likes || 0; });
        setLikeCounts(counts);
        setSources(sourcesRes.data);
        setStats(statsRes.data);
        setVoteStats(voteStatsRes.data);
        setWeeklyStats(weeklyRes.data);
        setLoading(false);
        fetchVotePair();
      })
      .catch(err => {
        console.error('Error fetching data:', err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', fontFamily: 'sans-serif', color: '#4f46e5' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>🤖</div>
          <div style={{ fontSize: 18, fontWeight: 600 }}>Loading benchmark data...</div>
        </div>
      </div>
    );
  }

  const tierConfig = {
    big: { label: 'BIG MOVE', color: '#ef4444', bg: '#fef2f2', border: '#fecaca' },
    moderate: { label: 'UPDATE', color: '#d97706', bg: '#fffbeb', border: '#fde68a' },
    small: { label: 'SHIFT', color: '#16a34a', bg: '#f0fdf4', border: '#bbf7d0' },
  };

  return (
    <div style={{ fontFamily: "'Inter', system-ui, sans-serif", background: '#f7f6ff', minHeight: '100vh', color: '#18181b' }}>

      {/* Top bar — full width */}
      <div style={{ background: '#4f46e5', color: 'white', height: 52, position: 'sticky', top: 0, zIndex: 100 }}>
        <div style={{ maxWidth: MAX_WIDTH, margin: '0 auto', padding: '0 24px', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontWeight: 800, fontSize: 18, letterSpacing: '-0.5px' }}>TUFF AI</span>
            <span style={{ background: 'rgba(255,255,255,0.15)', borderRadius: 20, padding: '2px 10px', fontSize: 11, fontWeight: 600, letterSpacing: '0.5px' }}>BENCHMARK</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 13 }}>
            <span style={{ opacity: 0.8 }}>🟢 Live</span>
            {!isMobile && <span style={{ opacity: 0.7 }}>Updated {stats.last_update ? new Date(stats.last_update).toLocaleTimeString() : 'N/A'}</span>}
          </div>
        </div>
      </div>

      {/* Hero — full width white background */}
      <div style={{ background: 'white', borderBottom: '1px solid #e5e7fb' }}>
        <div style={{ maxWidth: MAX_WIDTH, margin: '0 auto', padding: '20px 24px 0' }}>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
            <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.5px' }}>Today's Rankings</h1>
            <span style={{ fontSize: 13, color: '#71717a' }}>{stats.sources || 0} sources · {stats.models || 0} models tracked</span>
            <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 12, color: '#71717a' }}>Include cost/speed</span>
              <div onClick={handlePriceToggle} style={{ width: 36, height: 20, borderRadius: 10, background: priceToggle ? '#4f46e5' : '#d4d4d8', cursor: toggleLoading ? 'not-allowed' : 'pointer', position: 'relative', transition: 'background 0.2s', opacity: toggleLoading ? 0.6 : 1 }}>
                <div style={{ position: 'absolute', top: 2, left: priceToggle ? 18 : 2, width: 16, height: 16, borderRadius: 8, background: 'white', transition: 'left 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.2)' }} />
              </div>
            </div>
          </div>

          <div style={{ marginTop: 10, marginBottom: 18, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <input type="text" value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Search models..." style={{ flex: 1, minWidth: 240, borderRadius: 12, border: '1px solid #d4d4d8', padding: '12px 14px', fontSize: 14, outline: 'none' }} />
            {searchQuery && <button onClick={() => setSearchQuery('')} style={{ border: 'none', background: '#e5e7eb', color: '#374151', padding: '10px 14px', borderRadius: 12, cursor: 'pointer', fontWeight: 600 }}>Clear</button>}
          </div>

          <div style={{ display: 'flex', gap: 10, overflowX: 'auto', paddingBottom: 16, scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch' }}>
            {filteredModels.length === 0 ? (
              <div style={{ color: '#71717a', fontSize: 13, padding: '18px 0' }}>No models match "{searchQuery}".</div>
            ) : filteredModels.map((m, i) => (
              <div key={m.model} style={{ position: 'relative', minWidth: 130, background: i === 0 ? '#4f46e5' : '#f7f6ff', border: `1px solid ${i === 0 ? '#4f46e5' : '#e5e7fb'}`, borderRadius: 10, padding: '12px 14px', flexShrink: 0, transition: 'transform 0.15s', cursor: 'pointer' }}
                onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'}
                onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}
                onClick={() => navigate(`/model/${encodeURIComponent(m.model)}`)}>
                <button
                  onClick={(e) => { e.stopPropagation(); toggleWatchlist(m.model); }}
                  style={{ position: 'absolute', top: 6, right: 6, background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, lineHeight: 1, opacity: watchlist.includes(m.model) ? 1 : 0.3, color: i === 0 ? 'white' : '#f59e0b', padding: 2 }}
                  title={watchlist.includes(m.model) ? 'Remove from watchlist' : 'Add to watchlist'}
                >
                  {watchlist.includes(m.model) ? '★' : '☆'}
                </button>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '1px', color: i === 0 ? 'rgba(255,255,255,0.7)' : '#a1a1aa', marginBottom: 4 }}>#{m.rank || i + 1}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: i === 0 ? 'white' : '#18181b', marginBottom: 6, lineHeight: 1.2 }}>{m.model}</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: i === 0 ? 'white' : '#4f46e5', lineHeight: 1 }}>{m.composite_score ? m.composite_score.toFixed(1) : '—'}</div>
                <div style={{ fontSize: 10, marginTop: 4, color: i === 0 ? 'rgba(255,255,255,0.6)' : '#a1a1aa' }}>{m.sources_available || 0}/{sources.length} sources</div>
                <button
                  onClick={(e) => toggleLike('model', m.model, e)}
                  style={{ marginTop: 6, background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontSize: 11, color: likedItems.has(`model_${m.model}`) ? '#ef4444' : (i === 0 ? 'rgba(255,255,255,0.5)' : '#a1a1aa'), fontWeight: 600 }}
                >
                  {likedItems.has(`model_${m.model}`) ? '❤️' : '🤍'} {likeCounts[`model_${m.model}`] ?? m.likes ?? 0}
                </button>
              </div>
            ))}
          </div>

        </div>
        <div style={{ height: 3, background: '#4f46e5' }} />
      </div>

      {/* Main content — full width bg, centered grid */}
      <div style={{ background: '#f7f6ff' }}>
        <div style={{ maxWidth: isMobile ? 'none' : MAX_WIDTH, margin: '0 auto', padding: isMobile ? '16px' : '24px', display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 320px', gap: isMobile ? 16 : 24 }}>

          {/* Feed */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <h2 style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.3px' }}>What changed</h2>
              <span style={{ background: '#ef4444', color: 'white', fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 4, letterSpacing: '0.5px' }}>LIVE</span>
            </div>
            {newCount > 0 && lastVisit && (
              <div style={{ background: '#eeedfe', border: '1px solid #c7d2fe', borderRadius: 8, padding: '10px 16px', marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 13 }}>
                <span style={{ color: '#4f46e5', fontWeight: 600 }}>
                  ✦ {newCount} new {newCount === 1 ? 'item' : 'items'} since your last visit
                </span>
                <span style={{ color: '#7c7ac9', fontSize: 11 }}>
                  Last visited {formatRelativeTime(lastVisit)}
                </span>
              </div>
            )}

            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              <input type="text" value={feedSearchQuery} onChange={e => setFeedSearchQuery(e.target.value)} placeholder="Search feed..." style={{ flex: 1, borderRadius: 10, border: '1px solid #d4d4d8', padding: '9px 12px', fontSize: 13, outline: 'none', background: 'white' }} />
              {feedSearchQuery && <button onClick={() => setFeedSearchQuery('')} style={{ border: 'none', background: '#e5e7eb', color: '#374151', padding: '9px 12px', borderRadius: 10, cursor: 'pointer', fontWeight: 600, fontSize: 13 }}>Clear</button>}
            </div>

            {isMobile && (
              <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 8, marginBottom: 12, scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch' }}>
                {[
                  { key: 'leaderboard', label: '☰ Leaderboard' },
                  { key: 'model_release', label: '🤖 Models' },
                  { key: 'research_paper', label: '📄 Papers' },
                  { key: 'general_news', label: '📰 News' },
                  { key: 'benchmark', label: '⚠️ Benchmarks' },
                ].map(filter => (
                  <button key={filter.key}
                    onClick={() => setFilters({ ...filters, [filter.key]: !filters[filter.key] })}
                    style={{
                      flexShrink: 0, padding: '6px 14px', borderRadius: 20,
                      border: `1px solid ${filters[filter.key] ? '#4f46e5' : '#d4d4d8'}`,
                      background: filters[filter.key] ? '#4f46e5' : 'white',
                      color: filters[filter.key] ? 'white' : '#52525b',
                      fontSize: 12, fontWeight: 600, cursor: 'pointer',
                      whiteSpace: 'nowrap'
                    }}>
                    {filter.label}
                  </button>
                ))}
              </div>
            )}

            {feed.length === 0 ? (
              <div style={{ background: 'white', padding: 30, borderRadius: 10, textAlign: 'center', color: '#a1a1aa' }}>No feed entries yet. Changes will appear here when detected.</div>
            ) : watchlistOnly && watchlist.length > 0 && displayFeed.length === 0 ? (
              <div style={{ background: 'white', padding: 30, borderRadius: 10, textAlign: 'center', color: '#a1a1aa' }}>
                <div style={{ fontSize: 30, marginBottom: 8 }}>★</div>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>No recent activity for your watchlist</div>
                <div style={{ fontSize: 12 }}>Changes to {watchlist.join(', ')} will appear here when detected</div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {searchLoading && <div style={{ background: 'white', padding: 16, borderRadius: 10, textAlign: 'center', color: '#a1a1aa', fontSize: 13 }}>Searching all articles...</div>}
                {feedSearchQuery.trim() && !searchLoading && searchResults !== null && searchResults.filter(item => { const k = mapFeedItemToFilter(item); return k && filters[k]; }).length === 0 && (
                  <div style={{ background: 'white', padding: 20, borderRadius: 10, textAlign: 'center', color: '#a1a1aa', fontSize: 13 }}>No articles match "{feedSearchQuery}"</div>
                )}
                {(feedSearchQuery.trim()
                  ? (searchResults || []).filter(item => { const k = mapFeedItemToFilter(item); return k && filters[k]; })
                  : [...displayFeed, ...expandedFeed.filter(item => { const k = mapFeedItemToFilter(item); return k && filters[k]; })]
                ).map(item => {
                  const tier = tierConfig[item.tier] || tierConfig.moderate;
                  const isNew = lastVisit && new Date(item.created_at) > lastVisit;
                  return (
                    <div key={item.id} style={{ background: 'white', border: `1px solid ${isNew ? '#a5b4fc' : tier.border}`, borderRadius: 10, padding: isMobile ? '12px 14px' : '16px 18px', display: 'flex', gap: 14, transition: 'box-shadow 0.15s', cursor: 'pointer' }}
                      onClick={() => navigate(`/article/${item.id}`)}
                      onMouseEnter={e => e.currentTarget.style.boxShadow = '0 4px 16px rgba(79,70,229,0.08)'}
                      onMouseLeave={e => e.currentTarget.style.boxShadow = 'none'}>
                      <div style={{ minWidth: 56, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-start', paddingTop: 2 }}>
                        <div style={{ background: tier.bg, border: `1.5px solid ${tier.border}`, borderRadius: 6, padding: '4px 6px', textAlign: 'center' }}>
                          <div style={{ fontSize: 9, fontWeight: 800, letterSpacing: '1px', color: tier.color, lineHeight: 1 }}>{tier.label}</div>
                        </div>
                        {isNew && (
                          <div style={{ fontSize: 8, fontWeight: 800, letterSpacing: '0.5px', color: 'white', background: '#22c55e', borderRadius: 4, padding: '2px 5px', marginTop: 4, textAlign: 'center', animation: 'pulse 2s infinite' }}>
                            NEW
                          </div>
                        )}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: isMobile ? 14 : 15, fontWeight: 700, lineHeight: 1.3, marginBottom: 6, color: '#18181b', ...(isMobile && { wordBreak: 'break-word', overflowWrap: 'anywhere' }) }}>{item.headline}</div>
                        <div style={{ fontSize: 13, color: '#52525b', lineHeight: 1.5, marginBottom: 8, ...(isMobile && { wordBreak: 'break-word', overflowWrap: 'anywhere' }) }}>
                          {item.body && item.body.startsWith('http') ? (() => {
                            let domain = '';
                            try { domain = new URL(item.body).hostname.replace(/^www\./, ''); } catch { domain = item.body; }
                            return <a href={item.body} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} style={{ color: '#4f46e5', textDecoration: 'none', fontWeight: 600 }}>{domain} · Read article →</a>;
                          })() : item.body}
                        </div>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 11, flexWrap: 'wrap' }}>
                          <span style={{ background: '#ede9fe', color: '#5b21b6', padding: '2px 8px', borderRadius: 4, fontWeight: 600 }}>{sources.find(s => s.name === item.source)?.label || item.source}</span>
                          {item.type === 'news_scanner' && item.model && (
                            <span
                              onClick={e => { e.stopPropagation(); navigate(`/model/${encodeURIComponent(item.model)}`); }}
                              style={{ background: '#fef3c7', color: '#92400e', padding: '2px 8px', borderRadius: 4, fontWeight: 600, cursor: 'pointer' }}
                            >
                              {item.model}
                            </span>
                          )}
                          <span style={{ color: '#a1a1aa' }}>{item.created_at}</span>
                          <button
                            onClick={(e) => toggleLike('article', item.id, e)}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px 6px', borderRadius: 4, fontSize: 12, color: likedItems.has(`article_${item.id}`) ? '#ef4444' : '#a1a1aa', fontWeight: 600 }}
                          >
                            {likedItems.has(`article_${item.id}`) ? '❤️' : '🤍'} {likeCounts[`article_${item.id}`] ?? item.likes ?? 0}
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
                {!feedSearchQuery.trim() && expandHasMore && (
                  <div style={{ textAlign: 'center', paddingTop: 6, paddingBottom: 2 }}>
                    <button onClick={handleExpand} disabled={expandLoading} style={{ background: 'none', border: '1px solid #e5e7fb', borderRadius: 8, padding: '7px 20px', fontSize: 12, fontWeight: 600, color: '#71717a', cursor: expandLoading ? 'not-allowed' : 'pointer', opacity: expandLoading ? 0.6 : 1 }}>
                      {expandLoading ? 'Loading...' : 'Expand ▼'}
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Sidebar */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

            {/* Feed Filters */}
            {!isMobile && <div style={{ background: 'white', borderRadius: 10, border: '1px solid #e5e7fb', padding: '18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <h3 style={{ fontSize: 13, fontWeight: 800, letterSpacing: '0.5px', color: '#52525b', textTransform: 'uppercase' }}>Feed Filters</h3>
                <button onClick={() => { const allActive = Object.values(filters).every(v => v); setFilters(Object.keys(filters).reduce((acc, key) => { acc[key] = !allActive; return acc; }, {})); }} style={{ fontSize: 11, color: '#4f46e5', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
                  {Object.values(filters).every(v => v) ? 'None' : 'All'}
                </button>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {[
                  { key: 'leaderboard', label: '☰ Leaderboard Changes' },
                  { key: 'model_release', label: '🤖 Model Releases' },
                  { key: 'research_paper', label: '📄 Research Papers' },
                  { key: 'general_news', label: '📰 General News' },
                  { key: 'benchmark', label: '⚠️ Benchmark Alerts' },
                ].map(filter => (
                  <label key={filter.key} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, color: '#52525b' }}>
                    <input type="checkbox" checked={filters[filter.key]} onChange={(e) => setFilters({ ...filters, [filter.key]: e.target.checked })} style={{ width: 16, height: 16, cursor: 'pointer', accentColor: '#4f46e5' }} />
                    <span>{filter.label}</span>
                  </label>
                ))}
              </div>
            </div>}

            {/* Watchlist */}
            {!isMobile && (
              <div style={{ background: 'white', borderRadius: 10, border: '1px solid #e5e7fb', padding: '18px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <h3 style={{ fontSize: 13, fontWeight: 800, letterSpacing: '0.5px', color: '#52525b', textTransform: 'uppercase' }}>★ Watchlist</h3>
                  {watchlist.length > 0 && (
                    <button
                      onClick={() => setWatchlistOnly(!watchlistOnly)}
                      style={{ fontSize: 11, color: watchlistOnly ? 'white' : '#4f46e5', background: watchlistOnly ? '#4f46e5' : 'none', border: '1px solid #4f46e5', borderRadius: 6, padding: '2px 10px', cursor: 'pointer', fontWeight: 600 }}
                    >
                      {watchlistOnly ? 'All feed' : 'Filter feed'}
                    </button>
                  )}
                </div>
                {watchlist.length === 0 ? (
                  <div style={{ fontSize: 12, color: '#a1a1aa', textAlign: 'center', padding: '12px 0' }}>
                    <div style={{ fontSize: 20, marginBottom: 6 }}>☆</div>
                    Star models on the leaderboard to track them here
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {watchlist.map(modelName => {
                      const modelData = models.find(m => m.model === modelName);
                      return (
                        <div key={modelName} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '1px solid #f4f4f5', fontSize: 13 }}>
                          <span onClick={() => navigate(`/model/${encodeURIComponent(modelName)}`)} style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer', color: '#18181b', fontWeight: 500 }}>
                            {modelName}
                          </span>
                          {modelData && (
                            <span style={{ fontSize: 12, fontWeight: 700, color: '#4f46e5' }}>{modelData.composite_score?.toFixed(1)}</span>
                          )}
                          <button onClick={() => toggleWatchlist(modelName)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#f59e0b', fontSize: 14, padding: 0, lineHeight: 1 }}>★</button>
                        </div>
                      );
                    })}
                    <a
                      href={`/feed.rss?models=${encodeURIComponent(watchlist.join(','))}`}
                      target="_blank"
                      rel="noreferrer"
                      style={{ fontSize: 11, color: '#4f46e5', textDecoration: 'none', display: 'block', marginTop: 8, textAlign: 'center' }}
                    >
                      Subscribe to watchlist RSS ↗
                    </a>
                  </div>
                )}
              </div>
            )}

            {/* Community Sentiment */}
            <div style={{ background: 'white', borderRadius: 10, border: '1px solid #e5e7fb', padding: '18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <h3 style={{ fontSize: 13, fontWeight: 800, letterSpacing: '0.5px', color: '#52525b', textTransform: 'uppercase' }}>Community Sentiment</h3>
                <button onClick={() => { if (!showRankings) { fetchRankings(); } else { setShowRankings(false); } }} style={{ fontSize: 11, color: '#4f46e5', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
                  {showRankings ? '← Vote' : 'Rankings →'}
                </button>
              </div>
              <p style={{ fontSize: 11, color: '#a1a1aa', marginBottom: 14 }}>{voteStats.total_votes || 0} total votes · {voteStats.total_models || 0} models</p>

              {showRankings ? (
                <div>
                  {communityRankings.length === 0 ? (
                    <div style={{ textAlign: 'center', color: '#a1a1aa', fontSize: 13 }}>No rankings yet. Be the first to vote!</div>
                  ) : communityRankings.slice(0, 50).map((item, i) => (
                    <div key={item.model} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '1px solid #f4f4f5', fontSize: 13 }}>
                      <span style={{ fontWeight: 700, color: i < 3 ? '#4f46e5' : '#71717a', width: 24 }}>#{i + 1}</span>
                      <span onClick={() => navigate(`/model/${encodeURIComponent(item.model)}`)} style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer', color: '#111' }}>{item.model}</span>
                      <span style={{ fontWeight: 700, color: '#4f46e5' }}>{Number(item.rating).toFixed(0)}</span>
                    </div>
                  ))}
                  <button onClick={fetchRankings} style={{ width: '100%', padding: '8px', marginTop: 10, borderRadius: 6, border: '1px solid #e5e7fb', background: 'white', cursor: 'pointer', fontSize: 12, color: '#71717a' }}>Refresh Rankings</button>
                </div>
              ) : votePair ? (
                <div style={{ background: '#f7f6ff', borderRadius: 8, padding: '14px', textAlign: 'center', border: '1px dashed #c7d2fe' }}>
                  <div style={{ fontSize: 22, marginBottom: 6 }}>🗳️</div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Which is better?</div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={() => submitVote(votePair.model_a)} disabled={voteLoading} style={{ flex: 1, padding: '10px 8px', borderRadius: 6, border: '1px solid #c7d2fe', background: 'white', fontSize: 12, fontWeight: 600, cursor: voteLoading ? 'not-allowed' : 'pointer', color: '#4f46e5', opacity: voteLoading ? 0.6 : 1 }}>{votePair.model_a}</button>
                    <button onClick={() => submitVote(votePair.model_b)} disabled={voteLoading} style={{ flex: 1, padding: '10px 8px', borderRadius: 6, border: '1px solid #c7d2fe', background: 'white', fontSize: 12, fontWeight: 600, cursor: voteLoading ? 'not-allowed' : 'pointer', color: '#4f46e5', opacity: voteLoading ? 0.6 : 1 }}>{votePair.model_b}</button>
                  </div>
                  <button onClick={fetchVotePair} disabled={voteLoading} style={{ marginTop: 10, padding: '6px 12px', fontSize: 11, color: '#4f46e5', background: 'none', border: 'none', cursor: voteLoading ? 'not-allowed' : 'pointer', textDecoration: 'underline' }}>Skip</button>
                </div>
              ) : (
                <div style={{ textAlign: 'center', color: '#a1a1aa', padding: '10px' }}>Loading vote pair...</div>
              )}
            </div>

            {/* This Week */}
            <div style={{ background: '#4f46e5', borderRadius: 10, padding: '18px', color: 'white' }}>
              <h3 style={{ fontSize: 13, fontWeight: 800, marginBottom: 14, letterSpacing: '0.5px', opacity: 0.7, textTransform: 'uppercase' }}>This Week</h3>
              {[
                ['Rank changes', weeklyStats.rank_changes ?? '—'],
                ['New models', weeklyStats.new_models ?? '—'],
                ['News items', weeklyStats.news_items ?? '—'],
                ['Sources live', weeklyStats.sources_live != null ? `${weeklyStats.sources_live}/${weeklyStats.total_sources}` : '—'],
                ['Feed entries', weeklyStats.feed_entries ?? '—'],
              ].map(([label, val]) => (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10, fontSize: 13 }}>
                  <span style={{ opacity: 0.75 }}>{label}</span>
                  <strong>{val}</strong>
                </div>
              ))}
            </div>

          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={{ background: '#f7f6ff' }}>
        <div style={{ maxWidth: MAX_WIDTH, margin: '0 auto', textAlign: 'center', padding: '16px 24px 32px', fontSize: 12, color: '#a1a1aa' }}>
          Data updates hourly · Methodology is public · Not affiliated with any lab
          {' · '}
          <Link to="/methodology" style={{ color: '#a1a1aa', textDecoration: 'none' }}>Methodology &amp; Sources →</Link>
          {' · '}
          <Link to="/privacy" style={{ color: '#a1a1aa', textDecoration: 'none' }}>Privacy Policy →</Link>
          {' · '}
          <a href="/feed.rss" style={{ color: '#a1a1aa', textDecoration: 'none' }}>RSS ↗</a>
          {' · '}
          <Link to="/data" style={{ color: '#a1a1aa', textDecoration: 'none' }}>Data Explorer →</Link>
        </div>
      </div>

    </div>
  );
}

const METHODOLOGY_SOURCES = [
  { name: 'lmaena_text',               category: 'Human Preference',      weight: '12.5%', notes: '' },
  { name: 'lmaena_code',               category: 'Human Preference',      weight: '12.5%', notes: '' },
  { name: 'mmlu_pro',                  category: 'Reasoning & Knowledge', weight: '6.25%', notes: '' },
  { name: 'gpqa_diamond',              category: 'Reasoning & Knowledge', weight: '6.25%', notes: '' },
  { name: 'humanity_last_exam',        category: 'Reasoning & Knowledge', weight: '6.25%', notes: '' },
  { name: 'aime_2025',                 category: 'Reasoning & Knowledge', weight: '6.25%', notes: '' },
  { name: 'swe_bench',                 category: 'Coding',                weight: '6.25%', notes: '' },
  { name: 'livecodebench',             category: 'Coding',                weight: '6.25%', notes: '' },
  { name: 'aider_polyglot',            category: 'Coding',                weight: '6.25%', notes: '' },
  { name: 'scicode',                   category: 'Coding',                weight: '6.25%', notes: '' },
  { name: 'terminal_bench',            category: 'Agentic',               weight: '25%',   notes: 'Down-weighted: documented reward-hacking exploit' },
  { name: 'artificial_analysis_speed', category: 'Cost / Speed',          weight: '0%',    notes: 'Toggle-only: excluded from base composite' },
];

function MethodologyPage() {
  const navigate = useNavigate();
  return (
    <div style={{ fontFamily: "'Inter', system-ui, sans-serif", background: '#f7f6ff', minHeight: '100vh', color: '#18181b' }}>
      <div style={{ background: '#4f46e5', color: 'white', height: 52, position: 'sticky', top: 0, zIndex: 100 }}>
        <div style={{ maxWidth: MAX_WIDTH, margin: '0 auto', padding: '0 24px', height: '100%', display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={() => navigate('/')} style={{ background: 'transparent', border: 'none', color: 'white', fontSize: 20, cursor: 'pointer', padding: 0 }}>←</button>
          <span style={{ fontWeight: 800, fontSize: 18, letterSpacing: '-0.5px' }}>TUFF AI</span>
          <span style={{ background: 'rgba(255,255,255,0.15)', borderRadius: 20, padding: '2px 10px', fontSize: 11, fontWeight: 600, letterSpacing: '0.5px' }}>BENCHMARK</span>
        </div>
      </div>

      <div style={{ maxWidth: 860, margin: '32px auto', padding: '0 24px' }}>
        <div style={{ background: 'white', borderRadius: 12, border: '1px solid #e5e7fb', padding: '28px 32px' }}>
          <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 12 }}>Methodology &amp; Sources</h1>
          <p style={{ fontSize: 14, color: '#52525b', lineHeight: 1.7, marginBottom: 28 }}>
            This page documents how the composite score is calculated, which sources are included,
            their weights, and any integrity concerns. Full documentation coming soon.
          </p>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: '2px solid #e5e7fb' }}>
                {['Source', 'Category', 'Weight', 'Notes'].map(h => (
                  <th key={h} style={{ padding: '8px 12px', fontWeight: 700, color: '#52525b' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {METHODOLOGY_SOURCES.map((row, i) => (
                <tr key={row.name} style={{ borderBottom: '1px solid #f4f4f5', background: i % 2 === 0 ? 'white' : '#fafaf9' }}>
                  <td style={{ padding: '9px 12px', fontFamily: 'monospace', fontSize: 12, color: '#4f46e5' }}>{row.name}</td>
                  <td style={{ padding: '9px 12px', color: '#52525b' }}>{row.category}</td>
                  <td style={{ padding: '9px 12px', fontWeight: 700 }}>{row.weight}</td>
                  <td style={{ padding: '9px 12px', color: row.notes ? '#b45309' : '#a1a1aa', fontStyle: row.notes ? 'normal' : 'italic' }}>{row.notes || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        <div style={{ marginTop: 32 }}>
            <h2 style={{ fontSize: 16, fontWeight: 800, marginBottom: 12 }}>Data Attribution</h2>
            <p style={{ fontSize: 13, color: '#52525b', lineHeight: 1.7 }}>
              Benchmark scores are sourced from the organizations listed above and are reproduced for informational and comparative purposes. This site conducts no original evaluations. LMArena data courtesy of the LMSYS Chatbot Arena project. MMLU-Pro data courtesy of TIGER-Lab. SWE-bench data courtesy of Princeton NLP. Evaluation data for GPQA Diamond, HLE, AIME 2025, LiveCodeBench, Terminal-Bench, and SciCode courtesy of Artificial Analysis. Aider Polyglot data courtesy of Paul Gauthier / aider.chat.
            </p>
          </div>
        </div>
      </div>

      <div style={{ textAlign: 'center', padding: '16px 24px 32px', fontSize: 12, color: '#a1a1aa' }}>
        Data updates hourly · Methodology is public · Not affiliated with any lab
        {' · '}
        <Link to="/methodology" style={{ color: '#a1a1aa', textDecoration: 'none' }}>Methodology &amp; Sources →</Link>
        {' · '}
        <Link to="/privacy" style={{ color: '#a1a1aa', textDecoration: 'none' }}>Privacy Policy →</Link>
      </div>
    </div>
  );
}

function PrivacyPage() {
  const navigate = useNavigate();
  return (
    <div style={{ fontFamily: "'Inter', system-ui, sans-serif", background: '#f7f6ff', minHeight: '100vh', color: '#18181b' }}>
      <div style={{ background: '#4f46e5', color: 'white', height: 52, position: 'sticky', top: 0, zIndex: 100 }}>
        <div style={{ maxWidth: MAX_WIDTH, margin: '0 auto', padding: '0 24px', height: '100%', display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={() => navigate('/')} style={{ background: 'transparent', border: 'none', color: 'white', fontSize: 20, cursor: 'pointer', padding: 0 }}>←</button>
          <span style={{ fontWeight: 800, fontSize: 18, letterSpacing: '-0.5px' }}>TUFF AI</span>
          <span style={{ background: 'rgba(255,255,255,0.15)', borderRadius: 20, padding: '2px 10px', fontSize: 11, fontWeight: 600, letterSpacing: '0.5px' }}>BENCHMARK</span>
        </div>
      </div>

      <div style={{ maxWidth: 860, margin: '32px auto', padding: '0 24px' }}>
        <div style={{ background: 'white', borderRadius: 12, border: '1px solid #e5e7fb', padding: '28px 32px' }}>
          <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Privacy Policy</h1>
          <p style={{ fontSize: 12, color: '#a1a1aa', marginBottom: 28 }}>Last updated: June 2026</p>

          {[
            {
              heading: 'What we collect',
              body: 'We collect no personal information. Comments and votes are associated with an anonymous session ID stored in your browser — we never ask for your name, email, or account. The session ID is used only to prevent duplicate votes and allow you to delete your own comments.',
            },
            {
              heading: "What we don't collect",
              body: 'We do not use tracking cookies, advertising pixels, or analytics that identify individual users. We do not sell, share, or monetize any data about visitors.',
            },
            {
              heading: 'Data from benchmark sources',
              body: 'All model scores displayed on this site are sourced from publicly available leaderboards and APIs. We do not conduct original evaluations. Sources are listed on the Methodology page.',
            },
            {
              heading: 'News content',
              body: 'Article headlines and links are sourced from public RSS feeds and news sites. We store only the title and URL of articles, not their full content.',
            },
            {
              heading: 'Comment moderation',
              body: 'Comments are reviewed by a locally-running open-source AI model (Qwen3 8B via Ollama). Comment text is not sent to any third-party service for moderation.',
            },
            {
              heading: 'Third-party services',
              body: 'This site uses Cloudflare for DNS and routing. Cloudflare may log IP addresses per their own privacy policy. We use no other third-party services that receive user data.',
            },
            {
              heading: 'Contact',
              body: 'This site is independently operated. For questions or concerns, open an issue on our GitHub repository.',
            },
          ].map((section, i) => (
            <div key={i} style={{ marginBottom: 24 }}>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8, color: '#18181b' }}>{section.heading}</h2>
              <p style={{ fontSize: 13, color: '#52525b', lineHeight: 1.7, margin: 0 }}>{section.body}</p>
            </div>
          ))}
        </div>
      </div>

      <div style={{ textAlign: 'center', padding: '16px 24px 32px', fontSize: 12, color: '#a1a1aa' }}>
        Data updates hourly · Methodology is public · Not affiliated with any lab
        {' · '}
        <Link to="/methodology" style={{ color: '#a1a1aa', textDecoration: 'none' }}>Methodology &amp; Sources →</Link>
        {' · '}
        <Link to="/privacy" style={{ color: '#a1a1aa', textDecoration: 'none' }}>Privacy Policy →</Link>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/model/:modelName" element={<ModelPage />} />
        <Route path="/article/:id" element={<ArticlePage />} />
        <Route path="/methodology" element={<MethodologyPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/data" element={<DataPage />} />
      </Routes>
    </BrowserRouter>
  );
}
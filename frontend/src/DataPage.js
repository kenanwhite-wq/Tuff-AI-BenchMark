import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
} from 'recharts';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:5001/api';
const API = axios.create({ baseURL: API_BASE_URL, timeout: 30000 });
const MAX_WIDTH = 1400;

const SOURCE_COLORS = [
  '#4f46e5', '#f59e0b', '#22c55e', '#ef4444',
  '#8b5cf6', '#06b6d4', '#f97316', '#84cc16',
];

const COMPOSITE_SERIES = [
  { key: '__composite__', label: 'Overall', cats: null },
  { key: '__reasoning__', label: 'Reasoning', cats: ['reasoning_knowledge'] },
  { key: '__coding__', label: 'Coding', cats: ['coding'] },
  { key: '__human_pref__', label: 'Human Pref', cats: ['human_preference'] },
  { key: '__agentic__', label: 'Agentic', cats: ['agentic', 'tool_use', 'agentic_tool_use'] },
];
const COMPOSITE_COLORS = ['#1e293b', '#6366f1', '#e879f9', '#10b981', '#f43f5e'];

const CATEGORY_ROWS = [
  { label: 'Overall', cats: null },
  { label: 'Reasoning', cats: ['reasoning_knowledge'] },
  { label: 'Coding', cats: ['coding'] },
  { label: 'Human Pref', cats: ['human_preference'] },
  { label: 'Agentic', cats: ['agentic', 'tool_use', 'agentic_tool_use'] },
];

// Short labels for table column headers
const SOURCE_ABBREV = {
  lmaena_text: 'Arena',
  lmaena_code: 'Arena-Code',
  mmlu_pro: 'MMLU-Pro',
  gpqa_diamond: 'GPQA',
  humanity_last_exam: 'HLE',
  aime_2025: 'AIME',
  swe_bench: 'SWE-bench',
  livecodebench: 'LCB',
  aider_polyglot: 'Aider',
  scicode: 'SciCode',
  terminal_bench: 'T-Bench',
  artificial_analysis_speed: 'Speed',
};

function abbrev(name) {
  return SOURCE_ABBREV[name] || name.replace(/_/g, ' ');
}

function relativeTime(ts) {
  if (!ts) return 'Unknown';
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins} minute${mins !== 1 ? 's' : ''} ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hour${hrs !== 1 ? 's' : ''} ago`;
  const days = Math.floor(hrs / 24);
  return `${days} day${days !== 1 ? 's' : ''} ago`;
}

function freshnessStatus(ts) {
  if (!ts) return '🔴';
  const hrs = (Date.now() - new Date(ts).getTime()) / 3600000;
  if (hrs <= 2) return '🟢';
  if (hrs <= 25) return '🟡';
  return '🔴';
}

function formatTimestamp(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  return `${mm}/${dd} ${hh}:${mi}`;
}

export default function DataPage() {
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [sortCol, setSortCol] = useState('composite_score');
  const [sortDir, setSortDir] = useState('desc');
  const [selectedModels, setSelectedModels] = useState([]);
  const [historyModel, setHistoryModel] = useState(null);
  const [historySearch, setHistorySearch] = useState('');
  const [historyDropdownOpen, setHistoryDropdownOpen] = useState(false);
  const [historyData, setHistoryData] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedHistorySrc, setSelectedHistorySrc] = useState(null);
  const [historyScoreMode, setHistoryScoreMode] = useState('composite');
  const [comparisonHistories, setComparisonHistories] = useState({});
  const [historyOverlay, setHistoryOverlay] = useState(false);
  const [showPrice, setShowPrice] = useState(false);
  const [prices, setPrices] = useState({});
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

  useEffect(() => {
    API.get('/data/full')
      .then(res => {
        setData(res.data);
        setPrices(res.data.prices || {});
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const sourceNames = useMemo(
    () => (data?.source_list || []).map(s => s.name),
    [data]
  );

  const getSourceScore = (modelName, srcName) => {
    const srcModels = data?.sources[srcName]?.models || [];
    const match = srcModels.find(sm =>
      sm.normalized_model === modelName || sm.model === modelName
    );
    return match?.norm_combined ?? null;
  };

  // Top-3 scores per source column (across all composites, not just current page)
  const top3PerSource = useMemo(() => {
    if (!data) return {};
    const result = {};
    sourceNames.forEach(sn => {
      const scores = (data.composites || [])
        .map(m => getSourceScore(m.model, sn))
        .filter(s => s !== null)
        .sort((a, b) => b - a);
      result[sn] = new Set(scores.slice(0, 3));
    });
    return result;
  }, [data, sourceNames]);

  const filteredSorted = useMemo(() => {
    if (!data) return [];
    let rows = data.composites || [];
    const q = search.trim().toLowerCase();
    if (q) rows = rows.filter(m => (m.model || '').toLowerCase().includes(q));

    rows = [...rows].sort((a, b) => {
      let av, bv;
      if (sortCol === 'composite_score') {
        av = a.composite_score ?? -Infinity;
        bv = b.composite_score ?? -Infinity;
      } else if (sortCol === 'sources_available') {
        av = a.sources_available ?? 0;
        bv = b.sources_available ?? 0;
      } else if (sortCol === 'model') {
        av = (a.model || '').toLowerCase();
        bv = (b.model || '').toLowerCase();
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      } else {
        const srcModels = data.sources[sortCol]?.models || [];
        const getScore = m => {
          const match = srcModels.find(sm =>
            sm.normalized_model === m.model || sm.model === m.model
          );
          return match?.norm_combined ?? -Infinity;
        };
        av = getScore(a);
        bv = getScore(b);
      }
      return sortDir === 'asc' ? av - bv : bv - av;
    });

    return rows;
  }, [data, search, sortCol, sortDir]);

  const sortedModels = filteredSorted;
  const totalCount = (data?.composites || []).length;
  const filteredCount = sortedModels.length;
  const pageRows = sortedModels.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(sortedModels.length / PAGE_SIZE);

  const handleSort = col => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('desc'); }
    setPage(0);
  };

  const toggleModel = (modelName) => {
    setSelectedModels(prev => {
      if (prev.includes(modelName)) return prev.filter(m => m !== modelName);
      if (prev.length >= 4) return prev;
      return [...prev, modelName];
    });
  };

  const fetchHistory = async (modelName) => {
    if (!modelName) { setHistoryData(null); return; }
    setHistoryLoading(true);
    setSelectedHistorySrc(null);
    setHistoryScoreMode('composite');
    try {
      const res = await API.get(`/data/history/${encodeURIComponent(modelName)}`);
      setHistoryData(res.data);
    } catch {
      setHistoryData(null);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    if (selectedModels.length < 2) { setComparisonHistories({}); return; }
    Promise.all(
      selectedModels.map(m =>
        API.get(`/data/history/${encodeURIComponent(m)}`).then(r => [m, r.data]).catch(() => [m, null])
      )
    ).then(results => {
      const map = {};
      results.forEach(([m, d]) => { if (d) map[m] = d; });
      setComparisonHistories(map);
    });
  }, [selectedModels]);

  const compHistoryByModel = useMemo(() => {
    const sourceList = data?.source_list || [];
    const result = {};
    Object.entries(comparisonHistories).forEach(([modelName, mHist]) => {
      if (!mHist) return;
      const allTs = new Set();
      Object.values(mHist).forEach(arr => arr.forEach(p => allTs.add(p.snapshot_timestamp)));
      result[modelName] = [...allTs].sort().map(ts => {
        const entry = { ts };
        COMPOSITE_SERIES.forEach(cs => {
          const srcKeys = cs.cats === null
            ? Object.keys(mHist)
            : sourceList.filter(s => cs.cats.includes(s.category)).map(s => s.name).filter(n => mHist[n]);
          const vals = srcKeys
            .map(k => mHist[k]?.find(p => p.snapshot_timestamp === ts)?.norm_combined ?? null)
            .filter(v => v !== null);
          entry[cs.key] = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
        });
        return entry;
      });
    });
    return result;
  }, [comparisonHistories, data]);

  const compHistoryOverlay = useMemo(() => {
    if (!Object.keys(comparisonHistories).length) return [];
    const sourceList = data?.source_list || [];
    const allTs = new Set();
    Object.values(comparisonHistories).forEach(mHist => {
      if (!mHist) return;
      Object.values(mHist).forEach(arr => arr.forEach(p => allTs.add(p.snapshot_timestamp)));
    });
    return [...allTs].sort().map(ts => {
      const entry = { ts };
      selectedModels.forEach((modelName, mi) => {
        const mHist = comparisonHistories[modelName];
        if (!mHist) return;
        COMPOSITE_SERIES.forEach(cs => {
          const srcKeys = cs.cats === null
            ? Object.keys(mHist)
            : sourceList.filter(s => cs.cats.includes(s.category)).map(s => s.name).filter(n => mHist[n]);
          const vals = srcKeys
            .map(k => mHist[k]?.find(p => p.snapshot_timestamp === ts)?.norm_combined ?? null)
            .filter(v => v !== null);
          entry[`${mi}___${cs.key}`] = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
        });
      });
      return entry;
    });
  }, [comparisonHistories, selectedModels, data]);

  const historyModelOptions = useMemo(() => {
    if (!data || !historySearch.trim()) return [];
    const q = historySearch.toLowerCase();
    return data.composites
      .filter(m => m.model.toLowerCase().includes(q))
      .slice(0, 10);
  }, [data, historySearch]);

  const exportCSV = () => {
    const headers = ['rank', 'model', 'composite_score', ...sourceNames, 'sources_available'];
    const rows = sortedModels.map((m, i) => {
      const sourceScores = sourceNames.map(sName => {
        const sourceModels = data.sources[sName]?.models || [];
        const match = sourceModels.find(sm =>
          sm.normalized_model === m.model || sm.model === m.model
        );
        return match ? (match.norm_combined?.toFixed(1) ?? '') : '';
      });
      return [i + 1, m.model, m.composite_score?.toFixed(2) ?? '', ...sourceScores, m.sources_available];
    });
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `aibenchmark-data-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const categoryScore = (modelName, cats) => {
    if (!data) return null;
    const vals = (data.source_list || [])
      .filter(s => cats.includes(s.category))
      .map(s => getSourceScore(modelName, s.name))
      .filter(v => v !== null);
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  };

  const getModelPrice = (modelName) => {
    if (!prices) return null;
    const direct = prices[modelName];
    if (direct) return direct.blended ?? null;
    const lower = modelName.toLowerCase();
    const match = Object.entries(prices).find(([k]) => k.toLowerCase() === lower);
    return match ? (match[1].blended ?? null) : null;
  };

  const radarData = useMemo(() => {
    const categories = [
      { label: 'Reasoning', cats: ['reasoning_knowledge'] },
      { label: 'Coding', cats: ['coding'] },
      { label: 'Human Pref', cats: ['human_preference'] },
      { label: 'Agentic', cats: ['agentic', 'tool_use', 'agentic_tool_use'] },
    ];
    const rows = categories.map(cat => {
      const entry = { subject: cat.label };
      selectedModels.forEach(m => { entry[m] = categoryScore(m, cat.cats) ?? 0; });
      return entry;
    });
    if (showPrice) {
      const priceVals = selectedModels.map(m => getModelPrice(m)).filter(p => p != null);
      const minP = Math.min(...priceVals);
      const maxP = Math.max(...priceVals);
      const entry = { subject: 'Cost Efficiency' };
      selectedModels.forEach(m => {
        const p = getModelPrice(m);
        entry[m] = p == null ? 0 : (maxP === minP ? 50 : (maxP - p) / (maxP - minP) * 100);
      });
      rows.push(entry);
    }
    return rows;
  }, [selectedModels, data, showPrice, prices]);

  const modelColors = ['#4f46e5', '#f59e0b', '#22c55e', '#ef4444'];

  const historyHasEnoughData = useMemo(() => {
    if (!historyData) return false;
    return Object.values(historyData).some(arr => arr.length >= 2);
  }, [historyData]);

  const historySourceKeys = useMemo(() => {
    if (!historyData) return [];
    return [...Object.keys(historyData), ...COMPOSITE_SERIES.map(cs => cs.key)];
  }, [historyData]);

  const historyColorMap = useMemo(() => {
    const map = {};
    if (!historyData) return map;
    Object.keys(historyData).forEach((src, i) => { map[src] = SOURCE_COLORS[i % SOURCE_COLORS.length]; });
    COMPOSITE_SERIES.forEach((cs, i) => { map[cs.key] = COMPOSITE_COLORS[i]; });
    return map;
  }, [historyData]);

  const getHistoryLabel = key => {
    const cs = COMPOSITE_SERIES.find(c => c.key === key);
    return cs ? cs.label : abbrev(key);
  };

  const historyChartData = useMemo(() => {
    if (!historyData) return [];
    const sourceList = data?.source_list || [];
    const allTs = new Set();
    Object.values(historyData).forEach(arr => arr.forEach(p => allTs.add(p.snapshot_timestamp)));
    return [...allTs].sort().map(ts => {
      const entry = { ts };
      // Real sources
      Object.entries(historyData).forEach(([src, arr]) => {
        const pt = arr.find(p => p.snapshot_timestamp === ts);
        const useRaw = selectedHistorySrc === src && historyScoreMode === 'raw';
        entry[src] = useRaw ? (pt?.score ?? null) : (pt?.norm_combined ?? null);
      });
      // Composite series (always normalized averages)
      COMPOSITE_SERIES.forEach(cs => {
        const srcKeys = cs.cats === null
          ? Object.keys(historyData)
          : sourceList.filter(s => cs.cats.includes(s.category)).map(s => s.name).filter(n => historyData[n]);
        const vals = srcKeys
          .map(k => historyData[k]?.find(p => p.snapshot_timestamp === ts)?.norm_combined ?? null)
          .filter(v => v !== null);
        entry[cs.key] = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
      });
      return entry;
    });
  }, [historyData, data, selectedHistorySrc, historyScoreMode]);

  const thBtn = (col, label) => {
    const active = sortCol === col;
    return (
      <th key={col} style={{ padding: '10px 12px', background: '#f8f9fa', whiteSpace: 'nowrap' }}>
        <button
          onClick={() => handleSort(col)}
          style={{
            border: 'none', background: 'none', cursor: 'pointer',
            fontWeight: 700, fontSize: 12, color: active ? '#4f46e5' : '#52525b',
            fontFamily: 'inherit', padding: 0, whiteSpace: 'nowrap',
          }}
        >
          {label}{active ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
        </button>
      </th>
    );
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', fontFamily: 'sans-serif', color: '#4f46e5' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>📊</div>
          <div style={{ fontSize: 18, fontWeight: 600 }}>Loading data explorer...</div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', color: '#ef4444', fontFamily: 'sans-serif' }}>
        Failed to load data.
      </div>
    );
  }

  return (
    <div
      style={{ fontFamily: "'Inter', system-ui, sans-serif", background: '#f7f6ff', minHeight: '100vh', color: '#18181b' }}
      onClick={() => setHistoryDropdownOpen(false)}
    >

      {/* Topbar */}
      <div style={{ background: '#4f46e5', color: 'white', height: 52, position: 'sticky', top: 0, zIndex: 100 }}>
        <div style={{ maxWidth: MAX_WIDTH, margin: '0 auto', padding: '0 24px', height: '100%', display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={() => navigate('/')} style={{ background: 'transparent', border: 'none', color: 'white', fontSize: 20, cursor: 'pointer', padding: 0 }}>←</button>
          <span style={{ fontWeight: 800, fontSize: 18, letterSpacing: '-0.5px' }}>TUFF AI</span>
          <span style={{ background: 'rgba(255,255,255,0.15)', borderRadius: 20, padding: '2px 10px', fontSize: 11, fontWeight: 600, letterSpacing: '0.5px' }}>BENCHMARK</span>
          <span style={{ opacity: 0.7, fontSize: 13, marginLeft: 4 }}>/ Data Explorer</span>
        </div>
      </div>

      <div style={{ maxWidth: MAX_WIDTH, margin: '0 auto', padding: '24px' }}>

        {/* Page title + controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
          <h1 style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-0.5px', margin: 0 }}>Data Explorer</h1>
          <span style={{ fontSize: 13, color: '#71717a' }}>{sourceNames.length} sources</span>
          <button
            onClick={() => setShowPrice(p => !p)}
            style={{
              borderRadius: 10, border: `1px solid ${showPrice ? '#10b981' : '#e5e7eb'}`,
              background: showPrice ? '#10b981' : 'white',
              color: showPrice ? 'white' : '#71717a',
              padding: '8px 16px', fontSize: 13, fontWeight: 600, cursor: 'pointer',
            }}
          >
            {showPrice ? '$ Price On' : '$ Price'}
          </button>
          <button
            onClick={exportCSV}
            style={{ marginLeft: 'auto', borderRadius: 10, border: '1px solid #4f46e5', background: '#4f46e5', color: 'white', padding: '8px 16px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
          >
            Export CSV
          </button>
        </div>

        {/* Main table */}
        <div style={{ background: 'white', border: '1px solid #e5e7fb', borderRadius: 10, padding: '20px 20px 0', marginBottom: 24 }}>

          {/* Search bar above table */}
          <input
            type="text"
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(0); }}
            placeholder="Search models..."
            style={{ width: '100%', maxWidth: 400, padding: '10px 14px', borderRadius: 8, border: '1px solid #d4d4d8', fontSize: 14, outline: 'none', marginBottom: 10, boxSizing: 'border-box' }}
          />
          <div style={{ fontSize: 12, color: '#71717a', marginBottom: 12 }}>
            Showing {filteredCount} of {totalCount} models
            {selectedModels.length > 0 && (
              <span style={{ marginLeft: 12, color: '#4f46e5', fontWeight: 600 }}>
                {selectedModels.length} selected for comparison
                <button onClick={() => setSelectedModels([])} style={{ marginLeft: 8, background: 'none', border: 'none', color: '#71717a', cursor: 'pointer', fontSize: 12 }}>✕ clear</button>
              </span>
            )}
          </div>

          <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid #e5e7fb' }}>
            <table style={{ width: '100%', minWidth: 900, borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  {thBtn('rank', 'Rank')}
                  {thBtn('model', 'Model')}
                  {thBtn('composite_score', 'Composite')}
                  {sourceNames.map(sn => thBtn(sn, abbrev(sn)))}
                  {thBtn('sources_available', 'Sources')}
                  {showPrice && (
                    <th style={{ padding: '10px 12px', background: '#f0fdf4', whiteSpace: 'nowrap' }}>
                      <span style={{ fontWeight: 700, fontSize: 12, color: '#10b981' }}>$/1M</span>
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {pageRows.map((m, i) => {
                  const globalRank = page * PAGE_SIZE + i + 1;
                  const isSelected = selectedModels.includes(m.model);
                  return (
                    <tr
                      key={m.model}
                      style={{
                        background: isSelected ? '#eeedfe' : (i % 2 === 0 ? 'white' : '#fafaf9'),
                        borderBottom: '1px solid #f4f4f5',
                        cursor: 'pointer',
                      }}
                      onClick={() => toggleModel(m.model)}
                    >
                      <td style={{ padding: '8px 12px', color: '#71717a', fontWeight: 600, whiteSpace: 'nowrap' }}>{globalRank}</td>
                      <td style={{ padding: '8px 12px', maxWidth: 220 }}>
                        <span
                          onClick={e => { e.stopPropagation(); navigate(`/model/${encodeURIComponent(m.model)}`); }}
                          style={{ color: '#4f46e5', fontWeight: 600, cursor: 'pointer' }}
                          onMouseEnter={e => e.currentTarget.style.textDecoration = 'underline'}
                          onMouseLeave={e => e.currentTarget.style.textDecoration = 'none'}
                        >
                          {m.model}
                        </span>
                      </td>
                      <td style={{ padding: '8px 12px', fontWeight: 700, whiteSpace: 'nowrap' }}>
                        {m.composite_score != null ? m.composite_score.toFixed(2) : <span style={{ color: '#d4d4d8' }}>—</span>}
                      </td>
                      {sourceNames.map(sn => {
                        const score = getSourceScore(m.model, sn);
                        const isTop3 = score !== null && top3PerSource[sn]?.has(score);
                        return (
                          <td
                            key={sn}
                            style={{
                              padding: '8px 12px',
                              whiteSpace: 'nowrap',
                              background: isTop3 ? '#dcfce7' : 'transparent',
                              color: score !== null ? '#18181b' : '#d4d4d8',
                            }}
                          >
                            {score != null ? score.toFixed(1) : '—'}
                          </td>
                        );
                      })}
                      <td style={{ padding: '8px 12px', color: '#71717a', whiteSpace: 'nowrap' }}>
                        {m.sources_available}/{sourceNames.length}
                      </td>
                      {showPrice && (() => {
                        const p = getModelPrice(m.model);
                        return (
                          <td style={{ padding: '8px 12px', whiteSpace: 'nowrap', background: '#f0fdf4', color: p != null ? '#059669' : '#d4d4d8', fontWeight: 600 }}>
                            {p != null ? `$${p < 1 ? p.toFixed(3) : p.toFixed(2)}` : '—'}
                          </td>
                        );
                      })()}
                    </tr>
                  );
                })}
                {pageRows.length === 0 && (
                  <tr>
                    <td colSpan={3 + sourceNames.length + 1} style={{ textAlign: 'center', padding: 32, color: '#a1a1aa' }}>
                      No models match your search.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 0 16px' }}>
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                style={{ border: '1px solid #e5e7fb', borderRadius: 8, padding: '6px 16px', fontSize: 12, fontWeight: 600, color: '#71717a', background: 'white', cursor: page === 0 ? 'not-allowed' : 'pointer', opacity: page === 0 ? 0.5 : 1 }}
              >
                Previous
              </button>
              <span style={{ fontSize: 13, color: '#71717a' }}>Page {page + 1} of {totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                style={{ border: '1px solid #e5e7fb', borderRadius: 8, padding: '6px 16px', fontSize: 12, fontWeight: 600, color: '#71717a', background: 'white', cursor: page >= totalPages - 1 ? 'not-allowed' : 'pointer', opacity: page >= totalPages - 1 ? 0.5 : 1 }}
              >
                Next
              </button>
            </div>
          )}
        </div>

        {/* Comparison panel */}
        {selectedModels.length >= 2 && (
          <div style={{ background: 'white', border: '1px solid #e5e7fb', borderRadius: 10, padding: 24, marginBottom: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h2 style={{ fontSize: 15, fontWeight: 800, margin: 0 }}>Model Comparison</h2>
              <button
                onClick={() => setSelectedModels([])}
                style={{ border: '1px solid #e5e7fb', borderRadius: 8, padding: '5px 14px', fontSize: 12, fontWeight: 600, color: '#71717a', background: 'white', cursor: 'pointer' }}
              >
                Clear selection
              </button>
            </div>

            {/* Side-by-side grid */}
            <div style={{ overflowX: 'auto', marginBottom: 24 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr>
                    <th style={{ padding: '8px 12px', background: '#f8f9fa', textAlign: 'left', fontWeight: 700, color: '#52525b' }}>Source</th>
                    {selectedModels.map((m, mi) => (
                      <th key={m} style={{ padding: '8px 12px', background: '#f8f9fa', textAlign: 'center', fontWeight: 700, color: modelColors[mi] }}>
                        {m}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sourceNames.map((sn, i) => {
                    const scores = selectedModels.map(m => getSourceScore(m, sn));
                    const validScores = scores.filter(s => s !== null);
                    const maxScore = validScores.length ? Math.max(...validScores) : null;
                    return (
                      <tr key={sn} style={{ borderBottom: '1px solid #f4f4f5', background: i % 2 === 0 ? 'white' : '#fafaf9' }}>
                        <td style={{ padding: '8px 12px', color: '#52525b', fontWeight: 500 }}>{abbrev(sn)}</td>
                        {scores.map((score, mi) => (
                          <td
                            key={mi}
                            style={{
                              padding: '8px 12px',
                              textAlign: 'center',
                              fontWeight: 600,
                              background: score !== null && score === maxScore ? '#dcfce7' : 'transparent',
                            }}
                          >
                            {score !== null ? score.toFixed(1) : <span style={{ color: '#d4d4d8' }}>—</span>}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                  {/* Category composites */}
                  <tr>
                    <td
                      colSpan={1 + selectedModels.length}
                      style={{ padding: '6px 12px', fontSize: 11, fontWeight: 700, color: '#71717a', background: '#f8f9fa', letterSpacing: '0.5px', textTransform: 'uppercase' }}
                    >
                      Composites
                    </td>
                  </tr>
                  {CATEGORY_ROWS.map((cat, i) => {
                    const scores = selectedModels.map(m => {
                      if (!cat.cats) {
                        return (data.composites || []).find(c => c.model === m)?.composite_score ?? null;
                      }
                      return categoryScore(m, cat.cats);
                    });
                    const validScores = scores.filter(s => s !== null);
                    const maxScore = validScores.length ? Math.max(...validScores) : null;
                    return (
                      <tr key={cat.label} style={{ borderBottom: '1px solid #f4f4f5', background: i % 2 === 0 ? '#f7f6ff' : '#f0efff' }}>
                        <td style={{ padding: '8px 12px', color: '#4f46e5', fontWeight: 700 }}>{cat.label}</td>
                        {scores.map((score, mi) => (
                          <td
                            key={mi}
                            style={{
                              padding: '8px 12px',
                              textAlign: 'center',
                              fontWeight: 700,
                              color: '#4f46e5',
                              background: score !== null && score === maxScore ? '#e0e7ff' : 'transparent',
                            }}
                          >
                            {score !== null ? score.toFixed(1) : <span style={{ color: '#d4d4d8' }}>—</span>}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                  {/* Price row — always visible in comparison */}
                  <tr>
                    <td
                      colSpan={1 + selectedModels.length}
                      style={{ padding: '6px 12px', fontSize: 11, fontWeight: 700, color: '#71717a', background: '#f0fdf4', letterSpacing: '0.5px', textTransform: 'uppercase' }}
                    >
                      Pricing
                    </td>
                  </tr>
                  {[
                    { label: 'Blended $/1M', key: 'blended' },
                    { label: 'Input $/1M', key: 'input' },
                    { label: 'Output $/1M', key: 'output' },
                  ].map((row, i) => {
                    const priceVals = selectedModels.map(m => {
                      const entry = prices[m] ?? Object.entries(prices).find(([k]) => k.toLowerCase() === m.toLowerCase())?.[1];
                      return entry?.[row.key] ?? null;
                    });
                    const validVals = priceVals.filter(v => v != null);
                    const minVal = validVals.length ? Math.min(...validVals) : null;
                    return (
                      <tr key={row.label} style={{ borderBottom: '1px solid #f4f4f5', background: i % 2 === 0 ? '#f7fef9' : '#f0fdf4' }}>
                        <td style={{ padding: '8px 12px', color: '#059669', fontWeight: 600 }}>{row.label}</td>
                        {priceVals.map((val, mi) => (
                          <td
                            key={mi}
                            style={{
                              padding: '8px 12px',
                              textAlign: 'center',
                              fontWeight: 700,
                              color: '#059669',
                              background: val != null && val === minVal ? '#d1fae5' : 'transparent',
                            }}
                          >
                            {val != null ? `$${val < 1 ? val.toFixed(3) : val.toFixed(2)}` : <span style={{ color: '#d4d4d8' }}>—</span>}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Radar chart */}
            <div style={{ height: 280 }}>
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={radarData}>
                  <PolarGrid />
                  <PolarAngleAxis dataKey="subject" tick={{ fontSize: 12 }} />
                  <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 10 }} />
                  {selectedModels.map((m, mi) => (
                    <Radar key={m} name={m} dataKey={m} stroke={modelColors[mi]} fill={modelColors[mi]} fillOpacity={0.15} />
                  ))}
                  <Legend />
                  <Tooltip />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            {/* Comparison history */}
            {Object.keys(comparisonHistories).length > 0 && (
              <div style={{ marginTop: 24, borderTop: '1px solid #f4f4f5', paddingTop: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                  <h3 style={{ margin: 0, fontSize: 14, fontWeight: 800 }}>Score History</h3>
                  <div style={{ display: 'flex', background: '#f4f4f5', borderRadius: 20, padding: 3, gap: 2 }}>
                    {['Separate', 'Overlay'].map(mode => (
                      <button
                        key={mode}
                        onClick={() => setHistoryOverlay(mode === 'Overlay')}
                        style={{
                          padding: '3px 14px', borderRadius: 16, fontSize: 12, fontWeight: 600,
                          cursor: 'pointer', border: 'none',
                          background: (mode === 'Overlay') === historyOverlay ? '#4f46e5' : 'transparent',
                          color: (mode === 'Overlay') === historyOverlay ? 'white' : '#71717a',
                        }}
                      >
                        {mode}
                      </button>
                    ))}
                  </div>
                </div>

                {!historyOverlay ? (
                  /* Separate charts */
                  <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(selectedModels.length, 2)}, 1fr)`, gap: 20 }}>
                    {selectedModels.map((modelName, mi) => {
                      const mChartData = compHistoryByModel[modelName];
                      if (!mChartData || mChartData.length < 2) return (
                        <div key={modelName} style={{ padding: 20, background: '#f8f9fa', borderRadius: 8, textAlign: 'center' }}>
                          <div style={{ fontWeight: 700, color: modelColors[mi], fontSize: 12, marginBottom: 6 }}>{modelName}</div>
                          <span style={{ color: '#a1a1aa', fontSize: 12 }}>Not enough history yet</span>
                        </div>
                      );
                      return (
                        <div key={modelName}>
                          <div style={{ fontWeight: 700, color: modelColors[mi], fontSize: 12, marginBottom: 6 }}>{modelName}</div>
                          {/* Per-model legend */}
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 6 }}>
                            {COMPOSITE_SERIES.map((cs, ci) => (
                              <span key={cs.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#52525b' }}>
                                <span style={{ width: 16, height: 2, background: COMPOSITE_COLORS[ci], display: 'inline-block', borderRadius: 1 }} />
                                {cs.label}
                              </span>
                            ))}
                          </div>
                          <div style={{ height: 200 }}>
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={mChartData}>
                                <XAxis dataKey="ts" tickFormatter={formatTimestamp} tick={{ fontSize: 9 }} />
                                <YAxis domain={[0, 100]} tick={{ fontSize: 9 }} width={28} />
                                <Tooltip formatter={(v) => v != null ? v.toFixed(1) : '—'} labelFormatter={formatTimestamp} />
                                {COMPOSITE_SERIES.map((cs, ci) => (
                                  <Line
                                    key={cs.key}
                                    type="monotone"
                                    dataKey={cs.key}
                                    name={cs.label}
                                    stroke={COMPOSITE_COLORS[ci]}
                                    strokeDasharray={ci > 0 ? '5 3' : undefined}
                                    strokeWidth={ci === 0 ? 2 : 1.5}
                                    dot={false}
                                    connectNulls
                                  />
                                ))}
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  /* Overlay chart */
                  <>
                    {/* Grouped legend: one section per model */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, marginBottom: 12 }}>
                      {selectedModels.map((modelName, mi) => {
                        const dashPatterns = [null, '6 3', '2 2', '8 2 2 2'];
                        return (
                          <div key={modelName}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
                              <svg width="22" height="10" style={{ flexShrink: 0 }}>
                                <line x1="0" y1="5" x2="22" y2="5" stroke={modelColors[mi]} strokeWidth="2.5" strokeDasharray={dashPatterns[mi] || ''} />
                              </svg>
                              <span style={{ fontSize: 12, fontWeight: 700, color: modelColors[mi] }}>{modelName}</span>
                            </div>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                              {COMPOSITE_SERIES.map((cs, ci) => (
                                <span key={cs.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#52525b' }}>
                                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: COMPOSITE_COLORS[ci], display: 'inline-block' }} />
                                  {cs.label}
                                </span>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    <div style={{ height: 280 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={compHistoryOverlay}>
                          <XAxis dataKey="ts" tickFormatter={formatTimestamp} tick={{ fontSize: 10 }} />
                          <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                          <Tooltip formatter={(v) => v != null ? v.toFixed(1) : '—'} labelFormatter={formatTimestamp} />
                          {selectedModels.flatMap((modelName, mi) => {
                            const dashPatterns = [null, '6 3', '2 2', '8 2 2 2'];
                            return COMPOSITE_SERIES.map((cs, ci) => (
                              <Line
                                key={`${mi}___${cs.key}`}
                                type="monotone"
                                dataKey={`${mi}___${cs.key}`}
                                name={`${modelName} — ${cs.label}`}
                                stroke={COMPOSITE_COLORS[ci]}
                                strokeDasharray={dashPatterns[mi]}
                                strokeWidth={ci === 0 ? 2 : 1.5}
                                dot={false}
                                connectNulls
                              />
                            ));
                          })}
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        )}

        {/* History section */}
        <div style={{ background: 'white', border: '1px solid #e5e7fb', borderRadius: 10, padding: 24, marginBottom: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 800, marginBottom: 14, marginTop: 0 }}>Score History</h2>

          {/* Autocomplete input */}
          <div
            style={{ position: 'relative', maxWidth: 400, marginBottom: 20 }}
            onClick={e => e.stopPropagation()}
          >
            <input
              type="text"
              value={historySearch}
              onChange={e => {
                setHistorySearch(e.target.value);
                setHistoryDropdownOpen(true);
                setHistoryModel(null);
                setHistoryData(null);
              }}
              onFocus={() => { if (historySearch.trim()) setHistoryDropdownOpen(true); }}
              placeholder="Search for a model..."
              style={{ width: '100%', padding: '10px 14px', borderRadius: 8, border: '1px solid #d4d4d8', fontSize: 14, outline: 'none', boxSizing: 'border-box' }}
            />
            {historyDropdownOpen && historyModelOptions.length > 0 && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, right: 0,
                background: 'white', border: '1px solid #e5e7fb', borderRadius: 8,
                boxShadow: '0 4px 16px rgba(0,0,0,0.08)', zIndex: 50,
                maxHeight: 300, overflowY: 'auto',
              }}>
                {historyModelOptions.map(m => (
                  <div
                    key={m.model}
                    onClick={() => {
                      setHistoryModel(m.model);
                      setHistorySearch(m.model);
                      setHistoryDropdownOpen(false);
                      fetchHistory(m.model);
                    }}
                    style={{ padding: '10px 14px', cursor: 'pointer', fontSize: 13, borderBottom: '1px solid #f4f4f5', color: '#18181b' }}
                    onMouseEnter={e => e.currentTarget.style.background = '#f7f6ff'}
                    onMouseLeave={e => e.currentTarget.style.background = 'white'}
                  >
                    {m.model}
                    <span style={{ marginLeft: 8, fontSize: 11, color: '#a1a1aa' }}>
                      {m.composite_score?.toFixed(1)} · {m.sources_available} sources
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {historyLoading && <div style={{ color: '#71717a', fontSize: 13 }}>Loading history...</div>}

          {!historyLoading && historyModel && !historyHasEnoughData && (
            <div style={{ color: '#71717a', fontSize: 13 }}>Not enough history yet — check back after a few days.</div>
          )}

          {!historyLoading && historyHasEnoughData && (
            <>
              {/* Clickable legend — real sources */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 6 }}>
                {Object.keys(historyData).map(src => {
                  const color = historyColorMap[src];
                  const isSelected = selectedHistorySrc === src;
                  const dimmed = selectedHistorySrc && !isSelected;
                  return (
                    <button
                      key={src}
                      onClick={() => setSelectedHistorySrc(prev => prev === src ? null : src)}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 5,
                        padding: '3px 10px', borderRadius: 20, cursor: 'pointer',
                        border: `1.5px solid ${isSelected ? color : '#e5e7eb'}`,
                        background: isSelected ? `${color}18` : 'white',
                        color: dimmed ? '#a1a1aa' : '#18181b',
                        fontSize: 12, fontWeight: 600,
                        opacity: dimmed ? 0.45 : 1,
                        transition: 'all 0.15s',
                      }}
                    >
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
                      {abbrev(src)}
                    </button>
                  );
                })}
              </div>

              {/* Composite series legend row */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
                {COMPOSITE_SERIES.map(cs => {
                  const color = historyColorMap[cs.key];
                  const isSelected = selectedHistorySrc === cs.key;
                  const dimmed = selectedHistorySrc && !isSelected;
                  return (
                    <button
                      key={cs.key}
                      onClick={() => setSelectedHistorySrc(prev => prev === cs.key ? null : cs.key)}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 5,
                        padding: '3px 10px', borderRadius: 20, cursor: 'pointer',
                        border: `1.5px dashed ${isSelected ? color : '#c4c4c4'}`,
                        background: isSelected ? `${color}18` : '#fafafa',
                        color: dimmed ? '#a1a1aa' : '#18181b',
                        fontSize: 12, fontWeight: 600,
                        opacity: dimmed ? 0.45 : 1,
                        transition: 'all 0.15s',
                      }}
                    >
                      <span style={{ width: 18, height: 2, background: color, flexShrink: 0, borderRadius: 1 }} />
                      {cs.label}
                    </button>
                  );
                })}
              </div>

              {/* Raw / Normalized toggle — only for real (non-composite) sources */}
              {selectedHistorySrc && !selectedHistorySrc.startsWith('__') && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                  <span style={{ fontSize: 11, color: '#71717a', fontWeight: 500 }}>Score:</span>
                  {['composite', 'raw'].map(mode => (
                    <button
                      key={mode}
                      onClick={() => setHistoryScoreMode(mode)}
                      style={{
                        padding: '2px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600, cursor: 'pointer',
                        border: `1.5px solid ${historyScoreMode === mode ? '#4f46e5' : '#e5e7eb'}`,
                        background: historyScoreMode === mode ? '#4f46e5' : 'white',
                        color: historyScoreMode === mode ? 'white' : '#71717a',
                      }}
                    >
                      {mode === 'composite' ? 'Normalized' : 'Raw'}
                    </button>
                  ))}
                </div>
              )}

              <div style={{ height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={historyChartData}>
                    <XAxis dataKey="ts" tickFormatter={formatTimestamp} tick={{ fontSize: 11 }} />
                    <YAxis
                      domain={selectedHistorySrc && !selectedHistorySrc.startsWith('__') && historyScoreMode === 'raw' ? ['auto', 'auto'] : [0, 100]}
                      tick={{ fontSize: 11 }}
                    />
                    <Tooltip formatter={(v) => v != null ? v.toFixed(2) : '—'} labelFormatter={formatTimestamp} />
                    {historySourceKeys
                      .filter(src => !selectedHistorySrc || src === selectedHistorySrc)
                      .map(src => {
                        const isComposite = src.startsWith('__');
                        const label = getHistoryLabel(src);
                        return (
                          <Line
                            key={src}
                            type="monotone"
                            dataKey={src}
                            name={isComposite ? label : (selectedHistorySrc && historyScoreMode === 'raw' ? `${label} (raw)` : label)}
                            stroke={historyColorMap[src]}
                            strokeDasharray={isComposite ? '5 4' : undefined}
                            strokeWidth={isComposite ? 1.5 : 2}
                            dot={false}
                            connectNulls
                          />
                        );
                      })
                    }
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </div>

        {/* Freshness panel */}
        <div style={{ background: 'white', border: '1px solid #e5e7fb', borderRadius: 10, padding: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 800, marginBottom: 14, marginTop: 0 }}>Source Freshness</h2>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  {['Source', 'Category', 'Last Updated', 'Models', 'Status'].map(h => (
                    <th key={h} style={{ padding: '8px 12px', background: '#f8f9fa', textAlign: 'left', fontWeight: 700, color: '#52525b' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(data.source_list || []).map((src, i) => {
                  const info = data.sources[src.name];
                  return (
                    <tr key={src.name} style={{ borderBottom: '1px solid #f4f4f5', background: i % 2 === 0 ? 'white' : '#fafaf9' }}>
                      <td style={{ padding: '8px 12px', fontWeight: 500 }}>{src.name}</td>
                      <td style={{ padding: '8px 12px', color: '#52525b' }}>{src.category || '—'}</td>
                      <td style={{ padding: '8px 12px', color: '#71717a' }}>{info ? relativeTime(info.last_updated) : 'No data'}</td>
                      <td style={{ padding: '8px 12px' }}>{info ? info.model_count : '—'}</td>
                      <td style={{ padding: '8px 12px' }}>{info ? freshnessStatus(info.last_updated) : '🔴'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  );
}

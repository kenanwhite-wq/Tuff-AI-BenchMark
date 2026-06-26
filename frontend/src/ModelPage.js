import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import './App.css';
import ModelComments from './components/ModelComments';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:5001/api';

const API = axios.create({ baseURL: API_BASE_URL, timeout: 5000 });

export default function ModelPage() {
  const { modelName } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!modelName) return;
    setLoading(true);
    API.get(`/model/${encodeURIComponent(modelName)}`)
      .then(res => {
        setData(res.data);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error fetching model:', err);
        setData(null);
        setLoading(false);
      });
  }, [modelName]);

  if (loading) return (
    <div style={{padding:24}}>Loading model...</div>
  );

  if (!data) return (
    <div style={{padding:24}}>Model not found.</div>
  );

  const history = (data.history || []).map(h => ({
    timestamp: (new Date(h.timestamp)).toLocaleString(),
    composite_score: h.composite_score
  })).reverse();

  const formatScore = (value) => {
    if (value == null || value === '—') return '—';
    const num = Number(value);
    return Number.isFinite(num) ? num.toFixed(1) : value;
  };

  return (
    <div style={{ fontFamily: "'Inter', system-ui, sans-serif", background: '#f7f6ff', minHeight: '100vh', color: '#18181b' }}>
      <div style={{ background: '#4f46e5', color: 'white', padding: '12px 24px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => navigate('/')} style={{ background: 'transparent', border: 'none', color: 'white', fontSize: 20, cursor: 'pointer' }}>←</button>
        <div style={{ fontWeight: 800, fontSize: 18 }}>{decodeURIComponent(modelName)}</div>
        <div style={{ marginLeft: 'auto', opacity: 0.9 }}>Last updated: {data.last_updated || 'N/A'}</div>
      </div>

      <div style={{ maxWidth: 1100, margin: '18px auto', padding: '0 24px' }}>
        <div style={{ background: 'white', padding: 20, borderRadius: 12, display: 'grid', gridTemplateColumns: '1fr 320px', gap: 18 }}>
          <div>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <div style={{ background: '#eef2ff', borderRadius: 12, padding: 12, minWidth: 88, textAlign: 'center' }}>
                <div style={{ color: '#6b21a8', fontWeight: 700 }}>Composite score</div>
                <div style={{ fontSize: 36, fontWeight: 800, color: '#2b2b2b' }}>{data.composite_score != null ? Number(data.composite_score).toFixed(1) : '—'}</div>
                <div style={{ color: '#6b7280', fontSize: 12 }}>#{data.rank || '—'}</div>
              </div>

              <div style={{ display: 'flex', gap: 10, alignItems: 'stretch' }}>
                <div style={{ background: '#fafafa', borderRadius: 8, padding: 12, width: 140 }}>
                  <div style={{ fontSize: 12, color: '#71717a' }}>Human preference</div>
                  <div style={{ fontSize: 20, fontWeight: 800, marginTop: 6 }}>{formatScore(data.category_scores?.human_preference ?? '—')}</div>
                </div>
                <div style={{ background: '#fafafa', borderRadius: 8, padding: 12, width: 140 }}>
                  <div style={{ fontSize: 12, color: '#71717a' }}>Reasoning</div>
                  <div style={{ fontSize: 20, fontWeight: 800, marginTop: 6 }}>{formatScore(data.category_scores?.reasoning ?? '—')}</div>
                </div>
                <div style={{ background: '#fafafa', borderRadius: 8, padding: 12, width: 140 }}>
                  <div style={{ fontSize: 12, color: '#71717a' }}>Coding</div>
                  <div style={{ fontSize: 20, fontWeight: 800, marginTop: 6 }}>{formatScore(data.category_scores?.coding ?? '—')}</div>
                </div>
              </div>
            </div>

            <div style={{ marginTop: 18, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div style={{ background: '#eef2ff', borderRadius: 12, padding: 16 }}>
                <div style={{ fontSize: 12, color: '#4338ca' }}>Community Elo</div>
                <div style={{ fontSize: 34, fontWeight: 800, marginTop: 8, color: '#312e81' }}>
                  {data.community_elo != null ? Number(data.community_elo).toFixed(0) : 'No Elo yet'}
                </div>
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
                  {data.votes_total > 0 ? `${data.votes_total} community votes` : 'No votes yet'}
                </div>
              </div>
              <div style={{ background: '#fafafa', borderRadius: 12, padding: 16 }}>
                <div style={{ fontSize: 12, color: '#71717a' }}>Win / Loss</div>
                <div style={{ fontSize: 20, fontWeight: 700, marginTop: 8 }}>{data.votes_won ?? 0} / {data.votes_lost ?? 0}</div>
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>Recorded from pairwise voting</div>
              </div>
            </div>

            <div style={{ marginTop: 18 }}>
              <h3 style={{ fontSize: 14, fontWeight: 800, color: '#52525b' }}>Comments</h3>
              <div style={{ background: 'white', borderRadius: 10, border: '1px solid #eef2ff', padding: 12 }}>
                <ModelComments model={data.model} autoExpand={true} />
              </div>
            </div>

            <div style={{ marginTop: 18 }}>
              <h3 style={{ fontSize: 14, fontWeight: 800, color: '#52525b' }}>Scores by source</h3>
              <div style={{ marginTop: 8, background: '#fff', borderRadius: 10, border: '1px solid #eef2ff', padding: 12 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ textAlign: 'left', color: '#9ca3af' }}>
                      <th style={{ padding: 8 }}>Source</th>
                      <th style={{ padding: 8 }}>Raw score</th>
                      <th style={{ padding: 8 }}>Rank</th>
                      <th style={{ padding: 8 }}>Normalized</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.source_scores || []).map(s => (
                      <tr key={s.source_name} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: 8 }}>{s.source_name}</td>
                        <td style={{ padding: 8 }}>{s.raw_score != null ? (typeof s.raw_score === 'number' ? s.raw_score.toFixed(1) : s.raw_score) : '—'}</td>
                        <td style={{ padding: 8 }}>{s.rank || '—'} / {s.total_in_source || '—'}</td>
                        <td style={{ padding: 8 }}>{s.normalized_score != null ? Number(s.normalized_score).toFixed(1) : (s.has_data ? '—' : 'N/A')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div style={{ marginTop: 18 }}>
              <h3 style={{ fontSize: 14, fontWeight: 800, color: '#52525b' }}>Score history</h3>
              <div style={{ background: 'white', borderRadius: 10, padding: 12, border: '1px solid #eef2ff' }}>
                <div style={{ width: '100%', height: 180 }}>
                  <ResponsiveContainer>
                    <LineChart data={history}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="timestamp" hide />
                      <YAxis domain={[0, 100]} />
                      <Tooltip />
                      <Line type="monotone" dataKey="composite_score" stroke="#4f46e5" strokeWidth={2} dot={{ r: 2 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            <div style={{ marginTop: 18 }}>
              <h3 style={{ fontSize: 14, fontWeight: 800, color: '#52525b' }}>Recent activity</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {(data.feed_entries || []).map(f => (
                  <div key={f.id || f.created_at} style={{ background: 'white', padding: 12, borderRadius: 8, border: '1px solid #eef2ff' }}>
                    <div style={{ fontWeight: 700 }}>{f.headline}</div>
                    <div style={{ color: '#6b7280', marginTop: 6 }}>{f.body}</div>
                    <div style={{ marginTop: 8, fontSize: 12, color: '#9ca3af' }}>{f.source} · {f.created_at}</div>
                  </div>
                ))}
              </div>
            </div>

          </div>

          <div>
            <div style={{ background: '#fafafa', borderRadius: 10, padding: 12, border: '1px solid #eef2ff' }}>
              <h4 style={{ fontSize: 13, fontWeight: 800 }}>Quick stats</h4>
              <div style={{ marginTop: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                  <div style={{ color: '#6b7280' }}>Sources</div>
                  <div style={{ fontWeight: 700 }}>{data.sources_available || 0}</div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginTop: 8 }}>
                  <div style={{ color: '#6b7280' }}>Rank</div>
                  <div style={{ fontWeight: 700 }}>#{data.rank || '—'}</div>
                </div>
              </div>
            </div>

            <div style={{ marginTop: 12, background: 'white', borderRadius: 10, padding: 12, border: '1px solid #eef2ff' }}>
              <h4 style={{ fontSize: 13, fontWeight: 800 }}>Category scores</h4>
              <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div style={{ background: '#fff', padding: 8, borderRadius: 8 }}>
                  <div style={{ color: '#6b7280', fontSize: 12 }}>Human pref</div>
                  <div style={{ fontWeight: 800 }}>{formatScore(data.category_scores?.human_preference ?? '—')}</div>
                </div>
                <div style={{ background: '#fff', padding: 8, borderRadius: 8 }}>
                  <div style={{ color: '#6b7280', fontSize: 12 }}>Reasoning</div>
                  <div style={{ fontWeight: 800 }}>{formatScore(data.category_scores?.reasoning ?? '—')}</div>
                </div>
                <div style={{ background: '#fff', padding: 8, borderRadius: 8 }}>
                  <div style={{ color: '#6b7280', fontSize: 12 }}>Coding</div>
                  <div style={{ fontWeight: 800 }}>{formatScore(data.category_scores?.coding ?? '—')}</div>
                </div>
                <div style={{ background: '#fff', padding: 8, borderRadius: 8 }}>
                  <div style={{ color: '#6b7280', fontSize: 12 }}>Agentic</div>
                  <div style={{ fontWeight: 800 }}>{data.category_scores?.agentic ?? '—'}</div>
                </div>
              </div>
            </div>

          </div>
        </div>

        <div style={{ textAlign: 'center', color: '#9ca3af', marginTop: 12 }}>Composite score · Updates hourly</div>

      </div>
    </div>
  );
}

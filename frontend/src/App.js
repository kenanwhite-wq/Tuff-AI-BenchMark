import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';

const API = axios.create({
  baseURL: 'http://localhost:5001/api',
  timeout: 5000,
});

function App() {
  const [models, setModels] = useState([]);
  const [feed, setFeed] = useState([]);
  const [sources, setSources] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [priceToggle, setPriceToggle] = useState(false);

  useEffect(() => {
    Promise.all([
      API.get('/models'),
      API.get('/feed'),
      API.get('/sources'),
      API.get('/stats'),
    ])
      .then(([modelsRes, feedRes, sourcesRes, statsRes]) => {
        setModels(modelsRes.data);
        setFeed(feedRes.data.filter(item => item.status === 'approved'));
        setSources(sourcesRes.data);
        setStats(statsRes.data);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error fetching data:', err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div style={{
        display: 'flex', justifyContent: 'center', alignItems: 'center',
        height: '100vh', fontFamily: 'sans-serif', color: '#4f46e5'
      }}>
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

  const sourceColors = ['#4f46e5', '#f59e0b', '#22c55e'];

  return (
    <div style={{
      fontFamily: "'Inter', system-ui, sans-serif",
      background: '#f7f6ff',
      minHeight: '100vh',
      color: '#18181b',
    }}>
      {/* Top bar */}
      <div style={{
        background: '#4f46e5',
        color: 'white',
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        height: 52,
        position: 'sticky',
        top: 0,
        zIndex: 100,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontWeight: 800, fontSize: 18, letterSpacing: '-0.5px' }}>
            TUFF AI
          </span>
          <span style={{
            background: 'rgba(255,255,255,0.15)',
            borderRadius: 20,
            padding: '2px 10px',
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.5px'
          }}>BENCHMARK</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 13 }}>
          <span style={{ opacity: 0.8 }}>🟢 Live</span>
          <span style={{ opacity: 0.7 }}>
            Updated {stats.last_update ? new Date(stats.last_update).toLocaleTimeString() : 'N/A'}
          </span>
        </div>
      </div>

      {/* Hero section */}
      <div style={{
        background: 'white',
        borderBottom: '1px solid #e5e7fb',
        padding: '20px 24px 0',
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 12,
          marginBottom: 16,
        }}>
          <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.5px' }}>
            Today's Rankings
          </h1>
          <span style={{ fontSize: 13, color: '#71717a' }}>
            {stats.sources || 0} sources · {stats.models || 0} models tracked
          </span>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 12, color: '#71717a' }}>Include cost/speed</span>
            <div
              onClick={() => setPriceToggle(!priceToggle)}
              style={{
                width: 36, height: 20, borderRadius: 10,
                background: priceToggle ? '#4f46e5' : '#d4d4d8',
                cursor: 'pointer', position: 'relative', transition: 'background 0.2s'
              }}
            >
              <div style={{
                position: 'absolute', top: 2,
                left: priceToggle ? 18 : 2,
                width: 16, height: 16, borderRadius: 8,
                background: 'white', transition: 'left 0.2s',
                boxShadow: '0 1px 3px rgba(0,0,0,0.2)'
              }} />
            </div>
          </div>
        </div>

        {/* Model cards */}
        <div style={{
          display: 'flex',
          gap: 10,
          overflowX: 'auto',
          paddingBottom: 16,
          scrollbarWidth: 'none',
        }}>
          {models.map((m, i) => (
            <div key={m.model} style={{
              minWidth: 130,
              background: i === 0 ? '#4f46e5' : '#f7f6ff',
              border: `1px solid ${i === 0 ? '#4f46e5' : '#e5e7fb'}`,
              borderRadius: 10,
              padding: '12px 14px',
              flexShrink: 0,
              transition: 'transform 0.15s',
              cursor: 'default',
            }}
              onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'}
              onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}
            >
              <div style={{
                fontSize: 10, fontWeight: 700, letterSpacing: '1px',
                color: i === 0 ? 'rgba(255,255,255,0.7)' : '#a1a1aa',
                marginBottom: 4
              }}>
                #{m.rank || i + 1}
              </div>
              <div style={{
                fontSize: 12, fontWeight: 700,
                color: i === 0 ? 'white' : '#18181b',
                marginBottom: 6, lineHeight: 1.2
              }}>
                {m.model}
              </div>
              <div style={{
                fontSize: 22, fontWeight: 800,
                color: i === 0 ? 'white' : '#4f46e5',
                lineHeight: 1,
              }}>
                {m.composite_score ? m.composite_score.toFixed(1) : '—'}
              </div>
              <div style={{
                fontSize: 10, marginTop: 4,
                color: i === 0 ? 'rgba(255,255,255,0.6)' : '#a1a1aa'
              }}>
                {m.sources_available || 0}/{sources.length} sources
              </div>
            </div>
          ))}
        </div>

        {/* Weight bar */}
        <div style={{
          display: 'flex', gap: 0, height: 3, marginBottom: 0,
          borderRadius: '2px 2px 0 0', overflow: 'hidden'
        }}>
          {sources.map((s, i) => (
            <div key={s.name} style={{
              flex: s.weight || 33,
              background: sourceColors[i % sourceColors.length],
            }} title={`${s.label}: ${s.weight}%`} />
          ))}
        </div>
        <div style={{
          display: 'flex', gap: 16, padding: '8px 0 0', fontSize: 11, color: '#71717a'
        }}>
          {sources.map((s, i) => (
            <span key={s.name} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{
                width: 8, height: 8, borderRadius: 2, display: 'inline-block',
                background: sourceColors[i % sourceColors.length]
              }} />
              {s.label || s.name} <strong style={{ color: '#3f3f46' }}>{s.weight || '—'}%</strong>
            </span>
          ))}
          <span style={{ marginLeft: 'auto', color: '#a1a1aa' }}>weights · methodology ↗</span>
        </div>
      </div>

      {/* Main content */}
      <div style={{
        maxWidth: 1100, margin: '0 auto', padding: '24px 24px',
        display: 'grid', gridTemplateColumns: '1fr 320px', gap: 24,
      }}>
        {/* Feed */}
        <div>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16
          }}>
            <h2 style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.3px' }}>
              What changed
            </h2>
            <span style={{
              background: '#ef4444', color: 'white',
              fontSize: 10, fontWeight: 700, padding: '2px 8px',
              borderRadius: 4, letterSpacing: '0.5px'
            }}>LIVE</span>
          </div>

          {feed.length === 0 ? (
            <div style={{ background: 'white', padding: 30, borderRadius: 10, textAlign: 'center', color: '#a1a1aa' }}>
              No feed entries yet. Changes will appear here when detected.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {feed.map(item => {
                const tier = tierConfig[item.tier] || tierConfig.moderate;
                return (
                  <div key={item.id} style={{
                    background: 'white',
                    border: `1px solid ${tier.border}`,
                    borderRadius: 10,
                    padding: '16px 18px',
                    display: 'flex',
                    gap: 14,
                    transition: 'box-shadow 0.15s',
                    cursor: 'default',
                  }}
                    onMouseEnter={e => e.currentTarget.style.boxShadow = '0 4px 16px rgba(79,70,229,0.08)'}
                    onMouseLeave={e => e.currentTarget.style.boxShadow = 'none'}
                  >
                    <div style={{
                      minWidth: 56, display: 'flex', flexDirection: 'column',
                      alignItems: 'center', justifyContent: 'flex-start', paddingTop: 2
                    }}>
                      <div style={{
                        background: tier.bg,
                        border: `1.5px solid ${tier.border}`,
                        borderRadius: 6,
                        padding: '4px 6px',
                        textAlign: 'center',
                      }}>
                        <div style={{
                          fontSize: 9, fontWeight: 800, letterSpacing: '1px',
                          color: tier.color, lineHeight: 1
                        }}>
                          {tier.label}
                        </div>
                      </div>
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: 15, fontWeight: 700, lineHeight: 1.3,
                        marginBottom: 6, color: '#18181b'
                      }}>
                        {item.headline}
                      </div>
                      <div style={{
                        fontSize: 13, color: '#52525b', lineHeight: 1.5, marginBottom: 8
                      }}>
                        {item.body}
                      </div>
                      <div style={{
                        display: 'flex', gap: 8, alignItems: 'center', fontSize: 11
                      }}>
                        <span style={{
                          background: '#ede9fe', color: '#5b21b6',
                          padding: '2px 8px', borderRadius: 4, fontWeight: 600
                        }}>
                          {sources.find(s => s.name === item.source)?.label || item.source}
                        </span>
                        <span style={{ color: '#a1a1aa' }}>{item.created_at}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Sources breakdown */}
          <div style={{
            background: 'white', borderRadius: 10,
            border: '1px solid #e5e7fb', padding: '18px 18px'
          }}>
            <h3 style={{ fontSize: 13, fontWeight: 800, marginBottom: 14, letterSpacing: '0.5px', color: '#52525b', textTransform: 'uppercase' }}>
              Sources & Weights
            </h3>
            {sources.map((s, i) => (
              <div key={s.name} style={{ marginBottom: 12 }}>
                <div style={{
                  display: 'flex', justifyContent: 'space-between',
                  fontSize: 13, fontWeight: 600, marginBottom: 4
                }}>
                  <span>{s.label || s.name}</span>
                  <span style={{ color: '#71717a' }}>{s.weight || '—'}%</span>
                </div>
                <div style={{
                  fontSize: 11, color: '#a1a1aa', marginBottom: 5
                }}>{s.category || '—'}</div>
                <div style={{
                  height: 4, borderRadius: 2,
                  background: '#f4f4f5', overflow: 'hidden'
                }}>
                  <div style={{
                    height: '100%', width: `${s.weight || 33}%`,
                    background: sourceColors[i % sourceColors.length],
                    borderRadius: 2,
                  }} />
                </div>
              </div>
            ))}
            <a href="#" style={{
              fontSize: 11, color: '#4f46e5', textDecoration: 'none',
              display: 'block', marginTop: 8
            }}>View full methodology →</a>
          </div>

          {/* Community voting */}
          <div style={{
            background: 'white', borderRadius: 10,
            border: '1px solid #e5e7fb', padding: '18px 18px'
          }}>
            <h3 style={{ fontSize: 13, fontWeight: 800, marginBottom: 4, letterSpacing: '0.5px', color: '#52525b', textTransform: 'uppercase' }}>
              Community Sentiment
            </h3>
            <p style={{ fontSize: 11, color: '#a1a1aa', marginBottom: 14 }}>
              Informal · not included in composite score
            </p>
            <div style={{
              background: '#f7f6ff', borderRadius: 8, padding: '14px',
              textAlign: 'center', border: '1px dashed #c7d2fe'
            }}>
              <div style={{ fontSize: 22, marginBottom: 6 }}>🗳️</div>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                Which is better?
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                {models.slice(0, 2).map(m => (
                  <button key={m.model} style={{
                    flex: 1, padding: '8px', borderRadius: 6,
                    border: '1px solid #c7d2fe', background: 'white',
                    fontSize: 12, fontWeight: 600, cursor: 'pointer',
                    color: '#4f46e5'
                  }}>
                    {m.model}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Stats */}
          <div style={{
            background: '#4f46e5', borderRadius: 10, padding: '18px 18px', color: 'white'
          }}>
            <h3 style={{ fontSize: 13, fontWeight: 800, marginBottom: 14, letterSpacing: '0.5px', opacity: 0.7, textTransform: 'uppercase' }}>
              This Week
            </h3>
            {[
              ['Rank changes', '14'],
              ['New models', '2'],
              ['Sources live', `${sources.length}/3`],
              ['Feed entries', stats.feed_entries || '0'],
            ].map(([label, val]) => (
              <div key={label} style={{
                display: 'flex', justifyContent: 'space-between',
                marginBottom: 10, fontSize: 13
              }}>
                <span style={{ opacity: 0.75 }}>{label}</span>
                <strong>{val}</strong>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{
        textAlign: 'center', padding: '16px 24px 32px',
        fontSize: 12, color: '#a1a1aa'
      }}>
        Data updates hourly · Methodology is public · Not affiliated with any lab
      </div>
    </div>
  );
}

export default App;
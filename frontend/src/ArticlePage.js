import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useParams, useNavigate } from 'react-router-dom';
import ModelComments from './components/ModelComments';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:5001/api';
const API = axios.create({ baseURL: API_BASE_URL, timeout: 5000 });

const tierConfig = {
  big: { label: 'BIG MOVE', color: '#ef4444', bg: '#fef2f2', border: '#fecaca' },
  moderate: { label: 'UPDATE', color: '#d97706', bg: '#fffbeb', border: '#fde68a' },
  small: { label: 'SHIFT', color: '#16a34a', bg: '#f0fdf4', border: '#bbf7d0' },
};

export default function ArticlePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [article, setArticle] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    API.get(`/feed/entry/${id}`)
      .then(res => {
        setArticle(res.data);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error fetching article:', err);
        setArticle(null);
        setLoading(false);
      });
  }, [id]);

  if (loading) return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', fontFamily: 'sans-serif', color: '#4f46e5' }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 40, marginBottom: 16 }}>🤖</div>
        <div style={{ fontSize: 18, fontWeight: 600 }}>Loading article...</div>
      </div>
    </div>
  );

  if (!article) return (
    <div style={{ fontFamily: "'Inter', system-ui, sans-serif", background: '#f7f6ff', minHeight: '100vh' }}>
      <div style={{ background: '#4f46e5', color: 'white', padding: '12px 24px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => navigate('/')} style={{ background: 'transparent', border: 'none', color: 'white', fontSize: 20, cursor: 'pointer' }}>←</button>
        <div style={{ fontWeight: 800, fontSize: 18 }}>Article not found</div>
      </div>
      <div style={{ padding: 24, color: '#71717a' }}>This article could not be found.</div>
    </div>
  );

  const tier = tierConfig[article.tier] || tierConfig.moderate;
  const bodyIsUrl = article.body && article.body.trim().startsWith('http');

  return (
    <div style={{ fontFamily: "'Inter', system-ui, sans-serif", background: '#f7f6ff', minHeight: '100vh', color: '#18181b' }}>
      {/* Topbar */}
      <div style={{
        background: '#4f46e5', color: 'white', padding: '12px 24px',
        display: 'flex', alignItems: 'center', gap: 12,
        position: 'sticky', top: 0, zIndex: 100,
      }}>
        <button onClick={() => navigate('/')} style={{ background: 'transparent', border: 'none', color: 'white', fontSize: 20, cursor: 'pointer' }}>←</button>
        <div style={{ fontWeight: 800, fontSize: 18, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {article.headline}
        </div>
        <span style={{
          background: 'rgba(255,255,255,0.15)', borderRadius: 20,
          padding: '2px 10px', fontSize: 11, fontWeight: 600, letterSpacing: '0.5px', whiteSpace: 'nowrap'
        }}>
          {tier.label}
        </span>
      </div>

      <div style={{ maxWidth: 780, margin: '24px auto', padding: '0 24px' }}>
        {/* Article card */}
        <div style={{ background: 'white', borderRadius: 12, border: `1px solid ${tier.border}`, padding: '24px 28px', marginBottom: 20 }}>
          {/* Tier stamp */}
          <div style={{ marginBottom: 16 }}>
            <span style={{
              display: 'inline-block',
              background: tier.bg, border: `1.5px solid ${tier.border}`,
              borderRadius: 6, padding: '4px 10px',
              fontSize: 10, fontWeight: 800, letterSpacing: '1px', color: tier.color,
            }}>
              {tier.label}
            </span>
          </div>

          {/* Headline */}
          <h1 style={{ fontSize: 22, fontWeight: 800, lineHeight: 1.3, marginBottom: 16, color: '#18181b' }}>
            {article.headline}
          </h1>

          {/* Body or URL */}
          {bodyIsUrl ? (
            <div style={{ marginBottom: 16 }}>
              <a
                href={article.body.trim()}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: '#4f46e5', fontSize: 14, wordBreak: 'break-all', textDecoration: 'underline' }}
              >
                {article.body.trim()}
              </a>
            </div>
          ) : (
            article.body && (
              <p style={{ fontSize: 15, color: '#52525b', lineHeight: 1.7, marginBottom: 16 }}>
                {article.body}
              </p>
            )
          )}

          {/* Source and timestamp */}
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginTop: 8 }}>
            <span style={{
              background: '#ede9fe', color: '#5b21b6',
              padding: '3px 10px', borderRadius: 4, fontWeight: 600, fontSize: 12
            }}>
              {article.source}
            </span>
            <span style={{ color: '#a1a1aa', fontSize: 12 }}>{article.created_at}</span>
          </div>
        </div>

        {/* Comments section */}
        <div style={{ background: 'white', borderRadius: 12, border: '1px solid #e5e7fb', padding: '20px 24px' }}>
          <h3 style={{ fontSize: 14, fontWeight: 800, color: '#52525b', marginBottom: 12 }}>Comments</h3>
          <ModelComments model={`article_${id}`} autoExpand={true} />
        </div>
      </div>
    </div>
  );
}

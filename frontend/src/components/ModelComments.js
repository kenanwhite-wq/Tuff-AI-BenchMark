import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';

const API_BASE_URL =
  process.env.REACT_APP_API_BASE_URL ||
  (typeof window !== 'undefined' && ['localhost', '127.0.0.1', '0.0.0.0'].includes(window.location.hostname)
    ? 'http://localhost:5001/api'
    : '/api');

const API = axios.create({
  baseURL: API_BASE_URL,
  timeout: 5000,
});

function getSessionId() {
  if (typeof window === 'undefined') return 'anonymous';
  let sessionId = window.localStorage.getItem('comment-session-id');
  if (!sessionId) {
    sessionId = `session-${Math.random().toString(36).slice(2, 10)}`;
    window.localStorage.setItem('comment-session-id', sessionId);
  }
  return sessionId;
}

function CommentCard({ comment, onReply, onLike, onDelete, level = 0 }) {
  return (
    <div style={{ background: '#fff', border: '1px solid #eef2ff', borderRadius: 8, padding: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#4f46e5' }}>
          {comment.username || 'Anonymous'}
        </div>
        <div style={{ fontSize: 10, color: '#a1a1aa' }}>
          {comment.created_at ? new Date(comment.created_at).toLocaleString() : 'just now'}
        </div>
      </div>
      <div style={{ fontSize: 13, color: '#18181b', marginTop: 6, lineHeight: 1.4 }}>{comment.comment}</div>
      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <button
          type="button"
          onClick={() => onLike(comment.id, false)}
          style={{ background: 'none', border: 'none', color: '#a1a1aa', cursor: 'pointer', padding: 0, fontSize: 12 }}
        >
          ❤️ {comment.likes || 0}
        </button>
        <button
          type="button"
          onClick={() => onReply(comment)}
          style={{ background: 'none', border: 'none', color: '#a1a1aa', cursor: 'pointer', padding: 0, fontSize: 12 }}
        >
          Reply
        </button>
        <button
          type="button"
          onClick={() => onDelete(comment.id)}
          style={{ background: 'none', border: 'none', color: '#a1a1aa', cursor: 'pointer', padding: 0, fontSize: 12 }}
        >
          Delete
        </button>
      </div>
      {comment.replies && comment.replies.length > 0 ? (
        <div style={{ marginTop: 8, paddingLeft: 12 + level * 12, borderLeft: '2px solid #eef2ff', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {comment.replies.map((reply) => (
            <CommentCard
              key={reply.id}
              comment={reply}
              onReply={onReply}
              onLike={onLike}
              onDelete={onDelete}
              level={level + 1}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ModelComments({ model, autoExpand = false }) {
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [expanded, setExpanded] = useState(Boolean(autoExpand));
  const [newComment, setNewComment] = useState('');
  const [username, setUsername] = useState('');
  const [replyingTo, setReplyingTo] = useState(null);
  const [feedback, setFeedback] = useState('');
  const [feedbackDetails, setFeedbackDetails] = useState('');
  const sessionId = useMemo(() => getSessionId(), []);

  const loadComments = useCallback(async () => {
    if (!model) return;
    setLoading(true);
    try {
      const response = await API.get(`/comments/${encodeURIComponent(model)}?tree=1`);
      setComments(Array.isArray(response.data) ? response.data : []);
    } catch (err) {
      console.error('Error loading comments:', err);
    } finally {
      setLoading(false);
    }
  }, [model]);

  useEffect(() => {
    setExpanded(Boolean(autoExpand));
  }, [autoExpand]);

  useEffect(() => {
    if ((expanded || autoExpand) && model) {
      loadComments();
    }
  }, [expanded, autoExpand, loadComments, model]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!newComment.trim()) return;

    setSubmitting(true);
    setFeedback('');
    setFeedbackDetails('');
    try {
      const response = await API.post('/comments', {
        model,
        comment: newComment.trim(),
        username: username.trim() || null,
        session_id: sessionId,
        parent_id: replyingTo ? replyingTo.id : null,
      }, {
        headers: { 'Content-Type': 'application/json' },
      });

      if (response.status >= 400 || response.data?.error) {
        const message = response.data?.error || `Unable to post comment (${response.status})`;
        setFeedback(message);
        setFeedbackDetails(`/api/comments -> ${response.status}`);
        return;
      }

      setNewComment('');
      setReplyingTo(null);
      setExpanded(true);
      try {
        await loadComments();
      } catch (refreshError) {
        console.warn('Comment posted but refresh failed:', refreshError);
      }
      setFeedback('Comment posted');
    } catch (err) {
      console.error('Error posting comment:', err);
      const serverMessage = err.response?.data?.error || err.message || 'Unable to post comment right now';
      const status = err.response?.status ? ` ${err.response.status}` : '';
      setFeedback(serverMessage);
      setFeedbackDetails(`/api/comments${status}`);
    } finally {
      setSubmitting(false);
    }
  };

  const toggleLike = async (commentId, liked) => {
    try {
      if (liked) {
        await API.post(`/comments/${commentId}/unlike`, { session_id: sessionId });
      } else {
        await API.post(`/comments/${commentId}/like`, { session_id: sessionId });
      }
      await loadComments();
    } catch (err) {
      console.error('Error toggling like:', err);
    }
  };

  const removeComment = async (commentId) => {
    if (!window.confirm('Remove this comment?')) return;
    try {
      await API.delete(`/comments/${commentId}`, { data: { session_id: sessionId } });
      await loadComments();
    } catch (err) {
      console.error('Error deleting comment:', err);
    }
  };

  return (
    <div style={{ marginTop: 10 }} onClick={(event) => event.stopPropagation()}>
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        style={{
          background: 'none',
          border: 'none',
          color: '#4f46e5',
          cursor: 'pointer',
          padding: 0,
          fontSize: 12,
          fontWeight: 700,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        💬 {comments.length} {comments.length === 1 ? 'comment' : 'comments'}
        <span style={{ color: '#a1a1aa', fontSize: 10 }}>{expanded ? '▼' : '▶'}</span>
      </button>

      {expanded && (
        <div style={{ marginTop: 10 }}>
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 }}>
            {feedback ? (
              <div style={{ fontSize: 12, color: feedback === 'Comment posted' ? '#16a34a' : '#dc2626' }}>
                <div>{feedback}</div>
                {feedbackDetails ? <div style={{ marginTop: 2, color: '#71717a', fontSize: 11 }}>{feedbackDetails}</div> : null}
              </div>
            ) : null}
            {replyingTo ? (
              <div style={{ fontSize: 12, color: '#4f46e5' }}>
                Replying to {replyingTo.username || 'Anonymous'}
              </div>
            ) : null}
            <input
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Your name (optional)"
              style={{ padding: '7px 9px', borderRadius: 6, border: '1px solid #e5e7fb', fontSize: 12 }}
            />
            <textarea
              rows={3}
              value={newComment}
              onChange={(event) => setNewComment(event.target.value)}
              placeholder="Share a quick note about this model..."
              style={{ padding: '7px 9px', borderRadius: 6, border: '1px solid #e5e7fb', fontSize: 12, resize: 'vertical' }}
            />
            <button
              type="submit"
              disabled={submitting || !newComment.trim()}
              style={{
                alignSelf: 'flex-start',
                padding: '7px 12px',
                borderRadius: 6,
                border: 'none',
                background: '#4f46e5',
                color: 'white',
                cursor: submitting || !newComment.trim() ? 'not-allowed' : 'pointer',
                fontSize: 12,
                fontWeight: 600,
                opacity: submitting || !newComment.trim() ? 0.6 : 1,
              }}
            >
              {submitting ? 'Posting...' : 'Post comment'}
            </button>
          </form>

          {loading ? (
            <div style={{ color: '#a1a1aa', fontSize: 12 }}>Loading comments...</div>
          ) : comments.length === 0 ? (
            <div style={{ color: '#a1a1aa', fontSize: 12 }}>No comments yet. Start the conversation.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {comments.map((comment) => (
                <CommentCard
                  key={comment.id}
                  comment={comment}
                  onReply={setReplyingTo}
                  onLike={toggleLike}
                  onDelete={removeComment}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ModelComments;

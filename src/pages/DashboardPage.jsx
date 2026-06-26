/**
 * DashboardPage.jsx — Learning Analytics Dashboard.
 *
 * Shows:
 * - Course progress ring
 * - Quiz accuracy ring
 * - Stats grid: topics viewed, flashcards reviewed, quiz attempted
 * - Weak topics list (< 60% accuracy) with "Needs Revision" badges
 * - Strong topics list (>= 80% accuracy)
 * - Per-topic accuracy bar
 */
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { StatRing } from '../components/ProgressRing';
import {
  getDashboardSummary,
  getAllQuizResults,
  getViewedTopics,
} from '../utils/progress';

// Reads videoId + topics from sessionStorage (set by TranscriptPage)
const SESSION_KEY = 'lf_session';

function getSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

export function saveSession(videoId, topics) {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ videoId, topics }));
  } catch {}
}

const ACCURACY_COLOR = (pct) => {
  if (pct === null) return '#333';
  if (pct < 60) return '#ef4444';   // red
  if (pct < 80) return '#f59e0b';   // amber
  return '#10b981';                  // emerald
};

const ACCURACY_LABEL = (pct) => {
  if (pct === null) return null;
  if (pct < 60) return { text: 'Needs Revision', cls: 'bg-red-500/15 text-red-400 border-red-500/20' };
  if (pct < 80) return { text: 'Good', cls: 'bg-amber-500/15 text-amber-400 border-amber-500/20' };
  return { text: 'Mastered', cls: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20' };
};

export default function DashboardPage() {
  const navigate = useNavigate();
  const session = getSession();
  const { videoId, topics = [] } = session ?? {};

  const [summary, setSummary] = useState(null);
  const [quizResults, setQuizResults] = useState({});

  useEffect(() => {
    if (!videoId) return;
    setSummary(getDashboardSummary(videoId, topics.length));
    setQuizResults(getAllQuizResults(videoId));
  }, [videoId, topics.length]);

  if (!videoId) {
    return (
      <div className="min-h-screen bg-[#0B0B0B] flex flex-col items-center justify-center text-[#A3A3A3]">
        <p className="text-lg font-semibold mb-4">No active session found.</p>
        <button
          onClick={() => navigate('/')}
          className="px-5 py-2 bg-[#7C3AED] text-white text-sm rounded-lg hover:bg-[#6D28D9] transition"
        >
          ← Go Back
        </button>
      </div>
    );
  }

  const s = summary ?? { completionPct: 0, avgAccuracy: 0, viewedTopics: 0, totalTopics: topics.length, quizAttempted: 0, totalFlashcardReviews: 0, weakTopics: [], strongTopics: [] };

  return (
    <div className="min-h-screen bg-[#0B0B0B] text-[#F5F5F5]">
      {/* Nav */}
      <div className="border-b border-[#1a1a1a] bg-[#0e0e0e] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="text-[#737373] hover:text-[#F5F5F5] text-sm transition"
          >
            ← Back
          </button>
          <span className="text-[#2a2a2a]">|</span>
          <span className="text-sm font-semibold text-[#F5F5F5]">Learning Dashboard</span>
        </div>
        <span className="text-xs text-[#525252]">{topics.length} topics · {s.difficulty ?? 'intermediate'} level</span>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-10 space-y-10">

        {/* ── Header ── */}
        <div>
          <h1 className="text-2xl font-bold text-[#F5F5F5]">Your Progress</h1>
          <p className="text-sm text-[#525252] mt-1">Track your mastery across all topics</p>
        </div>

        {/* ── Ring Stats ── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {/* Completion */}
          <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-5 flex flex-col items-center gap-3">
            <StatRing pct={s.completionPct} color="#7C3AED" sublabel="done" />
            <div className="text-center">
              <p className="text-xs font-semibold text-[#F5F5F5]">Course Progress</p>
              <p className="text-[10px] text-[#525252]">{s.viewedTopics} / {s.totalTopics} topics</p>
            </div>
          </div>

          {/* Quiz accuracy */}
          <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-5 flex flex-col items-center gap-3">
            <StatRing pct={s.avgAccuracy} color={ACCURACY_COLOR(s.avgAccuracy)} sublabel="avg" />
            <div className="text-center">
              <p className="text-xs font-semibold text-[#F5F5F5]">Quiz Accuracy</p>
              <p className="text-[10px] text-[#525252]">{s.quizAttempted} topic{s.quizAttempted !== 1 ? 's' : ''} attempted</p>
            </div>
          </div>

          {/* Flashcards */}
          <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-5 flex flex-col items-center justify-center gap-2">
            <p className="text-3xl font-bold text-[#F5F5F5]">{s.totalFlashcardReviews}</p>
            <p className="text-xs font-semibold text-[#F5F5F5]">Cards Reviewed</p>
            <p className="text-[10px] text-[#525252]">Total flashcard reviews</p>
          </div>

          {/* Weak topics */}
          <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-5 flex flex-col items-center justify-center gap-2">
            <p className={`text-3xl font-bold ${s.weakTopics.length > 0 ? 'text-red-400' : 'text-emerald-400'}`}>
              {s.weakTopics.length}
            </p>
            <p className="text-xs font-semibold text-[#F5F5F5]">Weak Topics</p>
            <p className="text-[10px] text-[#525252]">Below 60% accuracy</p>
          </div>
        </div>

        {/* ── Per-topic accuracy ── */}
        {topics.length > 0 && (
          <div className="bg-[#111] border border-[#1e1e1e] rounded-xl p-6 space-y-4">
            <h2 className="text-sm font-semibold text-[#F5F5F5]">Topic Breakdown</h2>
            <div className="space-y-3">
              {topics.map((topic, idx) => {
                const result = quizResults[idx];
                const pct = result ? result.accuracy : null;
                const badge = ACCURACY_LABEL(pct);
                const viewed = (getViewedTopics(videoId) ?? []).includes(idx);

                return (
                  <div key={idx} className="flex items-center gap-4">
                    <div className="w-5 h-5 flex items-center justify-center shrink-0">
                      {viewed
                        ? <span className="text-xs text-emerald-400">✓</span>
                        : <span className="w-2 h-2 rounded-full bg-[#2a2a2a]" />
                      }
                    </div>
                    <p className="text-xs text-[#A3A3A3] w-48 truncate shrink-0">{topic.title}</p>
                    <div className="flex-1 h-1.5 bg-[#1e1e1e] rounded-full overflow-hidden">
                      {pct !== null && (
                        <div
                          className="h-full rounded-full transition-all duration-700"
                          style={{ width: `${pct}%`, background: ACCURACY_COLOR(pct) }}
                        />
                      )}
                    </div>
                    <span className="text-xs font-mono text-[#525252] w-10 text-right shrink-0">
                      {pct !== null ? `${pct}%` : '–'}
                    </span>
                    {badge && (
                      <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${badge.cls} shrink-0`}>
                        {badge.text}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Weak topics detail ── */}
        {s.weakTopics.length > 0 && (
          <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-6 space-y-3">
            <h2 className="text-sm font-semibold text-red-400 flex items-center gap-2">
              ⚠️ Topics Needing Revision
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {s.weakTopics.map(idx => (
                <div key={idx} className="flex items-center justify-between px-3 py-2 bg-[#111] border border-[#1e1e1e] rounded-lg">
                  <span className="text-xs text-[#D4D4D4] truncate">{topics[idx]?.title ?? `Topic ${idx + 1}`}</span>
                  <span className="text-xs font-mono text-red-400 ml-2 shrink-0">
                    {quizResults[idx]?.accuracy ?? 0}%
                  </span>
                </div>
              ))}
            </div>
            <button
              onClick={() => navigate('/')}
              className="mt-2 px-4 py-2 text-xs bg-red-500/10 border border-red-500/20 text-red-400 rounded-lg hover:bg-red-500/20 transition"
            >
              Review weak topics →
            </button>
          </div>
        )}

        {/* ── Strong topics ── */}
        {s.strongTopics.length > 0 && (
          <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-6 space-y-3">
            <h2 className="text-sm font-semibold text-emerald-400">🏆 Mastered Topics</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {s.strongTopics.map(idx => (
                <div key={idx} className="flex items-center justify-between px-3 py-2 bg-[#111] border border-[#1e1e1e] rounded-lg">
                  <span className="text-xs text-[#D4D4D4] truncate">{topics[idx]?.title ?? `Topic ${idx + 1}`}</span>
                  <span className="text-xs font-mono text-emerald-400 ml-2 shrink-0">
                    {quizResults[idx]?.accuracy ?? 0}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

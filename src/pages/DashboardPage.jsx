/**
 * DashboardPage.jsx — Learning Analytics Dashboard with Light/Dark Theme Support.
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

import ThemeToggle from '../components/ThemeToggle';

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
  if (pct === null) return '#94A3B8';
  if (pct < 60) return '#ef4444';   // red
  if (pct < 80) return '#f59e0b';   // amber
  return '#10b981';                  // emerald
};

const ACCURACY_LABEL = (pct) => {
  if (pct === null) return null;
  if (pct < 60) return { text: 'Needs Revision', cls: 'bg-red-100 text-red-800 border-red-300 dark:bg-red-500/15 dark:text-red-400 dark:border-red-500/20' };
  if (pct < 80) return { text: 'Good', cls: 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-500/15 dark:text-amber-400 dark:border-amber-500/20' };
  return { text: 'Mastered', cls: 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-400 dark:border-emerald-500/20' };
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
      <div className="min-h-screen bg-[#F1F5F9] dark:bg-[#0B0B0B] flex flex-col items-center justify-center text-slate-800 dark:text-[#A3A3A3]">
        <p className="text-xl font-extrabold mb-4 text-slate-900 dark:text-[#F5F5F5]">No active video session found.</p>
        <button
          onClick={() => navigate('/')}
          className="px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm rounded-xl transition shadow-lg"
        >
          ← Return to Home / Upload
        </button>
      </div>
    );
  }

  const s = summary ?? { completionPct: 0, avgAccuracy: 0, viewedTopics: 0, totalTopics: topics.length, quizAttempted: 0, totalFlashcardReviews: 0, weakTopics: [], strongTopics: [] };

  return (
    <div className="min-h-screen bg-[#F1F5F9] dark:bg-[#0B0B0B] text-slate-900 dark:text-[#F5F5F5] transition-colors duration-300">
      {/* Nav Header */}
      <div className="border-b border-slate-300 dark:border-[#1a1a1a] bg-white dark:bg-[#0e0e0e] px-6 py-3.5 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 px-4 py-2 text-xs font-extrabold text-white bg-indigo-600 hover:bg-indigo-700 dark:bg-[#7C3AED] dark:hover:bg-[#6D28D9] rounded-xl transition shadow-md cursor-pointer"
          >
            ← Back to Generated Content
          </button>
          <span className="text-slate-300 dark:text-[#2a2a2a]">|</span>
          <span className="text-base font-extrabold text-slate-900 dark:text-[#F5F5F5]">Learning Analytics Dashboard</span>
        </div>

        <div className="flex items-center gap-4">
          <span className="text-xs font-bold text-slate-600 dark:text-[#A3A3A3]">{topics.length} topics · {s.difficulty ?? 'intermediate'} level</span>
          <ThemeToggle />
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-10 space-y-10">

        {/* ── Title Header ── */}
        <div>
          <h1 className="text-3xl font-black text-slate-900 dark:text-[#F5F5F5]">Your Progress</h1>
          <p className="text-sm font-semibold text-slate-600 dark:text-[#A3A3A3] mt-1">Track your mastery and revision across all topics</p>
        </div>

        {/* ── Ring Stats ── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {/* Completion */}
          <div className="bg-white dark:bg-[#111] border-2 border-slate-300 dark:border-[#1e1e1e] rounded-2xl p-5 flex flex-col items-center gap-3 shadow-lg">
            <StatRing pct={s.completionPct} color="#4F46E5" sublabel="done" />
            <div className="text-center">
              <p className="text-xs font-extrabold text-slate-900 dark:text-[#F5F5F5]">Course Progress</p>
              <p className="text-[11px] font-bold text-slate-600 dark:text-[#A3A3A3]">{s.viewedTopics} / {s.totalTopics} topics</p>
            </div>
          </div>

          {/* Quiz accuracy */}
          <div className="bg-white dark:bg-[#111] border-2 border-slate-300 dark:border-[#1e1e1e] rounded-2xl p-5 flex flex-col items-center gap-3 shadow-lg">
            <StatRing pct={s.avgAccuracy} color={ACCURACY_COLOR(s.avgAccuracy)} sublabel="avg" />
            <div className="text-center">
              <p className="text-xs font-extrabold text-slate-900 dark:text-[#F5F5F5]">Quiz Accuracy</p>
              <p className="text-[11px] font-bold text-slate-600 dark:text-[#A3A3A3]">{s.quizAttempted} topic{s.quizAttempted !== 1 ? 's' : ''} attempted</p>
            </div>
          </div>

          {/* Flashcards */}
          <div className="bg-white dark:bg-[#111] border-2 border-slate-300 dark:border-[#1e1e1e] rounded-2xl p-5 flex flex-col items-center justify-center gap-2 shadow-lg">
            <p className="text-4xl font-black text-indigo-700 dark:text-[#F5F5F5]">{s.totalFlashcardReviews}</p>
            <p className="text-xs font-extrabold text-slate-900 dark:text-[#F5F5F5]">Cards Reviewed</p>
            <p className="text-[11px] font-bold text-slate-600 dark:text-[#A3A3A3]">Total flashcard reviews</p>
          </div>

          {/* Weak topics */}
          <div className="bg-white dark:bg-[#111] border-2 border-slate-300 dark:border-[#1e1e1e] rounded-2xl p-5 flex flex-col items-center justify-center gap-2 shadow-lg">
            <p className={`text-4xl font-black ${s.weakTopics.length > 0 ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
              {s.weakTopics.length}
            </p>
            <p className="text-xs font-extrabold text-slate-900 dark:text-[#F5F5F5]">Weak Topics</p>
            <p className="text-[11px] font-bold text-slate-600 dark:text-[#A3A3A3]">Below 60% accuracy</p>
          </div>
        </div>

        {/* ── Per-topic accuracy breakdown table ── */}
        {topics.length > 0 && (
          <div className="bg-white dark:bg-[#111] border-2 border-slate-300 dark:border-[#1e1e1e] rounded-2xl p-7 space-y-5 shadow-xl">
            <h2 className="text-base font-black text-slate-900 dark:text-[#F5F5F5]">Topic Breakdown</h2>
            <div className="space-y-4">
              {topics.map((topic, idx) => {
                const result = quizResults[idx];
                const pct = result ? result.accuracy : null;
                const badge = ACCURACY_LABEL(pct);
                const viewed = (getViewedTopics(videoId) ?? []).includes(idx);

                return (
                  <div key={idx} className="flex items-center gap-4 py-1">
                    <div className="w-5 h-5 flex items-center justify-center shrink-0">
                      {viewed
                        ? <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400">✓</span>
                        : <span className="w-2.5 h-2.5 rounded-full bg-slate-300 dark:bg-[#2a2a2a]" />
                      }
                    </div>
                    <p className="text-xs font-extrabold text-slate-900 dark:text-[#A3A3A3] w-56 truncate shrink-0">{topic.title}</p>
                    <div className="flex-1 h-2 bg-slate-200 dark:bg-[#1e1e1e] rounded-full overflow-hidden">
                      {pct !== null && (
                        <div
                          className="h-full rounded-full transition-all duration-700"
                          style={{ width: `${pct}%`, background: ACCURACY_COLOR(pct) }}
                        />
                      )}
                    </div>
                    <span className="text-xs font-mono font-bold text-slate-700 dark:text-[#525252] w-12 text-right shrink-0">
                      {pct !== null ? `${pct}%` : '–'}
                    </span>
                    {badge && (
                      <span className={`text-[10px] font-extrabold px-2.5 py-0.5 rounded-full border ${badge.cls} shrink-0`}>
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
          <div className="bg-red-50 dark:bg-red-500/5 border-2 border-red-300 dark:border-red-500/20 rounded-2xl p-6 space-y-4 shadow-md">
            <h2 className="text-sm font-black text-red-700 dark:text-red-400 flex items-center gap-2">
              ⚠️ Topics Needing Revision
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {s.weakTopics.map(idx => (
                <div key={idx} className="flex items-center justify-between px-4 py-2.5 bg-white dark:bg-[#111] border border-red-200 dark:border-[#1e1e1e] rounded-xl shadow-sm">
                  <span className="text-xs font-bold text-slate-900 dark:text-[#D4D4D4] truncate">{topics[idx]?.title ?? `Topic ${idx + 1}`}</span>
                  <span className="text-xs font-mono font-bold text-red-600 dark:text-red-400 ml-2 shrink-0">
                    {quizResults[idx]?.accuracy ?? 0}%
                  </span>
                </div>
              ))}
            </div>
            <button
              onClick={() => navigate('/')}
              className="mt-2 px-5 py-2.5 text-xs font-extrabold bg-red-600 hover:bg-red-700 text-white rounded-xl transition shadow-md"
            >
              Review weak topics →
            </button>
          </div>
        )}

        {/* ── Strong topics ── */}
        {s.strongTopics.length > 0 && (
          <div className="bg-emerald-50 dark:bg-emerald-500/5 border-2 border-emerald-300 dark:border-emerald-500/20 rounded-2xl p-6 space-y-4 shadow-md">
            <h2 className="text-sm font-black text-emerald-800 dark:text-emerald-400">🏆 Mastered Topics</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {s.strongTopics.map(idx => (
                <div key={idx} className="flex items-center justify-between px-4 py-2.5 bg-white dark:bg-[#111] border border-emerald-200 dark:border-[#1e1e1e] rounded-xl shadow-sm">
                  <span className="text-xs font-bold text-slate-900 dark:text-[#D4D4D4] truncate">{topics[idx]?.title ?? `Topic ${idx + 1}`}</span>
                  <span className="text-xs font-mono font-bold text-emerald-600 dark:text-emerald-400 ml-2 shrink-0">
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

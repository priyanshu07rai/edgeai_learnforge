/**
 * FloatingAI.jsx — Persistent floating AI Tutor (bottom-RIGHT corner).
 * Answers from transcript only (RAG). No hallucination.
 * Light/Dark theme-aware floating tutor modal.
 */
import React, { useState, useRef, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL !== undefined ? import.meta.env.VITE_API_BASE_URL : '';

async function askQuestion(videoId, topicIndex, question) {
  const res = await fetch(`${API_BASE}/qa/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_id: videoId, question, topic_index: topicIndex }),
  });
  if (!res.ok) throw new Error('Q&A failed');
  return res.json();
}

const QUICK_ACTIONS = [
  { label: '📖 Explain this topic', q: 'Explain this topic in simple terms.' },
  { label: '🔍 Simplify', q: 'Explain this topic simply for a beginner.' },
  { label: '🧪 Give examples', q: 'Give me concrete examples of the concepts in this topic.' },
  { label: '🎯 Interview questions', q: 'What interview questions might be asked about this topic?' },
  { label: '🔑 Key takeaways', q: 'What are the most important things to remember from this topic?' },
  { label: '⚠️ Common mistakes', q: 'What are common mistakes or misconceptions about this topic?' },
];

export default function FloatingAI({ videoId, topicIndex, topicTitle }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [searchAll, setSearchAll] = useState(false);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);
  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 100); }, [open]);
  useEffect(() => { setMessages([]); setInput(''); }, [topicIndex]);

  if (!videoId) return null;

  const send = async (text) => {
    const q = (text || input).trim();
    if (!q || loading) return;
    setInput('');
    setMessages(m => [...m, { role: 'user', text: q }]);
    setLoading(true);
    try {
      const topicArg = searchAll ? -1 : topicIndex;
      const res = await askQuestion(videoId, topicArg, q);
      setMessages(m => [...m, { role: 'ai', text: res.answer, sources: res.sources || [] }]);
    } catch {
      setMessages(m => [...m, { role: 'ai', text: 'Could not retrieve an answer. Make sure the video is processed.', sources: [] }]);
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  };

  const unreadCount = messages.filter(m => m.role === 'ai').length;

  return (
    <div className="fixed bottom-6 right-6 z-[100] flex flex-col items-end">

      {/* Chat panel */}
      {open && (
        <div className="mb-3 w-80 sm:w-[360px] bg-white dark:bg-[#0c0c0c] border-2 border-slate-300 dark:border-[#1e1e1e] rounded-2xl shadow-2xl flex flex-col overflow-hidden transition-all duration-300"
          style={{ maxHeight: '500px' }}>

          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-[#161616] bg-slate-100 dark:bg-[#0e0e0e]">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-full bg-indigo-100 dark:bg-[#7C3AED]/20 border border-indigo-300 dark:border-[#7C3AED]/30 flex items-center justify-center text-sm">🤖</div>
              <div>
                <p className="text-xs font-extrabold text-slate-900 dark:text-[#F0F0F0]">LearnForge Tutor</p>
                <p className="text-[9px] font-semibold text-slate-500 dark:text-[#404040]">Answers from transcript · No hallucination</p>
              </div>
            </div>
            <button onClick={() => setOpen(false)} className="text-slate-500 dark:text-[#383838] hover:text-slate-800 dark:hover:text-[#737373] text-xs font-bold transition">✕</button>
          </div>

          {/* Context selector */}
          <div className="flex items-center gap-2 px-4 py-2 border-b border-slate-200 dark:border-[#141414] bg-slate-50 dark:bg-[#0a0a0a]">
            <span className="text-[9px] font-bold text-slate-600 dark:text-[#383838] shrink-0">Context:</span>
            <button
              onClick={() => setSearchAll(false)}
              className={`text-[9px] px-2.5 py-1 rounded-full font-bold border transition-all ${
                !searchAll ? 'bg-indigo-600 text-white border-indigo-600 dark:bg-[#7C3AED]/15 dark:border-[#7C3AED]/30 dark:text-[#7C3AED]' : 'border-slate-300 dark:border-[#1e1e1e] text-slate-600 dark:text-[#404040] hover:text-slate-900 dark:hover:text-[#737373]'
              }`}
            >
              📍 {topicTitle ? topicTitle.slice(0, 22) + (topicTitle.length > 22 ? '…' : '') : 'Current topic'}
            </button>
            <button
              onClick={() => setSearchAll(true)}
              className={`text-[9px] px-2.5 py-1 rounded-full font-bold border transition-all ${
                searchAll ? 'bg-indigo-600 text-white border-indigo-600 dark:bg-[#7C3AED]/15 dark:border-[#7C3AED]/30 dark:text-[#7C3AED]' : 'border-slate-300 dark:border-[#1e1e1e] text-slate-600 dark:text-[#404040] hover:text-slate-900 dark:hover:text-[#737373]'
              }`}
            >
              🌐 Full course
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2.5 custom-scrollbar" style={{ maxHeight: '300px' }}>
            {messages.length === 0 && (
              <div className="space-y-1.5 pt-1">
                <p className="text-[9px] font-bold text-slate-500 dark:text-[#2a2a2a] text-center pb-1">Quick actions</p>
                {QUICK_ACTIONS.map((action, i) => (
                  <button key={i} onClick={() => send(action.q)}
                    className="w-full text-left text-[10px] font-semibold text-slate-700 dark:text-[#525252] px-3 py-2 bg-slate-50 dark:bg-[#0e0e0e] border border-slate-200 dark:border-[#181818] rounded-lg hover:border-indigo-400 dark:hover:border-[#7C3AED]/25 hover:text-indigo-700 dark:hover:text-[#A3A3A3] transition-all">
                    {action.label}
                  </button>
                ))}
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {msg.role === 'user' ? (
                  <div className="max-w-[82%] px-3 py-2 bg-indigo-600 dark:bg-[#7C3AED] rounded-2xl rounded-tr-sm text-[11px] font-semibold text-white leading-relaxed">
                    {msg.text}
                  </div>
                ) : (
                  <div className="max-w-[92%] space-y-1">
                    <div className="px-3 py-2.5 bg-slate-100 dark:bg-[#111] border border-slate-200 dark:border-[#1e1e1e] rounded-2xl rounded-tl-sm text-[11px] font-semibold text-slate-900 dark:text-[#C4C4C4] leading-relaxed">
                      {msg.text}
                    </div>
                    {msg.sources?.length > 0 && (
                      <details>
                        <summary className="text-[9px] font-bold text-slate-500 dark:text-[#2a2a2a] cursor-pointer hover:text-slate-800 dark:hover:text-[#404040] select-none list-none ml-1">
                          📄 {msg.sources.length} source{msg.sources.length > 1 ? 's' : ''} from transcript
                        </summary>
                        <div className="mt-1 space-y-1">
                          {msg.sources.map((src, j) => (
                            <div key={j} className="text-[9px] font-medium text-slate-600 dark:text-[#383838] bg-slate-50 dark:bg-[#090909] border border-slate-200 dark:border-[#141414] rounded px-2 py-1.5 italic">
                              {src}
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="px-3 py-2 bg-slate-100 dark:bg-[#111] border border-slate-200 dark:border-[#1e1e1e] rounded-2xl text-[11px] text-slate-600 dark:text-[#A3A3A3] flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-600 dark:bg-[#7C3AED] animate-ping" />
                  Thinking…
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input box */}
          <div className="p-2.5 border-t border-slate-200 dark:border-[#161616] bg-slate-100 dark:bg-[#0a0a0a] flex items-center gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && send()}
              placeholder="Ask a question about this video…"
              disabled={loading}
              className="flex-1 px-3 py-2 text-[11px] font-medium bg-white dark:bg-[#0e0e0e] border border-slate-300 dark:border-[#1e1e1e] rounded-xl text-slate-900 dark:text-[#D4D4D4] placeholder-slate-400 dark:placeholder-[#2a2a2a] focus:outline-none focus:border-indigo-500 dark:focus:border-[#7C3AED]/40 disabled:opacity-40 transition-all"
            />
            <button
              onClick={() => send()}
              disabled={!input.trim() || loading}
              className="px-3 py-2 bg-indigo-600 hover:bg-indigo-700 dark:bg-[#7C3AED] dark:hover:bg-[#6D28D9] disabled:bg-slate-300 dark:disabled:bg-[#141414] text-white text-xs font-bold rounded-xl transition-all"
            >→</button>
          </div>
        </div>
      )}

      {/* Trigger button */}
      <button
        onClick={() => setOpen(o => !o)}
        className={`flex items-center gap-2.5 px-4 py-2.5 rounded-2xl border-2 shadow-xl transition-all font-bold text-sm select-none ${
          open
            ? 'bg-indigo-600 border-indigo-600 text-white shadow-indigo-500/30'
            : 'bg-indigo-600 hover:bg-indigo-700 text-white border-indigo-600 dark:bg-[#0e0e0e] dark:border-[#1e1e1e] dark:text-[#D4D4D4] shadow-slate-300/50 dark:shadow-black/50'
        }`}
      >
        <span className="text-base">🤖</span>
        <span>AI Tutor</span>
        {!open && unreadCount > 0 && (
          <span className="w-2 h-2 rounded-full bg-amber-400 dark:bg-[#7C3AED] animate-pulse" />
        )}
      </button>
    </div>
  );
}

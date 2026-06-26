/**
 * FloatingAI.jsx — Persistent floating AI Tutor (bottom-RIGHT corner).
 * Answers from transcript only (RAG). No hallucination.
 * Capabilities: Explain / Simplify / Examples / Interview Questions / Custom question.
 */
import React, { useState, useRef, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

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
        <div className="mb-3 w-80 sm:w-[360px] bg-[#0c0c0c] border border-[#1e1e1e] rounded-2xl shadow-2xl shadow-black/70 flex flex-col overflow-hidden"
          style={{ maxHeight: '500px' }}>

          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[#161616] bg-[#0e0e0e]">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-full bg-[#7C3AED]/20 border border-[#7C3AED]/30 flex items-center justify-center text-sm">🤖</div>
              <div>
                <p className="text-xs font-bold text-[#F0F0F0]">LearnForge Tutor</p>
                <p className="text-[9px] text-[#404040]">Answers from transcript · No hallucination</p>
              </div>
            </div>
            <button onClick={() => setOpen(false)} className="text-[#383838] hover:text-[#737373] text-xs transition">✕</button>
          </div>

          {/* Context selector */}
          <div className="flex items-center gap-2 px-4 py-2 border-b border-[#141414] bg-[#0a0a0a]">
            <span className="text-[9px] text-[#383838] shrink-0">Context:</span>
            <button
              onClick={() => setSearchAll(false)}
              className={`text-[9px] px-2.5 py-1 rounded-full font-semibold border transition-all ${
                !searchAll ? 'bg-[#7C3AED]/15 border-[#7C3AED]/30 text-[#7C3AED]' : 'border-[#1e1e1e] text-[#404040] hover:text-[#737373]'
              }`}
            >
              📍 {topicTitle ? topicTitle.slice(0, 22) + (topicTitle.length > 22 ? '…' : '') : 'Current topic'}
            </button>
            <button
              onClick={() => setSearchAll(true)}
              className={`text-[9px] px-2.5 py-1 rounded-full font-semibold border transition-all ${
                searchAll ? 'bg-[#7C3AED]/15 border-[#7C3AED]/30 text-[#7C3AED]' : 'border-[#1e1e1e] text-[#404040] hover:text-[#737373]'
              }`}
            >
              🌐 Full course
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2.5" style={{ maxHeight: '300px' }}>
            {messages.length === 0 && (
              <div className="space-y-1.5 pt-1">
                <p className="text-[9px] text-[#2a2a2a] text-center pb-1">Quick actions</p>
                {QUICK_ACTIONS.map((action, i) => (
                  <button key={i} onClick={() => send(action.q)}
                    className="w-full text-left text-[10px] text-[#525252] px-3 py-2 bg-[#0e0e0e] border border-[#181818] rounded-lg hover:border-[#7C3AED]/25 hover:text-[#A3A3A3] transition-all">
                    {action.label}
                  </button>
                ))}
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {msg.role === 'user' ? (
                  <div className="max-w-[82%] px-3 py-2 bg-[#7C3AED] rounded-2xl rounded-tr-sm text-[11px] text-white leading-relaxed">
                    {msg.text}
                  </div>
                ) : (
                  <div className="max-w-[92%] space-y-1">
                    <div className="px-3 py-2.5 bg-[#111] border border-[#1e1e1e] rounded-2xl rounded-tl-sm text-[11px] text-[#C4C4C4] leading-relaxed">
                      {msg.text}
                    </div>
                    {msg.sources?.length > 0 && (
                      <details>
                        <summary className="text-[9px] text-[#2a2a2a] cursor-pointer hover:text-[#404040] select-none list-none ml-1">
                          📄 {msg.sources.length} source{msg.sources.length > 1 ? 's' : ''} from transcript
                        </summary>
                        <div className="mt-1 space-y-1">
                          {msg.sources.map((src, j) => (
                            <div key={j} className="text-[9px] text-[#383838] bg-[#090909] border border-[#141414] rounded px-2 py-1.5 italic">
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
                <div className="px-3 py-2.5 bg-[#111] border border-[#1e1e1e] rounded-2xl rounded-tl-sm flex gap-1 items-center">
                  {[0, 150, 300].map(d => (
                    <span key={d} className="w-1.5 h-1.5 bg-[#7C3AED]/60 rounded-full animate-bounce"
                      style={{ animationDelay: `${d}ms` }} />
                  ))}
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="px-3 py-3 border-t border-[#141414] flex gap-2">
            <input
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder="Ask anything…"
              disabled={loading}
              className="flex-1 px-3 py-2 text-[11px] bg-[#0e0e0e] border border-[#1e1e1e] rounded-xl text-[#D4D4D4] placeholder-[#2a2a2a] focus:outline-none focus:border-[#7C3AED]/40 disabled:opacity-40 transition-all"
            />
            <button
              onClick={() => send()}
              disabled={!input.trim() || loading}
              className="px-3 py-2 bg-[#7C3AED] hover:bg-[#6D28D9] disabled:bg-[#141414] disabled:text-[#2a2a2a] text-white text-xs font-bold rounded-xl transition-all"
            >→</button>
          </div>
        </div>
      )}

      {/* Trigger button */}
      <button
        onClick={() => setOpen(o => !o)}
        className={`flex items-center gap-2.5 px-4 py-2.5 rounded-2xl border shadow-xl shadow-black/50 transition-all font-semibold text-sm ${
          open
            ? 'bg-[#7C3AED] border-[#7C3AED] text-white'
            : 'bg-[#0e0e0e] border-[#1e1e1e] text-[#737373] hover:border-[#7C3AED]/40 hover:text-[#D4D4D4]'
        }`}
      >
        <span className="text-base">🤖</span>
        <span>AI Tutor</span>
        {!open && unreadCount > 0 && (
          <span className="w-2 h-2 rounded-full bg-[#7C3AED] animate-pulse" />
        )}
      </button>
    </div>
  );
}

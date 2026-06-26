/**
 * AskAI.jsx — RAG-based Q&A chat panel for a single topic.
 * Answers come ONLY from the video transcript (no hallucination).
 */
import React, { useState, useRef, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function askQuestion(videoId, topicIndex, question) {
  const resp = await fetch(`${API_BASE}/qa/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_id: videoId, question, topic_index: topicIndex }),
  });
  if (!resp.ok) throw new Error('Q&A request failed');
  return resp.json();
}

const SUGGESTED_QUESTIONS = [
  'What is the main topic covered here?',
  'Explain the key concept simply.',
  'What are the important dates or facts?',
  'Who are the key figures mentioned?',
];

export default function AskAI({ videoId, topicIndex, topicTitle }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Reset on topic change
  useEffect(() => {
    setMessages([]);
    setInput('');
  }, [topicIndex]);

  const sendMessage = async (text) => {
    const q = (text || input).trim();
    if (!q || isLoading) return;
    setInput('');

    const userMsg = { role: 'user', text: q, ts: Date.now() };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const result = await askQuestion(videoId, topicIndex, q);
      const aiMsg = {
        role: 'ai',
        text: result.answer,
        sources: result.sources || [],
        ts: Date.now(),
      };
      setMessages(prev => [...prev, aiMsg]);
    } catch (e) {
      setMessages(prev => [...prev, {
        role: 'ai',
        text: 'Sorry, Q&A is temporarily unavailable. Please try again.',
        sources: [],
        ts: Date.now(),
      }]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col h-full min-h-[500px]">
      {/* Header */}
      <div className="px-6 py-4 border-b border-[#262626]">
        <div className="flex items-center gap-2">
          <span className="text-base">🤖</span>
          <div>
            <p className="text-xs font-semibold text-[#A3A3A3] uppercase tracking-wider">Ask AI</p>
            <p className="text-xs text-[#525252]">Answers from transcript only · No hallucination</p>
          </div>
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 max-h-[380px]">

        {/* Empty state with suggestions */}
        {messages.length === 0 && (
          <div className="space-y-4">
            <p className="text-xs text-[#525252] text-center">
              Ask anything about <span className="text-[#A3A3A3] font-medium">{topicTitle}</span>
            </p>
            <div className="grid grid-cols-1 gap-2">
              {SUGGESTED_QUESTIONS.map((q, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(q)}
                  className="text-left px-3 py-2 text-xs text-[#A3A3A3] bg-[#1a1a1a] border border-[#2a2a2a] rounded-lg hover:border-[#7C3AED]/40 hover:text-[#D4D4D4] transition-all"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Chat messages */}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] ${msg.role === 'user' ? 'order-2' : 'order-1'}`}>

              {msg.role === 'user' ? (
                <div className="px-4 py-2.5 bg-[#7C3AED] rounded-2xl rounded-tr-sm text-xs text-white leading-relaxed">
                  {msg.text}
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="px-4 py-3 bg-[#1E1E1E] border border-[#2a2a2a] rounded-2xl rounded-tl-sm text-xs text-[#D4D4D4] leading-relaxed">
                    {msg.text}
                  </div>
                  {/* Source citations */}
                  {msg.sources && msg.sources.length > 0 && (
                    <details className="group">
                      <summary className="text-[10px] text-[#525252] cursor-pointer hover:text-[#737373] ml-1 select-none list-none flex items-center gap-1">
                        <span className="group-open:rotate-90 transition-transform inline-block">▶</span>
                        View {msg.sources.length} source{msg.sources.length > 1 ? 's' : ''} from transcript
                      </summary>
                      <div className="mt-1.5 space-y-1.5">
                        {msg.sources.map((src, j) => (
                          <div key={j} className="px-3 py-2 text-[10px] text-[#525252] bg-[#141414] border border-[#1e1e1e] rounded-lg leading-relaxed">
                            <span className="text-[#404040] font-mono">[{j + 1}]</span> {src}
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Loading indicator */}
        {isLoading && (
          <div className="flex justify-start">
            <div className="px-4 py-3 bg-[#1E1E1E] border border-[#2a2a2a] rounded-2xl rounded-tl-sm">
              <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 bg-[#7C3AED] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-[#7C3AED] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-[#7C3AED] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="px-6 py-4 border-t border-[#262626]">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about this topic…"
            disabled={isLoading}
            className="flex-1 px-4 py-2.5 text-xs bg-[#1a1a1a] border border-[#2a2a2a] rounded-xl text-[#D4D4D4] placeholder-[#404040] focus:outline-none focus:border-[#7C3AED]/50 transition-all disabled:opacity-50"
          />
          <button
            onClick={() => sendMessage()}
            disabled={!input.trim() || isLoading}
            className="px-4 py-2.5 bg-[#7C3AED] hover:bg-[#6D28D9] disabled:bg-[#1a1a1a] disabled:text-[#404040] text-white text-xs font-semibold rounded-xl transition-all disabled:cursor-not-allowed"
          >
            Send
          </button>
        </div>
        <p className="mt-1.5 text-[10px] text-[#404040]">
          Press Enter to send · Answers sourced from transcript only
        </p>
      </div>
    </div>
  );
}

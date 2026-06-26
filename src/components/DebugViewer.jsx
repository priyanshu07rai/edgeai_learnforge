import React, { useState, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * DebugViewer — Developer tool to verify transcript grounding.
 * Shows: Topic Title → Raw Transcript → Notes → Flashcards → Quiz
 */
export default function DebugViewer({ videoId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [expandedSection, setExpandedSection] = useState('transcript');

  useEffect(() => {
    if (!videoId) return;
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/debug/${videoId}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(d => { setData(d); setSelectedIdx(0); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [videoId]);

  if (!videoId) return null;

  return (
    <div className="fixed inset-0 z-50 bg-[#050505]/95 backdrop-blur-sm flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[#1a1a1a] shrink-0">
        <div className="flex items-center gap-3">
          <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
          <span className="text-xs font-mono text-amber-400 uppercase tracking-widest">Debug Viewer</span>
          <span className="text-xs text-[#404040] font-mono ml-2">{videoId?.slice(0, 8)}…</span>
        </div>
        <div className="flex items-center gap-4">
          {data && (
            <span className="text-xs text-[#737373]">
              {data.topic_count} topics · verifying transcript grounding
            </span>
          )}
        </div>
      </div>

      {loading && (
        <div className="flex-1 flex items-center justify-center text-[#737373] text-sm">
          <div className="animate-spin w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full mr-3" />
          Loading debug data…
        </div>
      )}

      {error && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-red-400 text-sm font-mono">Error: {error}</div>
        </div>
      )}

      {data && (
        <div className="flex flex-1 overflow-hidden">
          {/* Topic sidebar */}
          <div className="w-56 shrink-0 border-r border-[#1a1a1a] overflow-y-auto">
            <div className="p-3 text-xs font-semibold text-[#404040] uppercase tracking-wider border-b border-[#1a1a1a]">
              Topics
            </div>
            {data.topics.map((t, i) => (
              <button
                key={i}
                onClick={() => { setSelectedIdx(i); setExpandedSection('transcript'); }}
                className={`w-full text-left px-3 py-2.5 text-xs border-b border-[#111] transition-colors ${
                  selectedIdx === i
                    ? 'bg-amber-400/10 text-amber-300 font-medium'
                    : 'text-[#737373] hover:text-[#A3A3A3] hover:bg-[#111]'
                }`}
              >
                <div className="flex items-start gap-2">
                  <span className={`shrink-0 w-4 h-4 rounded-full text-[9px] flex items-center justify-center font-bold ${
                    t.content_length > 0 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
                  }`}>
                    {t.content_length > 0 ? '✓' : '✗'}
                  </span>
                  <span className="line-clamp-2 leading-tight">{t.title}</span>
                </div>
                <div className="ml-6 mt-0.5 text-[10px] text-[#404040] font-mono">
                  {t.content_length.toLocaleString()} chars · {t.chunk_count} chunks
                </div>
              </button>
            ))}
          </div>

          {/* Detail panel */}
          {data.topics[selectedIdx] && (
            <div className="flex-1 overflow-y-auto">
              <TopicDebugPanel
                topic={data.topics[selectedIdx]}
                expandedSection={expandedSection}
                setExpandedSection={setExpandedSection}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TopicDebugPanel({ topic, expandedSection, setExpandedSection }) {
  const sections = [
    { id: 'transcript', label: 'Raw Transcript', icon: '📄' },
    { id: 'notes', label: 'Generated Notes', icon: '📝' },
    { id: 'flashcards', label: 'Flashcards', icon: '🃏' },
    { id: 'quiz', label: 'Quiz', icon: '❓' },
  ];

  return (
    <div className="p-6 space-y-4">
      {/* Topic header */}
      <div className="border border-amber-400/20 bg-amber-400/5 rounded-xl p-4">
        <div className="text-xs text-amber-400 font-mono uppercase tracking-wider mb-1">Selected Topic</div>
        <div className="text-lg font-bold text-[#F5F5F5]">{topic.title}</div>
        <div className="flex gap-4 mt-2 text-xs font-mono text-[#737373]">
          <span className={topic.content_length > 0 ? 'text-emerald-400' : 'text-red-400'}>
            {topic.content_length > 0 ? `✓ ${topic.content_length.toLocaleString()} chars of transcript content` : '✗ No transcript content found'}
          </span>
          <span>{topic.chunk_count} chunks in vector DB</span>
        </div>
      </div>

      {/* Section tabs */}
      <div className="flex gap-2 flex-wrap">
        {sections.map(s => (
          <button
            key={s.id}
            onClick={() => setExpandedSection(expandedSection === s.id ? null : s.id)}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-all ${
              expandedSection === s.id
                ? 'border-amber-400/40 bg-amber-400/10 text-amber-300'
                : 'border-[#262626] text-[#737373] hover:border-[#404040] hover:text-[#A3A3A3]'
            }`}
          >
            {s.icon} {s.label}
          </button>
        ))}
      </div>

      {/* Transcript section */}
      {expandedSection === 'transcript' && (
        <DebugSection title="Raw Transcript Chunk" badge={`${topic.content_length} chars`} color="amber">
          {topic.content ? (
            <pre className="font-mono text-xs text-[#A3A3A3] whitespace-pre-wrap leading-relaxed max-h-96 overflow-y-auto">
              {topic.content}
            </pre>
          ) : (
            <div className="text-red-400 text-sm font-mono">
              ✗ content field is empty. Re-process this video to embed transcript content in topics.json.
            </div>
          )}
        </DebugSection>
      )}

      {/* Notes section */}
      {expandedSection === 'notes' && (
        <DebugSection title="Generated Notes" color="violet">
          {topic.notes && topic.notes.summary ? (
            <div className="space-y-4 text-sm">
              <div>
                <div className="text-xs text-[#737373] uppercase tracking-wider mb-1">Summary</div>
                <GroundingCheck text={topic.notes.summary} transcript={topic.content} />
                <p className="text-[#D4D4D4]">{topic.notes.summary}</p>
              </div>
              <div>
                <div className="text-xs text-[#737373] uppercase tracking-wider mb-1">Key Points</div>
                <ul className="space-y-1">
                  {(topic.notes.key_points || []).map((pt, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <GroundingCheck text={pt} transcript={topic.content} inline />
                      <span className="text-[#D4D4D4]">{pt}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="text-xs text-[#737373] uppercase tracking-wider mb-1">Important Terms</div>
                <div className="flex flex-wrap gap-2">
                  {(topic.notes.important_terms || []).map((term, i) => (
                    <span key={i} className="px-2 py-1 bg-[#1a1a1a] border border-[#262626] rounded text-xs text-[#D4D4D4]">
                      {term}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-[#737373] italic text-sm">Notes not yet generated for this topic.</div>
          )}
        </DebugSection>
      )}

      {/* Flashcards section */}
      {expandedSection === 'flashcards' && (
        <DebugSection title="Generated Flashcards" color="blue">
          {topic.flashcards && topic.flashcards.cards?.length > 0 ? (
            <div className="space-y-3">
              {topic.flashcards.cards.map((card, i) => (
                <div key={i} className="border border-[#1a1a1a] rounded-lg p-3 space-y-2">
                  <div className="flex items-start gap-2">
                    <GroundingCheck text={card.question + ' ' + card.answer} transcript={topic.content} inline />
                    <div className="flex-1">
                      <div className="text-xs text-[#737373] mb-0.5">Q{i + 1}</div>
                      <div className="text-sm text-[#F5F5F5]">{card.question}</div>
                    </div>
                  </div>
                  <div className="ml-5 pl-3 border-l border-[#262626]">
                    <div className="text-xs text-[#737373] mb-0.5">Answer</div>
                    <div className="text-sm text-[#A3A3A3]">{card.answer}</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[#737373] italic text-sm">Flashcards not yet generated.</div>
          )}
        </DebugSection>
      )}

      {/* Quiz section */}
      {expandedSection === 'quiz' && (
        <DebugSection title="Generated Quiz" color="emerald">
          {topic.quiz && topic.quiz.quiz?.length > 0 ? (
            <div className="space-y-4">
              {topic.quiz.quiz.map((q, i) => (
                <div key={i} className="border border-[#1a1a1a] rounded-lg p-3 space-y-2">
                  <div className="flex items-start gap-2">
                    <GroundingCheck text={q.question} transcript={topic.content} inline />
                    <div className="text-sm font-medium text-[#F5F5F5] flex-1">Q{i + 1}: {q.question}</div>
                  </div>
                  <div className="ml-5 grid grid-cols-2 gap-1">
                    {(q.options || []).map((opt, j) => (
                      <div
                        key={j}
                        className={`text-xs px-2 py-1 rounded ${
                          opt.startsWith(q.correct_answer + ')')
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                            : 'text-[#737373] border border-[#1a1a1a]'
                        }`}
                      >
                        {opt}
                      </div>
                    ))}
                  </div>
                  {q.explanation && (
                    <div className="ml-5 text-xs text-[#737373] italic border-t border-[#1a1a1a] pt-1 mt-1">
                      {q.explanation}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[#737373] italic text-sm">Quiz not yet generated.</div>
          )}
        </DebugSection>
      )}
    </div>
  );
}

/**
 * GroundingCheck — visual indicator showing whether content references transcript text.
 * Green = content appears grounded (mentions specific years/names from transcript).
 * Red = content may be generic (no specific references).
 */
function GroundingCheck({ text = '', transcript = '', inline = false }) {
  const isGrounded = checkGrounding(text, transcript);
  const cls = inline
    ? `shrink-0 w-2 h-2 rounded-full mt-1.5 ${isGrounded ? 'bg-emerald-500' : 'bg-red-400'}`
    : `inline-block w-2 h-2 rounded-full mr-2 ${isGrounded ? 'bg-emerald-500' : 'bg-red-400'}`;
  const title = isGrounded
    ? 'Grounded: references specific content from transcript'
    : 'May be generic: no direct reference to transcript-specific content detected';
  return <span className={cls} title={title} />;
}

function checkGrounding(text, transcript) {
  if (!text || !transcript) return false;
  const genericPhrases = [
    'foundational concepts', 'best practices', 'practical examples',
    'implementation overview', 'covers the core', 'covers foundational',
    'key concepts', 'course content', 'further study'
  ];
  const lower = text.toLowerCase();
  if (genericPhrases.some(p => lower.includes(p))) return false;

  // Check if any years from transcript appear in the text
  const transcriptYears = (transcript.match(/\b[12][0-9]{3}\b/g) || []);
  const textYears = (text.match(/\b[12][0-9]{3}\b/g) || []);
  if (transcriptYears.length > 0 && textYears.some(y => transcriptYears.includes(y))) return true;

  // Check if any capitalized Latin words from transcript appear in text
  const transcriptNouns = (transcript.match(/\b[A-Z][a-zA-Z]{3,}\b/g) || []);
  const textNouns = (text.match(/\b[A-Z][a-zA-Z]{3,}\b/g) || []);
  if (transcriptNouns.length > 0 && textNouns.some(n => transcriptNouns.includes(n))) return true;

  return false;
}

function DebugSection({ title, badge, children, color = 'amber' }) {
  const colors = {
    amber: 'border-amber-500/20 text-amber-400',
    violet: 'border-violet-500/20 text-violet-400',
    blue: 'border-blue-500/20 text-blue-400',
    emerald: 'border-emerald-500/20 text-emerald-400',
  };
  return (
    <div className={`border rounded-xl p-4 ${colors[color].split(' ')[0]}`}>
      <div className={`flex items-center justify-between mb-3`}>
        <span className={`text-xs font-semibold uppercase tracking-wider ${colors[color].split(' ')[1]}`}>
          {title}
        </span>
        {badge && (
          <span className="text-xs font-mono text-[#404040]">{badge}</span>
        )}
      </div>
      {children}
    </div>
  );
}

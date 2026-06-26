import React, { useState, useEffect } from 'react';
import { saveQuizResult, markTopicViewed, recordFlashcardReview, getTopicAccuracyStatus } from '../utils/progress';

const parseMarkdown = (markdown) => {
  if (!markdown) return '';
  
  // Remove H1 title header if it matches the topic title at the start to avoid duplication
  let html = markdown.replace(/^#\s+.*$/m, '').trim();

  // Escapes html tag markers to prevent injection
  html = html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Headers (H3, H2, H1)
  html = html.replace(/^###\s+(.*$)/gim, '<h4 class="text-sm font-bold text-violet-300 mt-4 mb-2">$1</h4>');
  html = html.replace(/^##\s+(.*$)/gim, '<h3 class="text-md font-bold text-violet-400 mt-5 mb-2.5">$1</h3>');
  html = html.replace(/^#\s+(.*$)/gim, '<h2 class="text-lg font-extrabold text-white mt-6 mb-3 border-b border-[#1e1e1e] pb-1">$1</h2>');

  // Bold
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="font-bold text-[#E5E5E5]">$1</strong>');
  
  // Italic
  html = html.replace(/\*(.*?)\*/g, '<em class="italic text-[#A3A3A3]">$1</em>');

  // Inline code
  html = html.replace(/`(.*?)`/g, '<code class="px-1.5 py-0.5 text-xs font-mono bg-[#141414] border border-[#1e1e1e] rounded text-violet-300">$1</code>');

  // Multi-line code block wrapper
  html = html.replace(/```([\s\S]*?)```/g, '<pre class="p-4 bg-[#0e0e0e] border border-[#1e1e1e] rounded-xl text-xs font-mono text-[#D4D4D4] my-3 overflow-x-auto"><code>$1</code></pre>');

  // Horizontal Rule
  html = html.replace(/^---\s*$/gim, '<hr class="my-6 border-[#1e1e1e]" />');

  // Unordered list items with indentation
  // First, handle nested bullets (indented by 2 or more spaces or tab)
  html = html.replace(/^(?: {2,}|\t)\*\s+(.*$)/gim, '<li class="ml-6 list-disc pl-1 text-xs text-[#A3A3A3] leading-relaxed mt-1">$1</li>');
  html = html.replace(/^\*\s+(.*$)/gim, '<li class="ml-3 list-disc pl-1 text-sm text-[#D4D4D4] leading-relaxed mt-1.5">$1</li>');
  
  // Also handle dash list items (-)
  html = html.replace(/^(?: {2,}|\t)-\s+(.*$)/gim, '<li class="ml-6 list-disc pl-1 text-xs text-[#A3A3A3] leading-relaxed mt-1">$1</li>');
  html = html.replace(/^-\s+(.*$)/gim, '<li class="ml-3 list-disc pl-1 text-sm text-[#D4D4D4] leading-relaxed mt-1.5">$1</li>');

  // Ordered list items
  html = html.replace(/^(?: {2,}|\t)(\d+)\.\s+(.*$)/gim, '<li class="ml-6 list-decimal pl-1 text-xs text-[#A3A3A3] leading-relaxed mt-1">$2</li>');
  html = html.replace(/^(\d+)\.\s+(.*$)/gim, '<li class="ml-3 list-decimal pl-1 text-sm text-[#D4D4D4] leading-relaxed mt-1.5">$2</li>');

  // Helper to parse Markdown tables
  const parseTableRows = (rows) => {
    let hasHeader = false;
    let headerCols = [];
    const bodyRows = [];
    
    // Check if the second row is a separator row (e.g. |---|---|)
    if (rows.length > 1 && rows[1].includes('-')) {
      hasHeader = true;
      headerCols = rows[0].split('|').map(s => s.trim()).filter((s, idx) => idx > 0 && idx < rows[0].split('|').length - 1);
      
      for (let r = 2; r < rows.length; r++) {
        const cols = rows[r].split('|').map(s => s.trim()).filter((s, idx) => idx > 0 && idx < rows[r].split('|').length - 1);
        if (cols.length > 0) {
          bodyRows.push(cols);
        }
      }
    } else {
      for (let r = 0; r < rows.length; r++) {
        const cols = rows[r].split('|').map(s => s.trim()).filter((s, idx) => idx > 0 && idx < rows[r].split('|').length - 1);
        if (cols.length > 0) {
          bodyRows.push(cols);
        }
      }
    }
    
    let tableHtml = '<div class="overflow-x-auto my-4 border border-[#1e1e1e] rounded-xl"><table class="min-w-full divide-y divide-[#1e1e1e] bg-[#0c0c0c] text-sm">';
    if (hasHeader && headerCols.length > 0) {
      tableHtml += '<thead class="bg-[#141414] text-[#E5E5E5]"><tr>';
      headerCols.forEach(col => {
        tableHtml += `<th class="px-4 py-2 text-left font-semibold text-xs tracking-wider border-b border-[#1e1e1e]">${col}</th>`;
      });
      tableHtml += '</tr></thead>';
    }
    tableHtml += '<tbody class="divide-y divide-[#1e1e1e] text-[#D4D4D4]">';
    bodyRows.forEach(row => {
      tableHtml += '<tr class="hover:bg-[#141414]/50 transition-colors">';
      row.forEach(col => {
        tableHtml += `<td class="px-4 py-2 border-b border-[#1f1f1f] text-xs">${col}</td>`;
      });
      tableHtml += '</tr>';
    });
    tableHtml += '</tbody></table></div>';
    return tableHtml;
  };

  // Find tables and parse them
  const lines = html.split('\n');
  let inTable = false;
  let tableRows = [];
  const parsedLines = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('|') && line.endsWith('|')) {
      if (!inTable) {
        inTable = true;
        tableRows = [];
      }
      tableRows.push(line);
    } else {
      if (inTable) {
        parsedLines.push(parseTableRows(tableRows));
        inTable = false;
      }
      parsedLines.push(lines[i]);
    }
  }
  if (inTable) {
    parsedLines.push(parseTableRows(tableRows));
  }
  html = parsedLines.join('\n');

  // Paragraphs (split by newline, wrap plain text in <p>, ignore elements that are already HTML tags)
  const finalLines = html.split('\n');
  const processed = finalLines.map(line => {
    const trimmed = line.trim();
    if (!trimmed) return '';
    if (trimmed.startsWith('<h') || trimmed.startsWith('<li') || trimmed.startsWith('<pre') || 
        trimmed.startsWith('<code') || trimmed.startsWith('</pre') || trimmed.startsWith('</code') ||
        trimmed.startsWith('<hr') || trimmed.startsWith('<table') || trimmed.startsWith('<thead') || 
        trimmed.startsWith('<tbody') || trimmed.startsWith('<tr') || trimmed.startsWith('<td') || 
        trimmed.startsWith('<th') || trimmed.startsWith('<div') || trimmed.startsWith('</div') ||
        trimmed.startsWith('</table>') || trimmed.startsWith('</tr>') || trimmed.startsWith('</td>') ||
        trimmed.startsWith('</th>') || trimmed.startsWith('</tbody>') || trimmed.startsWith('</thead>')) {
      return line;
    }
    return `<p class="text-sm text-[#D4D4D4] leading-relaxed mt-2">${line}</p>`;
  });
  
  return processed.filter(Boolean).join('\n');
};

/**
 * TranscriptViewer — 4 tabs: Detailed Notes | Quick Revision | Flashcards | Quiz
 *
 * Detailed Notes renders rich structured sections:
 *   ▸ What is it?  ▸ Why it matters  ▸ How it works
 *   ▸ Example  ▸ Key Points  ▸ Key Terms
 *
 * Quick Revision renders a 30-second sheet:
 *   ▸ Definition  ▸ Key Facts (bullets)  ▸ Terms  ▸ Remember
 */
export default function TranscriptViewer({
  topics = [], activeTopicIdx,
  activeTab = 'notes', setActiveTab,
  notes = [], flashcards = [], quiz = [],
  isLoadingNotes = false, isLoadingFlashcards = false, isLoadingQuiz = false,
  videoId = null,
  overallSummary = null,
  isLoadingSummary = false,
  onTopicClick,
}) {
  const [cardIdx, setCardIdx] = useState(0);
  const [showAnswer, setShowAnswer] = useState(false);
  const [qIdx, setQIdx] = useState(0);
  const [selected, setSelected] = useState(null);
  const [showExp, setShowExp] = useState(false);
  const [answers, setAnswers] = useState([]);
  const [quizDone, setQuizDone] = useState(false);

  useEffect(() => { setCardIdx(0); setShowAnswer(false); resetQuiz(); }, [activeTopicIdx]);
  useEffect(() => { if (activeTab === 'quiz') resetQuiz(); }, [activeTab]);
  useEffect(() => {
    if (activeTab === 'notes' && videoId && topics[activeTopicIdx]) {
      markTopicViewed(videoId, activeTopicIdx);
    }
  }, [activeTab, activeTopicIdx, videoId, topics]);

  function resetQuiz() { setQIdx(0); setSelected(null); setShowExp(false); setAnswers([]); setQuizDone(false); }

  const activeTopic = topics[activeTopicIdx];
  const topicTitle = activeTopic?.title ?? '';

  // ── Shared states ─────────────────────────────────────────────────────────
  const Spinner = ({ msg }) => (
    <div className="flex-1 flex flex-col items-center justify-center p-16 gap-4">
      <div className="w-8 h-8 border-2 border-[#7C3AED]/20 border-t-[#7C3AED] rounded-full animate-spin" />
      <p className="text-sm font-medium text-[#525252]">{msg}</p>
    </div>
  );

  const Empty = ({ msg }) => (
    <div className="flex-1 flex items-center justify-center p-12">
      <p className="text-sm text-[#383838] italic">{msg}</p>
    </div>
  );

  // ── DETAILED NOTES ────────────────────────────────────────────────────────
  const renderNotes = () => {
    if (isLoadingNotes) return <Spinner msg="Extracting knowledge & building notes…" />;

    const note = notes[activeTopicIdx];
    if (!note) return <Spinner msg="Notes loading…" />;

    // Normalise — handle both old and new formats
    const d = note.detailed ?? {};
    const markdown = d.markdown ?? note.markdown ?? '';
    const summary = d.summary ?? note.summary ?? '';
    const important_terms = d.important_terms ?? note.important_terms ?? [];

    if (markdown) {
      return (
        <div className="p-7 space-y-7 select-text overflow-y-auto">
          {/* Title bar */}
          <div className="pb-4 border-b border-[#1a1a1a]">
            <h2 className="text-2xl font-bold text-[#F5F5F5] leading-tight">{note.topic}</h2>
            <p className="text-[10px] text-[#404040] mt-1.5 uppercase tracking-[0.2em]">Detailed Notes · Study Guide</p>
          </div>

          {/* Markdown Content */}
          <div 
            className="prose prose-invert max-w-none text-sm text-[#D4D4D4] space-y-4"
            dangerouslySetInnerHTML={{ __html: parseMarkdown(markdown) }}
          />

          {/* Key Terms */}
          {important_terms.length > 0 && (
            <div className="pt-6 border-t border-[#1a1a1a] space-y-3">
              <div className="flex items-center gap-2">
                <span>📚</span>
                <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Key Terms</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {important_terms.map((t, i) => (
                  <span key={i}
                    className="px-3 py-1 text-xs font-medium text-[#A3A3A3] bg-[#141414] border border-[#1e1e1e] rounded-lg hover:border-[#404040] transition-colors cursor-default">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      );
    }
    
    // Build dynamic sections list on the fly for backward compatibility or heuristic path
    let sections = d.sections ?? [];
    if (sections.length === 0) {
      if (d.what_is_it || note.summary) {
        sections.push({
          title: "Definition",
          icon: "📌",
          content: [d.what_is_it || note.summary]
        });
      }
      if (d.why_matters) {
        sections.push({
          title: "Advantages",
          icon: "💡",
          content: [d.why_matters]
        });
      }
      if (d.how_it_works && d.how_it_works.length > 0) {
        sections.push({
          title: "Steps",
          icon: "⚙️",
          content: d.how_it_works
        });
      }
      if (d.example) {
        sections.push({
          title: "Example",
          icon: "🧪",
          content: [d.example]
        });
      }
      if (d.common_mistakes && d.common_mistakes.length > 0) {
        sections.push({
          title: "Common Mistakes",
          icon: "⚠️",
          content: d.common_mistakes
        });
      }
      if (d.key_points && d.key_points.length > 0) {
        sections.push({
          title: "Key Takeaways",
          icon: "⚡",
          content: d.key_points
        });
      }
      if (d.interview_questions && d.interview_questions.length > 0) {
        sections.push({
          title: "Interview Questions",
          icon: "💬",
          content: d.interview_questions
        });
      }
    }

    const hasContent = sections.length > 0 || summary;

    if (!hasContent) {
      return (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 p-12">
          <div className="w-8 h-8 border-2 border-[#7C3AED]/20 border-t-[#7C3AED] rounded-full animate-spin" />
          <p className="text-sm text-[#525252]">Generating notes for <span className="text-[#7C3AED]">{note.topic}</span>…</p>
          <p className="text-xs text-[#383838]">Translating and extracting knowledge</p>
        </div>
      );
    }

    const getSectionColor = (title) => {
      const t = title.toLowerCase();
      if (t.includes('mistake') || t.includes('error')) return 'rose';
      if (t.includes('interview') || t.includes('question')) return 'amber';
      if (t.includes('step') || t.includes('how') || t.includes('install') || t.includes('config') || t.includes('setup')) return 'cyan';
      if (t.includes('example') || t.includes('code') || t.includes('command') || t.includes('verify')) return 'emerald';
      if (t.includes('definition') || t.includes('purpose') || t.includes('concept') || t.includes('what is it')) return 'violet';
      return 'violet';
    };

    return (
      <div className="p-7 space-y-7 select-text overflow-y-auto">

        {/* Title bar */}
        <div className="pb-4 border-b border-[#1a1a1a]">
          <h2 className="text-2xl font-bold text-[#F5F5F5] leading-tight">{note.topic}</h2>
          <p className="text-[10px] text-[#404040] mt-1.5 uppercase tracking-[0.2em]">Detailed Notes · Educational Content</p>
        </div>

        {/* Render dynamic sections */}
        {sections.map((sec, idx) => {
          const color = getSectionColor(sec.title);
          return (
            <Section key={idx} icon={sec.icon || '📌'} label={sec.title} color={color}>
              {Array.isArray(sec.content) ? (
                <ul className="space-y-2.5">
                  {sec.content.map((pt, i) => (
                    <li key={i} className="flex items-start gap-3">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#7C3AED] shrink-0 mt-2" />
                      <span className="text-sm text-[#D4D4D4] leading-relaxed">{pt}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-[#D4D4D4] leading-relaxed">{sec.content}</p>
              )}
            </Section>
          );
        })}

        {/* Key Terms */}
        {important_terms.length > 0 && (
          <Section icon="📚" label="Key Terms" color="slate">
            <div className="flex flex-wrap gap-2">
              {important_terms.map((t, i) => (
                <span key={i}
                  className="px-3 py-1 text-xs font-medium text-[#A3A3A3] bg-[#141414] border border-[#1e1e1e] rounded-lg hover:border-[#404040] transition-colors cursor-default">
                  {t}
                </span>
              ))}
            </div>
          </Section>
        )}
      </div>
    );
  };

  // ── QUICK REVISION ────────────────────────────────────────────────────────
  const renderRevision = () => {
    if (isLoadingNotes) return <Spinner msg="Building 30-second revision…" />;

    const note = notes[activeTopicIdx];
    if (!note) return <Spinner msg="Revision loading…" />;

    const r = note.revision ?? {
      definition: note.summary?.split('.')[0] ?? '',
      facts: note.key_points?.slice(0, 5) ?? [],
      terms: note.important_terms?.slice(0, 5) ?? [],
      remember: '',
    };

    const hasContent = r.definition || r.facts?.length > 0;

    if (!hasContent) {
      return (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 p-12">
          <div className="w-8 h-8 border-2 border-[#7C3AED]/20 border-t-[#7C3AED] rounded-full animate-spin" />
          <p className="text-sm text-[#525252]">Building quick revision for <span className="text-[#7C3AED]">{note.topic}</span>…</p>
        </div>
      );
    }

    return (
      <div className="p-7 space-y-5 select-text max-w-2xl">
        {/* Header */}
        <div className="pb-4 border-b border-[#1a1a1a]">
          <h2 className="text-2xl font-bold text-[#F5F5F5]">{note.topic}</h2>
          <p className="text-[10px] text-[#404040] mt-1.5 uppercase tracking-[0.2em]">Quick Revision · 30-second read</p>
        </div>

        {/* Definition */}
        {r.definition && (
          <div className="space-y-1.5">
            <p className="text-[10px] font-bold text-[#7C3AED] uppercase tracking-widest">Definition</p>
            <div className="px-4 py-3.5 bg-[#7C3AED]/08 border border-[#7C3AED]/20 rounded-xl">
              <p className="text-sm font-semibold text-[#C4B5FD] leading-relaxed">{r.definition}</p>
            </div>
          </div>
        )}

        {/* Key Facts */}
        {r.facts?.length > 0 && (
          <div className="space-y-2">
            <p className="text-[10px] font-bold text-emerald-400 uppercase tracking-widest">Key Facts</p>
            <div className="space-y-1.5">
              {r.facts.map((fact, i) => (
                <div key={i} className="flex items-start gap-3">
                  <span className="text-emerald-400 font-bold text-base shrink-0 leading-5">•</span>
                  <span className="text-sm text-[#D4D4D4] leading-snug">{fact}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Important Terms */}
        {r.terms?.length > 0 && (
          <div className="space-y-2">
            <p className="text-[10px] font-bold text-amber-400 uppercase tracking-widest">Important Terms</p>
            <div className="flex flex-wrap gap-2">
              {r.terms.map((t, i) => (
                <span key={i} className="px-3 py-1 text-xs font-bold text-amber-400 bg-amber-400/08 border border-amber-400/20 rounded-lg">
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Remember */}
        {r.remember && (
          <div className="space-y-1.5">
            <p className="text-[10px] font-bold text-rose-400 uppercase tracking-widest">Remember</p>
            <div className="px-4 py-3 bg-rose-500/05 border border-rose-500/15 rounded-xl">
              <p className="text-sm font-medium text-rose-300 leading-relaxed">{r.remember}</p>
            </div>
          </div>
        )}
      </div>
    );
  };

  // ── FLASHCARDS ────────────────────────────────────────────────────────────
  const renderFlashcards = () => {
    if (isLoadingFlashcards) return <Spinner msg="Generating flashcards…" />;
    const cardObj = flashcards[activeTopicIdx];
    const cards = cardObj?.cards ?? [];
    if (!cards.length) return <Empty msg="Flashcards loading…" />;

    const card = cards[cardIdx];

    return (
      <div className="p-7 flex flex-col gap-5">
        <div className="flex justify-between items-center text-xs text-[#404040]">
          <span className="font-semibold text-[#525252]">{topicTitle}</span>
          <span className="font-mono">{cardIdx + 1} / {cards.length}</span>
        </div>

        {/* Progress bar */}
        <div className="w-full h-0.5 bg-[#1e1e1e] rounded-full">
          <div className="h-full bg-[#7C3AED] rounded-full transition-all duration-300"
            style={{ width: `${((cardIdx + 1) / cards.length) * 100}%` }} />
        </div>

        {/* Card */}
        <div
          onClick={() => setShowAnswer(a => !a)}
          className="flex-1 min-h-[200px] rounded-xl border border-[#1e1e1e] bg-[#0e0e0e] flex flex-col items-center justify-center p-8 cursor-pointer hover:border-[#2a2a2a] transition-all group"
        >
          <p className="text-[9px] font-bold text-[#383838] uppercase tracking-widest mb-5 group-hover:text-[#404040] transition select-none">
            {showAnswer ? '▼ Answer' : '▲ Question · tap to reveal'}
          </p>
          <p className={`text-center leading-relaxed transition-all font-${showAnswer ? 'normal text-sm text-[#D4D4D4]' : 'semibold text-base text-[#E5E5E5]'}`}>
            {showAnswer ? card.answer : card.question}
          </p>
        </div>

        <div className="flex justify-between gap-3">
          <button
            onClick={() => { if (cardIdx > 0) { setCardIdx(cardIdx - 1); setShowAnswer(false); } }}
            disabled={cardIdx === 0}
            className="px-5 py-2 text-xs font-semibold border border-[#1e1e1e] rounded-lg text-[#525252] hover:border-[#404040] hover:text-[#D4D4D4] disabled:opacity-25 disabled:cursor-not-allowed transition-all"
          >← Prev</button>
          <button
            onClick={() => setShowAnswer(a => !a)}
            className="px-5 py-2 text-xs font-semibold border border-[#7C3AED]/30 text-[#7C3AED] rounded-lg hover:bg-[#7C3AED]/08 transition-all"
          >{showAnswer ? 'Hide' : 'Reveal'}</button>
          <button
            onClick={() => {
              if (cardIdx < cards.length - 1) {
                setCardIdx(cardIdx + 1); setShowAnswer(false);
                if (videoId) recordFlashcardReview(videoId, activeTopicIdx);
              }
            }}
            disabled={cardIdx === cards.length - 1}
            className="px-5 py-2 text-xs font-semibold border border-[#1e1e1e] rounded-lg text-[#525252] hover:border-[#404040] hover:text-[#D4D4D4] disabled:opacity-25 disabled:cursor-not-allowed transition-all"
          >Next →</button>
        </div>
      </div>
    );
  };

  // ── QUIZ ──────────────────────────────────────────────────────────────────
  const renderQuiz = () => {
    if (isLoadingQuiz) return <Spinner msg="Generating quiz…" />;
    const quizObj = quiz[activeTopicIdx];
    const questions = quizObj?.quiz ?? [];
    if (!questions.length) return <Empty msg="Quiz loading…" />;

    const total = questions.length;

    if (quizDone) {
      const correct = answers.filter(Boolean).length;
      const pct = Math.round((correct / total) * 100);
      if (videoId) saveQuizResult(videoId, activeTopicIdx, correct, total);
      const [col, label] = pct >= 80
        ? ['text-emerald-400', '🏆 Excellent!']
        : pct >= 60
        ? ['text-amber-400', '👍 Good — keep going']
        : ['text-red-400', '⚠️ Needs Revision'];

      return (
        <div className="flex-1 flex flex-col items-center justify-center gap-5 p-12">
          <p className={`text-6xl font-black ${col}`}>{pct}%</p>
          <p className="text-sm text-[#525252]">{correct} of {total} correct</p>
          <span className={`text-xs font-bold px-5 py-2 rounded-full border ${
            pct >= 80 ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' :
            pct >= 60 ? 'bg-amber-500/10 border-amber-500/20 text-amber-400' :
            'bg-red-500/10 border-red-500/20 text-red-400'
          }`}>{label}</span>
          <button onClick={resetQuiz}
            className="px-7 py-2.5 text-xs font-bold uppercase tracking-widest bg-[#7C3AED] hover:bg-[#6D28D9] text-white rounded-lg transition-all">
            Retry Quiz
          </button>
        </div>
      );
    }

    const q = questions[qIdx];
    const answered = selected !== null;
    const correct = q?.correct_answer;

    const optStyle = (letter) => {
      if (!answered) return 'border-[#1e1e1e] text-[#C4C4C4] hover:border-[#404040] hover:bg-[#141414]';
      if (letter === correct) return 'border-emerald-500/40 bg-emerald-500/08 text-emerald-300';
      if (letter === selected) return 'border-red-500/40 bg-red-500/08 text-red-300';
      return 'border-[#141414] text-[#404040]';
    };

    return (
      <div className="p-7 space-y-5">
        <div className="flex items-center justify-between text-xs text-[#404040]">
          <span>{topicTitle}</span>
          <span className="font-mono">{qIdx + 1} / {total}</span>
        </div>
        <div className="w-full h-0.5 bg-[#1a1a1a] rounded-full">
          <div className="h-full bg-[#7C3AED]/60 rounded-full transition-all duration-500"
            style={{ width: `${(qIdx / total) * 100}%` }} />
        </div>
        <p className="text-sm font-semibold text-[#F0F0F0] leading-relaxed pt-1">{q?.question}</p>
        <div className="space-y-2">
          {q?.options?.map((opt, i) => {
            const letter = ['A', 'B', 'C', 'D'][i];
            return (
              <button key={i}
                onClick={() => { if (!answered) { setSelected(letter); setShowExp(true); } }}
                disabled={answered}
                className={`w-full text-left px-4 py-3 rounded-lg border text-xs font-medium transition-all ${optStyle(letter)}`}>
                {opt}
              </button>
            );
          })}
        </div>
        {showExp && q?.explanation && (
          <div className={`px-4 py-3 rounded-lg border text-xs leading-relaxed ${
            selected === correct ? 'bg-emerald-950/30 border-emerald-500/20' : 'bg-red-950/30 border-red-500/20'
          }`}>
            <span className={`font-bold mr-2 ${selected === correct ? 'text-emerald-400' : 'text-red-400'}`}>
              {selected === correct ? '✓ Correct!' : '✗ Incorrect.'}
            </span>
            <span className="text-[#C4C4C4]">{q.explanation}</span>
          </div>
        )}
        {answered && (
          <div className="flex justify-end pt-1">
            <button
              onClick={() => {
                const newAnswers = [...answers, selected === correct];
                setAnswers(newAnswers);
                if (qIdx + 1 >= total) setQuizDone(true);
                else { setQIdx(qIdx + 1); setSelected(null); setShowExp(false); }
              }}
              className="px-7 py-2.5 text-xs font-bold uppercase tracking-widest bg-[#7C3AED] hover:bg-[#6D28D9] text-white rounded-lg transition-all">
              {qIdx + 1 >= total ? 'See Results' : 'Next →'}
            </button>
          </div>
        )}
      </div>
    );
  };

  // ── Tabs ──────────────────────────────────────────────────────────────────
  const TABS = [
    { id: 'notes', label: 'Detailed Notes', loading: isLoadingNotes },
    { id: 'flashcards', label: 'Flashcards', loading: isLoadingFlashcards },
    { id: 'quiz', label: 'Quiz', loading: isLoadingQuiz },
  ];

  // ── Course Overview summary view (activeTopicIdx === -1) ───────────────────
  if (activeTopicIdx === -1) {
    if (isLoadingSummary) {
      return (
        <div className="flex-1 flex flex-col items-center justify-center p-16 gap-4 min-h-[500px]">
          <div className="w-8 h-8 border-2 border-[#7C3AED]/20 border-t-[#7C3AED] rounded-full animate-spin" />
          <p className="text-sm font-medium text-[#525252]">Generating course overview with MapReduce...</p>
        </div>
      );
    }

    if (!overallSummary) {
      return (
        <div className="flex-1 flex items-center justify-center p-12 min-h-[500px]">
          <p className="text-sm text-[#404040] italic">Select a topic to begin studying, or wait for course summary to compile.</p>
        </div>
      );
    }

    return (
      <div className="flex-1 p-7 space-y-7 overflow-y-auto select-text min-h-[500px] max-h-[640px] custom-scrollbar">
        {/* Title bar */}
        <div className="pb-4 border-b border-[#1a1a1a]">
          <h2 className="text-2xl font-bold text-[#F5F5F5] leading-tight">
            {overallSummary.title || "Course Overview"}
          </h2>
          <p className="text-[10px] text-[#7C3AED] mt-1.5 uppercase font-bold tracking-[0.2em]">
            Overall Course Summary · MapReduce Engine
          </p>
        </div>

        {/* Cohesive Summary Box */}
        <div className="p-5 rounded-xl border border-[#7C3AED]/20 bg-[#7C3AED]/05 space-y-3">
          <div className="flex items-center gap-2">
            <span>📌</span>
            <span className="text-[10px] font-bold uppercase tracking-widest text-[#C4B5FD]">
              Cohesive Course Overview
            </span>
          </div>
          <p className="text-sm text-[#D4D4D4] leading-relaxed">
            {overallSummary.cohesive_summary}
          </p>
        </div>

        {/* Key Takeaways */}
        {overallSummary.key_takeaways?.length > 0 && (
          <div className="rounded-xl border border-[#1e1e1e] bg-[#0c0c0c] p-5 space-y-4">
            <div className="flex items-center gap-2">
              <span>⚡</span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                Key Technical Takeaways
              </span>
            </div>
            <ul className="space-y-3">
              {overallSummary.key_takeaways.map((takeaway, i) => (
                <li key={i} className="flex items-start gap-3">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#7C3AED] shrink-0 mt-2" />
                  <span className="text-sm text-[#D4D4D4] leading-relaxed">{takeaway}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Course Roadmap */}
        {topics.length > 0 && (
          <div className="rounded-xl border border-[#1e1e1e] bg-[#0c0c0c] p-6 space-y-6">
            <div className="flex items-center gap-2">
              <span>🗺️</span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                Course Roadmap & Study Path
              </span>
            </div>
            
            <div className="relative pl-8 space-y-6">
              {/* Vertical timeline line with gradient */}
              <div className="absolute left-[15px] top-2 bottom-2 w-0.5 bg-gradient-to-b from-[#7C3AED] via-fuchsia-500 to-violet-600 opacity-60" />

              {topics.map((topic, idx) => {
                const status = videoId ? getTopicAccuracyStatus(videoId, idx) : 'unattempted';
                
                // Color mapping for nodes
                const statusColors = {
                  strong:      'bg-emerald-500 border-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.5)]',
                  medium:      'bg-amber-500 border-amber-400 shadow-[0_0_8px_rgba(245,158,11,0.5)]',
                  weak:        'bg-red-500 border-red-400 shadow-[0_0_8px_rgba(239,68,68,0.5)] animate-pulse',
                  unattempted: 'bg-[#1a1a1a] border-[#333] shadow-none',
                };
                const nodeClass = statusColors[status] || statusColors.unattempted;
                
                // Icon based on topic keywords
                let topicIcon = '📘';
                const lowerTitle = topic.title.toLowerCase();
                if (lowerTitle.includes('install') || lowerTitle.includes('setup') || lowerTitle.includes('config')) {
                  topicIcon = '🛠️';
                } else if (lowerTitle.includes('code') || lowerTitle.includes('program') || lowerTitle.includes('develop')) {
                  topicIcon = '💻';
                } else if (lowerTitle.includes('intro') || lowerTitle.includes('overview')) {
                  topicIcon = '🚀';
                } else if (lowerTitle.includes('concept') || lowerTitle.includes('theory') || lowerTitle.includes('what is')) {
                  topicIcon = '📌';
                } else if (lowerTitle.includes('database') || lowerTitle.includes('sql') || lowerTitle.includes('model')) {
                  topicIcon = '🗄️';
                } else if (lowerTitle.includes('api') || lowerTitle.includes('request') || lowerTitle.includes('rest')) {
                  topicIcon = '🔌';
                }

                return (
                  <div key={idx} className="relative flex items-start gap-4 group">
                    {/* Node circle */}
                    <div className={`absolute -left-[23px] top-1.5 w-3.5 h-3.5 rounded-full border-2 ${nodeClass} transition-transform duration-200 group-hover:scale-125 z-10`} />
                    
                    {/* Topic Card */}
                    <div 
                      onClick={() => onTopicClick && onTopicClick(idx)}
                      className="flex-1 rounded-xl bg-[#141414]/60 hover:bg-[#1a1a1a]/80 border border-[#1e1e1e] hover:border-[#7C3AED]/40 p-4 transition-all duration-200 cursor-pointer flex items-center justify-between shadow-md hover:shadow-[0_4px_20px_rgba(124,58,237,0.08)] group/card"
                    >
                      <div className="space-y-1.5 pr-4">
                        <div className="flex items-center gap-2">
                          <span className="text-base">{topicIcon}</span>
                          <span className="text-xs font-mono font-bold text-[#7C3AED] bg-[#7C3AED]/10 px-2 py-0.5 rounded">
                            Topic {String(idx + 1).padStart(2, '0')}
                          </span>
                        </div>
                        <h4 className="text-sm font-semibold text-[#E5E5E5] group-hover/card:text-[#F5F5F5] transition-colors">
                          {topic.title}
                        </h4>
                      </div>
                      
                      <div className="shrink-0 flex items-center gap-2.5">
                        {status === 'weak' && (
                          <span className="text-[9px] font-bold text-red-400 bg-red-500/10 border border-red-500/20 rounded px-1.5 py-0.5">
                            Needs Revision
                          </span>
                        )}
                        {status === 'strong' && (
                          <span className="text-[9px] font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded px-1.5 py-0.5">
                            Mastered
                          </span>
                        )}
                        <span className="text-xs text-[#404040] group-hover/card:text-[#7C3AED] group-hover/card:translate-x-0.5 transition-all">
                          Study →
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-[500px]">
      {/* Tab bar */}
      <div className="flex items-center border-b border-[#1a1a1a] px-3 py-2 gap-0.5 overflow-x-auto select-none">
        {TABS.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            className={`relative px-4 py-2 text-[11px] font-semibold rounded-md transition-all whitespace-nowrap ${
              activeTab === tab.id
                ? 'bg-[#1a1a1a] text-[#F5F5F5] border border-[#2a2a2a]'
                : 'text-[#404040] hover:text-[#A3A3A3] border border-transparent'
            }`}>
            {tab.label}
            {tab.loading && (
              <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-[#7C3AED] animate-pulse" />
            )}
          </button>
        ))}
      </div>

      {/* Content pane */}
      <div className="flex-1 overflow-y-auto" style={{ maxHeight: '640px' }}>
        {activeTab === 'notes' && renderNotes()}
        {activeTab === 'flashcards' && renderFlashcards()}
        {activeTab === 'quiz' && renderQuiz()}
      </div>
    </div>
  );
}

// ── Section component ─────────────────────────────────────────────────────────

const COLOR_MAP = {
  violet: { bg: 'bg-violet-500/05', border: 'border-violet-500/15', label: 'text-violet-400' },
  amber:  { bg: 'bg-amber-500/05',  border: 'border-amber-500/15',  label: 'text-amber-400'  },
  cyan:   { bg: 'bg-cyan-500/05',   border: 'border-cyan-500/15',   label: 'text-cyan-400'   },
  emerald:{ bg: 'bg-emerald-500/05',border: 'border-emerald-500/15',label: 'text-emerald-400'},
  rose:   { bg: 'bg-rose-500/05',   border: 'border-rose-500/15',   label: 'text-rose-400'   },
  slate:  { bg: 'bg-slate-500/05',  border: 'border-slate-500/15',  label: 'text-slate-400'  },
};

function Section({ icon, label, color = 'violet', children }) {
  const c = COLOR_MAP[color] || COLOR_MAP.violet;
  return (
    <div className={`rounded-xl border ${c.bg} ${c.border} p-5 space-y-3`}>
      <div className="flex items-center gap-2">
        <span>{icon}</span>
        <span className={`text-[10px] font-bold uppercase tracking-widest ${c.label}`}>{label}</span>
      </div>
      {children}
    </div>
  );
}

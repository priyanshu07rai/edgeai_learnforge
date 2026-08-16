import React, { useState, useEffect } from 'react';
import { saveQuizResult, markTopicViewed, recordFlashcardReview, getTopicAccuracyStatus } from '../utils/progress';
import { fetchGraphForTopic } from '../services/api';

// Real code syntax detector — same logic as backend sanitizer
const _REAL_CODE_RE = /(?:^|\n)[ \t]*(?:def \w+\s*\(|class \w+[:(]|import \w|from \w+ import|const |let |var |function\s+\w+\s*\(|=>|\w+\(\)|return |elif |else:|except:|lambda |yield |async def|await |#include|\$\s*\w+|pip install|npm install|git |docker |curl |wget)/m;

const sanitizeMdCodeFences = (md) => {
  if (!md) return md;
  // Strip code blocks that contain no real code syntax
  return md.replace(/```([a-zA-Z]*)\n?([\s\S]*?)```/g, (match, lang, content) => {
    const stripped = content.trim();
    if (!stripped) return ''; // remove empty blocks
    const hasRealCode = _REAL_CODE_RE.test(stripped);
    const lines = stripped.split('\n').filter(l => l.trim());
    if (hasRealCode || (lines.length >= 2 && stripped.length > 80)) {
      return match; // keep real code blocks as-is
    }
    // Prose misidentified as code — convert to bullet point
    return `- ${lines.join(' ')}`;
  });
};

const parseMarkdown = (markdown) => {
  if (!markdown) return '';

  // Pre-sanitize: remove false-positive code fences before HTML conversion
  let md = sanitizeMdCodeFences(markdown);

  // Remove H1 title header at the very start to avoid duplication
  let html = md.replace(/^#\s+.*$/m, '').trim();

  // Escape HTML entities
  html = html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // ── Headers ────────────────────────────────────────────────────────────────
  // ── Headers ────────────────────────────────────────────────────────────────
  // H3 → styled section heading with left accent bar
  html = html.replace(/^###\s+(.*$)/gim,
    '<h4 class="md-h3" data-heading="$1">'
    + '<span style="display:inline-block;width:4px;height:18px;background:linear-gradient(to bottom,#4f46e5,#9333ea);border-radius:2px;flex-shrink:0;"></span>$1</h4>'
  );
  // H2 → bold section break
  html = html.replace(/^##\s+(.*$)/gim,
    '<h3 class="md-h2">$1</h3>'
  );
  // H1 → large title
  html = html.replace(/^#\s+(.*$)/gim,
    '<h2 class="md-h2" style="font-size:1.25rem;">$1</h2>'
  );

  // ── Inline formatting ──────────────────────────────────────────────────────
  // Bold
  html = html.replace(/\*\*(.*?)\*\*/g,
    '<strong class="md-strong">$1</strong>'
  );
  // Italic
  html = html.replace(/\*(.*?)\*/g,
    '<em style="font-style:italic;opacity:0.85;">$1</em>'
  );
  // Inline code
  html = html.replace(/`(.*?)`/g,
    '<code class="md-code">$1</code>'
  );

  // ── Code blocks ────────────────────────────────────────────────────────────
  // Fenced code block with language tag
  html = html.replace(/```([a-zA-Z]*)\n([\s\S]*?)```/g, (match, lang, codeContent) => {
    const langLabel = lang
      ? `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 14px;background:rgba(0,0,0,0.05);border-bottom:1px solid rgba(0,0,0,0.1);"><span style="font-size:0.68rem;font-family:monospace;font-weight:700;color:#6366f1;text-transform:uppercase;letter-spacing:0.1em;">${lang}</span><span style="font-size:0.65rem;font-family:monospace;opacity:0.6;">code</span></div>`
      : '';
    return `<div style="margin:16px 0;border-radius:10px;overflow:hidden;border:1px solid rgba(100,116,139,0.2);" class="bg-slate-900 text-slate-100 dark:bg-slate-950">${langLabel}<pre style="padding:14px 16px;overflow-x:auto;margin:0;"><code style="font-family:'JetBrains Mono',Consolas,monospace;font-size:0.8rem;white-space:pre;">${codeContent.trimEnd()}</code></pre></div>`;
  });
  // Fallback code block (no language tag)
  html = html.replace(/```([\s\S]*?)```/g, (match, codeContent) => {
    return `<div style="margin:16px 0;border-radius:10px;overflow:hidden;border:1px solid rgba(100,116,139,0.2);" class="bg-slate-900 text-slate-100 dark:bg-slate-950"><pre style="padding:14px 16px;overflow-x:auto;margin:0;"><code style="font-family:'JetBrains Mono',Consolas,monospace;font-size:0.8rem;white-space:pre;">${codeContent.trimEnd()}</code></pre></div>`;
  });

  // ── Horizontal Rule ────────────────────────────────────────────────────────
  html = html.replace(/^---\s*$/gim,
    '<hr style="margin:24px 0;border:none;border-top:1px solid rgba(100,116,139,0.2);" />'
  );

  // ── List items ─────────────────────────────────────────────────────────────
  // Nested bullets (indented)
  html = html.replace(/^(?: {2,}|\t)[*-]\s+(.*$)/gim,
    '<li class="md-li _nested_li" style="margin-left:20px;"><span style="width:5px;height:5px;border-radius:50%;background:#6366f1;flex-shrink:0;margin-top:7px;"></span><span>$1</span></li>'
  );
  // Top-level bullets (asterisk)
  html = html.replace(/^[*]\s+(.*$)/gim,
    '<li class="md-li _top_li"><span style="width:6px;height:6px;border-radius:50%;background:#4f46e5;flex-shrink:0;margin-top:8px;"></span><span>$1</span></li>'
  );
  // Top-level bullets (dash)
  html = html.replace(/^-\s+(.*$)/gim,
    '<li class="md-li _top_li"><span style="width:6px;height:6px;border-radius:50%;background:#4f46e5;flex-shrink:0;margin-top:8px;"></span><span>$1</span></li>'
  );
  // Ordered list items
  let olCounter = 0;
  html = html.replace(/^(\d+)\.\s+(.*$)/gim, (match, num, content) => {
    return `<li class="md-li"><span style="min-width:22px;height:22px;border-radius:50%;background:rgba(99,102,241,0.12);border:1px solid rgba(99,102,241,0.3);display:flex;align-items:center;justify-content:center;font-size:0.7rem;font-weight:800;color:#4f46e5;flex-shrink:0;">${num}</span><span>${content}</span></li>`;
  });

  // ── Table parsing ──────────────────────────────────────────────────────────
  const parseTableRows = (rows) => {
    let hasHeader = false;
    let headerCols = [];
    const bodyRows = [];
    if (rows.length > 1 && rows[1].includes('-')) {
      hasHeader = true;
      headerCols = rows[0].split('|').map(s => s.trim()).filter((s, idx) => idx > 0 && idx < rows[0].split('|').length - 1);
      for (let r = 2; r < rows.length; r++) {
        const cols = rows[r].split('|').map(s => s.trim()).filter((s, idx) => idx > 0 && idx < rows[r].split('|').length - 1);
        if (cols.length > 0) bodyRows.push(cols);
      }
    } else {
      for (let r = 0; r < rows.length; r++) {
        const cols = rows[r].split('|').map(s => s.trim()).filter((s, idx) => idx > 0 && idx < rows[r].split('|').length - 1);
        if (cols.length > 0) bodyRows.push(cols);
      }
    }
    let t = '<div style="overflow-x:auto;margin:16px 0;border:1px solid rgba(100,116,139,0.2);border-radius:10px;"><table style="min-width:100%;border-collapse:collapse;font-size:0.84rem;">';
    if (hasHeader && headerCols.length > 0) {
      t += '<thead class="bg-indigo-50 dark:bg-slate-900"><tr>';
      headerCols.forEach(col => { t += `<th style="padding:10px 14px;text-align:left;font-weight:700;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.05em;border-bottom:1px solid rgba(100,116,139,0.2);">${col}</th>`; });
      t += '</tr></thead>';
    }
    t += '<tbody>';
    bodyRows.forEach((row, ri) => {
      t += `<tr class="${ri % 2 === 0 ? 'bg-white dark:bg-slate-900/60' : 'bg-slate-50 dark:bg-slate-900/30'}">`;
      row.forEach(col => { t += `<td style="padding:9px 14px;border-bottom:1px solid rgba(100,116,139,0.15);">${col}</td>`; });
      t += '</tr>';
    });
    t += '</tbody></table></div>';
    return t;
  };

  const lines = html.split('\n');
  let inTable = false;
  let tableRows = [];
  const parsedLines = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('|') && line.endsWith('|')) {
      if (!inTable) { inTable = true; tableRows = []; }
      tableRows.push(line);
    } else {
      if (inTable) { parsedLines.push(parseTableRows(tableRows)); inTable = false; }
      parsedLines.push(lines[i]);
    }
  }
  if (inTable) parsedLines.push(parseTableRows(tableRows));
  html = parsedLines.join('\n');

  // ── Paragraph wrapping ─────────────────────────────────────────────────────
  let currentHeadingLower = '';
  const finalLines = html.split('\n');
  const processed = finalLines.map(line => {
    const trimmed = line.trim();
    if (!trimmed) return '';

    const headingMatch = trimmed.match(/data-heading="([^"]+)"/);
    if (headingMatch) {
      currentHeadingLower = headingMatch[1].toLowerCase();
    }

    if (trimmed.startsWith('<h') || trimmed.startsWith('<li') || trimmed.startsWith('<pre') ||
        trimmed.startsWith('<code') || trimmed.startsWith('</pre') || trimmed.startsWith('</code') ||
        trimmed.startsWith('<hr') || trimmed.startsWith('<table') || trimmed.startsWith('<thead') ||
        trimmed.startsWith('<tbody') || trimmed.startsWith('<tr') || trimmed.startsWith('<td') ||
        trimmed.startsWith('<th') || trimmed.startsWith('<div') || trimmed.startsWith('</div') ||
        trimmed.startsWith('</table>') || trimmed.startsWith('</tr>') || trimmed.startsWith('</td>') ||
        trimmed.startsWith('</th>') || trimmed.startsWith('</tbody>') || trimmed.startsWith('</thead>')) {
      return line;
    }

    // Section-aware callout cards
    const isWarning   = /warning|mistake|pitfall|avoid|caution|error|don.?t/i.test(currentHeadingLower);
    const isAnalogy   = /analogy|imagine|think of|real.world|like a/i.test(currentHeadingLower);
    const isExample   = /example|use case|demo|illustrat/i.test(currentHeadingLower);
    const isTakeaway  = /takeaway|best practice|key point|remember/i.test(currentHeadingLower);
    const isQuestion  = /concept check|review|interview|question/i.test(currentHeadingLower);

    if (isWarning) {
      return `<div class="callout-card callout-warning">⚠️ <span>${trimmed}</span></div>`;
    }
    if (isAnalogy) {
      return `<div class="callout-card callout-analogy">💡 <span>${trimmed}</span></div>`;
    }
    if (isExample) {
      return `<div class="callout-card callout-example">🧪 <span>${trimmed}</span></div>`;
    }
    if (isTakeaway) {
      return `<div class="callout-card callout-takeaway">⚡ <span>${trimmed}</span></div>`;
    }
    if (isQuestion) {
      return `<div class="callout-card callout-question">💬 <span>${trimmed}</span></div>`;
    }

    // Regular paragraph
    return `<p class="md-p">${line}</p>`;
  });


  let result = processed.filter(Boolean).join('\n');

  // Final cleanup: remove empty pre blocks
  result = result.replace(/<pre[^>]*>\s*(?:<span[^>]*>[^<]*<\/span>)?\s*<code>\s*<\/code>\s*<\/pre>/g, '');

  return result;
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
  transcriptData,
  onPlayVideo,
}) {
  const [cardIdx, setCardIdx] = useState(0);
  const [showAnswer, setShowAnswer] = useState(false);
  const [qIdx, setQIdx] = useState(0);
  const [selected, setSelected] = useState(null);
  const [showExp, setShowExp] = useState(false);
  const [answers, setAnswers] = useState([]);
  const [quizDone, setQuizDone] = useState(false);

  const [graphData, setGraphData] = useState(null);
  const [isLoadingGraph, setIsLoadingGraph] = useState(false);
  const [graphError, setGraphError] = useState(null);

  useEffect(() => { setCardIdx(0); setShowAnswer(false); resetQuiz(); setGraphData(null); }, [activeTopicIdx]);
  useEffect(() => { if (activeTab === 'quiz') resetQuiz(); }, [activeTab]);
  useEffect(() => {
    if (activeTab === 'notes' && videoId && topics[activeTopicIdx]) {
      markTopicViewed(videoId, activeTopicIdx);
    }
  }, [activeTab, activeTopicIdx, videoId, topics]);

  useEffect(() => {
    if (activeTab === 'graph' && videoId && activeTopicIdx >= 0 && !graphData && !isLoadingGraph && !graphError) {
      const fetchGraph = async () => {
        setIsLoadingGraph(true);
        setGraphError(null);
        try {
          const data = await fetchGraphForTopic(videoId, activeTopicIdx);
          setGraphData(data);
        } catch (e) {
          if (e.response && e.response.status === 404) {
            setGraphError('Knowledge Graph generation failed or is still processing. Please try again later.');
          } else {
            setGraphError('Failed to load Knowledge Graph.');
          }
        } finally {
          setIsLoadingGraph(false);
        }
      };
      fetchGraph();
    }
  }, [activeTab, videoId, activeTopicIdx, graphData, isLoadingGraph, graphError]);

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
        <div className="select-text overflow-y-auto">
          {/* Topic header */}
          <div className="px-8 pt-7 pb-5 border-b border-slate-200 dark:border-[#13131f]">
            <div className="flex items-center gap-2.5 mb-2">
              <span className="text-[10px] font-extrabold uppercase tracking-widest text-indigo-700 dark:text-[#7c3aed] bg-indigo-100 dark:bg-[#7c3aed18] px-2.5 py-1 rounded-full border border-indigo-300 dark:border-[#7c3aed30]">Study Guide</span>
              {note.density_badge && (
                <span className="text-[11px] text-slate-500 dark:text-[#525270] font-semibold">{note.density_badge}</span>
              )}
            </div>
            <h2 className="text-2xl font-extrabold text-slate-900 dark:text-[#f1f1f8] leading-tight m-0">{note.topic}</h2>
            {summary && (
              <p className="text-sm text-slate-700 dark:text-[#8888a8] leading-relaxed mt-2.5 max-w-2xl font-semibold">{summary}</p>
            )}
          </div>

          {/* Markdown body */}
          <div
            className="px-8 py-7 max-w-3xl"
            dangerouslySetInnerHTML={{ __html: parseMarkdown(markdown) }}
          />

          {/* Key Terms pill bar */}
          {important_terms.length > 0 && (
            <div className="px-8 pt-4 pb-7 border-t border-slate-200 dark:border-[#13131f]">
              <div className="flex items-center gap-2 mb-2.5">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-[#525270]">Key Terms</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {important_terms.map((t, i) => (
                  <span key={i} className="px-3 py-1 text-xs font-bold text-indigo-900 dark:text-[#a78bfa] bg-indigo-100 dark:bg-[#7c3aed12] border border-indigo-300 dark:border-[#7c3aed25] rounded-full cursor-default">{t}</span>
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
        <div className="relative w-full h-[320px] perspective-1000 group cursor-pointer" onClick={() => setShowAnswer(a => !a)}>
          <div className={`relative w-full h-full transition-all duration-500 preserve-3d ${showAnswer ? 'rotate-y-180' : ''}`}>
            
            {/* Front: Question */}
            <div className="absolute inset-0 w-full h-full backface-hidden bg-white dark:bg-[#0c0c14] border-2 border-slate-300 dark:border-[#2a2a3e] rounded-2xl flex flex-col p-8 hover:border-indigo-500 transition-all shadow-xl shadow-slate-200/50 dark:shadow-lg">
              
              <div className="flex justify-between items-start mb-6">
                <span className="text-[10px] font-extrabold text-slate-700 dark:text-[#525270] uppercase tracking-widest bg-slate-100 dark:bg-[#13131f] px-3 py-1 rounded-full border border-slate-300 dark:border-transparent">
                  Question
                </span>
                {card.type && (
                  <span className={`text-[10px] font-extrabold uppercase tracking-widest px-3 py-1 rounded-full border ${
                    card.type === 'conceptual' ? 'text-violet-700 dark:text-violet-400 bg-violet-100 dark:bg-violet-400/10 border-violet-300 dark:border-violet-400/20' :
                    card.type === 'application' ? 'text-emerald-700 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-400/10 border-emerald-300 dark:border-emerald-400/20' :
                    card.type === 'misconception' ? 'text-rose-700 dark:text-rose-400 bg-rose-100 dark:bg-rose-400/10 border-rose-300 dark:border-rose-400/20' :
                    'text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-400/10 border-amber-300 dark:border-amber-400/20'
                  }`}>
                    {card.type}
                  </span>
                )}
              </div>
              
              <div className="flex-1 flex items-center justify-center">
                <p className="text-center text-lg md:text-xl font-extrabold text-slate-900 dark:text-[#f1f1f8] leading-relaxed max-w-lg">
                  {card.question}
                </p>
              </div>

              {card.hint && (
                <div className="mt-6 flex items-start gap-3 bg-slate-50 dark:bg-[#13131f] border border-slate-300 dark:border-[#2a2a3e] p-3 rounded-xl">
                  <span className="text-amber-500 text-sm">💡</span>
                  <p className="text-xs text-slate-700 dark:text-[#94a3b8] font-medium italic mt-0.5">{card.hint}</p>
                </div>
              )}
              
              <div className="absolute bottom-4 left-0 w-full text-center">
                <p className="text-[10px] text-slate-500 dark:text-[#525270] font-bold tracking-wider">Tap to reveal answer</p>
              </div>
            </div>

            {/* Back: Answer */}
            <div className="absolute inset-0 w-full h-full backface-hidden rotate-y-180 bg-indigo-50/90 dark:bg-[#120a1f] border-2 border-indigo-300 dark:border-[#7c3aed40] rounded-2xl flex flex-col p-8 shadow-xl">
              
              <div className="flex justify-between items-start mb-6">
                <span className="text-[10px] font-extrabold text-indigo-900 dark:text-[#a78bfa] uppercase tracking-widest bg-indigo-200 dark:bg-[#7c3aed20] px-3 py-1 rounded-full">
                  Answer
                </span>
              </div>
              
              <div className="flex-1 flex flex-col items-center justify-center gap-4 overflow-y-auto pr-2 custom-scrollbar">
                <p className="text-center text-sm md:text-base text-slate-900 dark:text-[#d4d4d8] font-bold leading-relaxed max-w-lg">
                  {card.answer}
                </p>
              </div>
              
              <div className="absolute bottom-4 left-0 w-full text-center">
                <p className="text-[10px] text-indigo-700 dark:text-[#a78bfa] font-bold tracking-wider opacity-80">Tap to see question</p>
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-between gap-3 pt-2">
          <button
            onClick={() => { if (cardIdx > 0) { setCardIdx(cardIdx - 1); setShowAnswer(false); } }}
            disabled={cardIdx === 0}
            className="px-6 py-2.5 text-xs font-bold uppercase tracking-widest border border-slate-300 dark:border-[#2a2a3e] rounded-xl text-slate-700 dark:text-[#94a3b8] bg-white dark:bg-transparent hover:bg-slate-100 dark:hover:bg-[#13131f] hover:text-slate-900 dark:hover:text-[#f8fafc] disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-sm"
          >← Previous</button>
          <button
            onClick={() => { if (cardIdx < cards.length - 1) { setCardIdx(cardIdx + 1); setShowAnswer(false); } }}
            disabled={cardIdx === cards.length - 1}
            className="px-6 py-2.5 text-xs font-bold uppercase tracking-widest bg-indigo-600 hover:bg-indigo-700 dark:bg-[#7C3AED] dark:hover:bg-[#6D28D9] text-white rounded-xl disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-md"
          >Next →</button>
        </div>
      </div>
    );
  };

  // ── QUIZ ──────────────────────────────────────────────────────────────────
  const renderQuiz = () => {
    if (isLoadingQuiz) return <Spinner msg="Building assessment quiz…" />;
    const quizObj = quiz[activeTopicIdx];
    const questions = quizObj?.quiz ?? quizObj?.questions ?? (Array.isArray(quizObj) ? quizObj : []);
    if (!questions.length) return <Empty msg="Quiz loading…" />;

    const total = questions.length;

    if (quizFinished) {
      let correct = 0;
      questions.forEach((q, i) => {
        if (answers[i] === q.correct_answer) correct++;
      });
      const pct = Math.round((correct / total) * 100);
      
      const [col, bg, label, icon] = pct >= 80
        ? ['text-emerald-700 dark:text-emerald-400', 'bg-emerald-100 dark:bg-emerald-500/10', 'Excellent Mastery', '🏆']
        : pct >= 60
        ? ['text-amber-700 dark:text-amber-400', 'bg-amber-100 dark:bg-amber-500/10', 'Good Understanding', '👍']
        : ['text-rose-700 dark:text-rose-400', 'bg-rose-100 dark:bg-rose-500/10', 'Needs Review', '⚠️'];

      return (
        <div className="flex-1 flex flex-col items-center justify-center p-12 select-text">
          <div className="flex flex-col items-center justify-center bg-white dark:bg-[#0c0c14] border-2 border-slate-300 dark:border-[#2a2a3e] rounded-2xl p-10 shadow-2xl w-full max-w-md">
            <span className="text-5xl mb-4">{icon}</span>
            <p className={`text-6xl font-black tracking-tight mb-2 ${col}`}>{pct}%</p>
            <p className="text-sm text-slate-600 dark:text-[#94a3b8] font-bold tracking-wide uppercase mb-6">{correct} out of {total} correct</p>
            
            <div className={`px-5 py-2 rounded-full border border-current/20 ${bg} ${col} mb-8`}>
              <span className="text-xs font-extrabold uppercase tracking-widest">{label}</span>
            </div>
            
            <button onClick={resetQuiz}
              className="w-full py-3.5 text-xs font-extrabold uppercase tracking-widest bg-indigo-600 hover:bg-indigo-700 dark:bg-white text-white dark:text-black hover:shadow-xl rounded-xl transition-all shadow-lg">
              Retry Assessment
            </button>
          </div>
        </div>
      );
    }

    const q = questions[qIdx];
    const answered = selected !== null;
    const correct = q?.correct_answer;

    const optStyle = (letter) => {
      if (!answered) return 'border-2 border-slate-300 dark:border-[#2a2a3e] bg-white dark:bg-[#13131f] text-slate-900 dark:text-[#d4d4d8] font-bold hover:border-indigo-500 hover:bg-indigo-50/50 dark:hover:bg-[#7c3aed10] shadow-sm cursor-pointer';
      if (letter === correct) return 'border-2 border-emerald-500 bg-emerald-100 dark:bg-emerald-500/10 text-emerald-900 dark:text-emerald-300 font-extrabold shadow-md';
      if (letter === selected) return 'border-2 border-rose-500 bg-rose-100 dark:bg-rose-500/10 text-rose-900 dark:text-rose-300 font-extrabold shadow-md';
      return 'border border-slate-200 dark:border-[#1a1a2a] bg-slate-100 dark:bg-[#0c0c14] text-slate-400 dark:text-[#525270] opacity-50';
    };

    return (
      <div className="p-7 space-y-6 max-w-3xl select-text">
        
        {/* Header & Progress */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-[10px] font-extrabold text-indigo-700 dark:text-[#7c3aed] uppercase tracking-widest bg-indigo-100 dark:bg-[#7c3aed15] px-3 py-1 rounded-full border border-indigo-300 dark:border-[#7c3aed30]">
              Assessment
            </span>
            <span className="text-sm font-bold text-slate-900 dark:text-[#a78bfa]">{topicTitle}</span>
          </div>
          <span className="text-xs font-mono font-bold text-slate-700 dark:text-[#525270] bg-slate-200 dark:bg-[#13131f] px-3 py-1 rounded-lg">
            {qIdx + 1} / {total}
          </span>
        </div>

        <div className="w-full h-1.5 bg-slate-200 dark:bg-[#13131f] rounded-full overflow-hidden">
          <div className="h-full bg-gradient-to-r from-sky-600 to-indigo-600 dark:from-[#7c3aed] dark:to-[#a855f7] transition-all duration-500 ease-out"
            style={{ width: `${(qIdx / total) * 100}%` }} />
        </div>

        {/* Question */}
        <div className="pt-4 pb-2">
          <h3 className="text-lg md:text-xl font-bold text-[#f8fafc] leading-relaxed">
            {q?.question}
          </h3>
        </div>

        {/* Options */}
        <div className="space-y-3">
          {q?.options?.map((opt, i) => {
            const letter = ['A', 'B', 'C', 'D'][i];
            
            // Clean up the letter prefix from the text if present
            const optText = opt.startsWith(`${letter})`) ? opt.substring(2).trim() : opt;
            
            return (
              <button key={i}
                onClick={() => { if (!answered) { setSelected(letter); setShowExp(true); } }}
                disabled={answered}
                className={`w-full flex items-center gap-4 text-left px-5 py-4 rounded-xl border transition-all duration-200 ${optStyle(letter)}`}>
                
                <span className={`shrink-0 flex items-center justify-center w-8 h-8 rounded-lg text-xs font-bold border
                  ${answered && letter === correct ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400' : 
                    answered && letter === selected ? 'bg-rose-500/20 border-rose-500/40 text-rose-400' :
                    'bg-[#1e1e2e] border-[#2a2a3e] text-[#94a3b8]'}`}>
                  {letter}
                </span>
                <span className="text-sm leading-relaxed">{optText}</span>
              </button>
            );
          })}
        </div>

        {/* Explanation Reveal */}
        <div className={`transition-all duration-500 overflow-hidden ${showExp ? 'max-h-[500px] opacity-100 mt-6' : 'max-h-0 opacity-0 mt-0'}`}>
          {showExp && q?.explanation && (
            <div className={`p-5 rounded-xl border flex gap-4 items-start ${
              selected === correct 
                ? 'bg-[#061810] border-emerald-500/30' 
                : 'bg-[#18060a] border-rose-500/30'
            }`}>
              <div className={`shrink-0 flex items-center justify-center w-8 h-8 rounded-full ${
                selected === correct ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
              }`}>
                {selected === correct ? '✓' : '✗'}
              </div>
              <div className="space-y-1">
                <p className={`text-sm font-bold tracking-wide ${
                  selected === correct ? 'text-emerald-400' : 'text-rose-400'
                }`}>
                  {selected === correct ? 'Correct!' : 'Incorrect'}
                </p>
                <p className="text-sm text-[#cbd5e1] leading-relaxed">
                  {q.explanation}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className={`flex justify-end pt-4 transition-all duration-300 ${answered ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}>
          <button
            onClick={() => {
              const newAnswers = [...answers, selected === correct];
              setAnswers(newAnswers);
              if (qIdx + 1 >= total) setQuizDone(true);
              else { setQIdx(qIdx + 1); setSelected(null); setShowExp(false); }
            }}
            className="px-8 py-3 text-xs font-bold uppercase tracking-widest bg-white text-black hover:bg-gray-200 rounded-xl shadow-lg transition-all">
            {qIdx + 1 >= total ? 'View Assessment Results' : 'Next Question →'}
          </button>
        </div>
      </div>
    );
  };


  // ── GRAPH ─────────────────────────────────────────────────────────────────
  const [graphTab, setGraphTab] = useState('tree'); // 'tree' | 'flowchart'

  const renderGraph = () => {
    if (isLoadingGraph) return <Spinner msg="Loading Knowledge Graph..." />;
    if (graphError) return (
      <div className="flex flex-col items-center justify-center gap-5 p-16 min-h-[300px]">
        <div className="text-4xl">🔄</div>
        <p className="text-sm text-center text-[#737373] max-w-xs leading-relaxed">{graphError}</p>
        <button
          onClick={() => { setGraphError(null); setGraphData(null); }}
          className="px-5 py-2 text-xs font-semibold text-[#a78bfa] border border-[#7c3aed]/40 rounded-lg bg-[#7c3aed]/10 hover:bg-[#7c3aed]/20 transition-all"
        >
          Retry
        </button>
      </div>
    );
    if (!graphData) return <Empty msg="No graph data available." />;

    // Non-structural topics get a simple info view
    if (!graphData.is_structural) return (
      <div className="flex flex-col items-center justify-center gap-4 p-12 min-h-[300px] text-center">
        <div className="text-4xl">📋</div>
        <p className="text-base font-semibold text-[#e5e5e5]">{graphData.main_topic}</p>
        <p className="text-sm text-[#737373] max-w-sm leading-relaxed">
          {graphData.explanation || 'This topic contains introductory or conversational content that does not form a structured knowledge hierarchy.'}
        </p>
      </div>
    );

    const { main_topic, subtopics = [], examples = [], key_takeaways = [], related_topics = [], flowchart_steps = [], explanation = '', topic_type } = graphData;

    const typeColor = {
      algorithm: '#10b981',
      workflow: '#60a5fa',
      procedure: '#f59e0b',
      system: '#a78bfa',
      concept: '#7c3aed',
      general: '#64748b',
    }[topic_type] || '#7c3aed';

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0px', minHeight: '600px' }}>

        {/* ── Header ── */}
        <div style={{ padding: '20px 24px 14px', borderBottom: '1px solid #1a1a2e' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
            <span style={{ fontSize: '1.2rem' }}>🔀</span>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#f8fafc', margin: 0 }}>Strict Knowledge Graph</h2>
          </div>
          <p style={{ fontSize: '0.72rem', color: '#525270', margin: 0 }}>
            AI-generated visual representation of key concepts and their relationships
          </p>

          {/* Sub-tabs */}
          <div style={{ display: 'flex', gap: '8px', marginTop: '14px' }}>
            {[['tree', '🌳', 'Concept Tree'], ['flowchart', '🔀', 'Flowchart']].map(([id, icon, label]) => (
              <button key={id} onClick={() => setGraphTab(id)} style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                padding: '5px 14px', borderRadius: '8px', fontSize: '0.72rem', fontWeight: 600,
                cursor: 'pointer', border: 'none', transition: 'all 0.2s',
                background: graphTab === id ? `${typeColor}22` : 'transparent',
                color: graphTab === id ? typeColor : '#525270',
                outline: graphTab === id ? `1px solid ${typeColor}55` : '1px solid transparent',
              }}>
                {icon} {label}
              </button>
            ))}

            {/* Legend */}
            <div style={{ marginLeft: 'auto', display: 'flex', gap: '14px', alignItems: 'center' }}>
              {[['#7c3aed', 'Main Concept'], ['#3b82f6', 'Sub-Concept'], ['#10b981', 'Key Detail']].map(([clr, lbl]) => (
                <div key={lbl} style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                  <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: clr }} />
                  <span style={{ fontSize: '0.65rem', color: '#525270' }}>{lbl}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── Main content: left tree/flow + right sidebar ── */}
        <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

          {/* ── LEFT: Tree or Flowchart ── */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '24px 20px', minWidth: 0 }}>

            {graphTab === 'tree' && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0px' }}>

                {/* Root node */}
                <div style={{
                  padding: '16px 24px', borderRadius: '14px', textAlign: 'center',
                  background: 'linear-gradient(135deg, #13131f, #1a1030)',
                  border: `2px solid ${typeColor}`,
                  boxShadow: `0 0 20px ${typeColor}30`,
                  maxWidth: '280px', width: '100%',
                }}>
                  <div style={{ fontSize: '1.5rem', marginBottom: '6px' }}>🎓</div>
                  <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#f8fafc', lineHeight: 1.3 }}>{main_topic}</div>
                  {topic_type && (
                    <div style={{ marginTop: '6px', display: 'inline-block', fontSize: '0.6rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', padding: '2px 8px', borderRadius: '999px', background: `${typeColor}22`, color: typeColor }}>
                      {topic_type}
                    </div>
                  )}
                </div>

                {/* Connector line down */}
                {subtopics.length > 0 && (
                  <div style={{ width: '2px', height: '24px', background: `linear-gradient(to bottom, ${typeColor}, #1e293b)` }} />
                )}

                {/* Horizontal bar above subtopics */}
                {subtopics.length > 1 && (
                  <div style={{ width: '80%', maxWidth: '600px', height: '2px', background: '#1e293b', position: 'relative' }}>
                    <div style={{ position: 'absolute', top: 0, left: '50%', transform: 'translateX(-50%)', width: '30%', height: '2px', background: `${typeColor}60` }} />
                  </div>
                )}

                {/* Subtopic cards row */}
                {subtopics.length > 0 && (
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: `repeat(${Math.min(subtopics.length, 3)}, minmax(0, 1fr))`,
                    gap: '12px', width: '100%', marginTop: '8px',
                  }}>
                    {subtopics.map((st, idx) => (
                      <div key={idx} style={{
                        padding: '14px', borderRadius: '12px',
                        background: '#0f0f1a',
                        border: '1px solid #2a2a3e',
                        transition: 'border-color 0.2s, box-shadow 0.2s',
                        cursor: 'default',
                      }}
                        onMouseEnter={e => { e.currentTarget.style.borderColor = `${typeColor}60`; e.currentTarget.style.boxShadow = `0 4px 20px ${typeColor}15`; }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor = '#2a2a3e'; e.currentTarget.style.boxShadow = 'none'; }}
                      >
                        {/* Number badge + icon */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                          <div style={{
                            width: '22px', height: '22px', borderRadius: '50%', fontSize: '0.65rem', fontWeight: 700,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            background: `${typeColor}22`, color: typeColor, border: `1px solid ${typeColor}55`,
                          }}>{idx + 1}</div>
                          <span style={{ fontSize: '1rem' }}>{st.icon || '🔵'}</span>
                        </div>

                        {/* Title */}
                        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#e2e8f0', marginBottom: '5px', lineHeight: 1.3 }}>
                          {idx + 1}. {st.title}
                        </div>

                        {/* Description */}
                        {st.description && (
                          <p style={{ fontSize: '0.7rem', color: '#94a3b8', lineHeight: 1.55, margin: '0 0 6px', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                            {st.description}
                          </p>
                        )}

                        {/* Items list */}
                        {st.items?.length > 0 && (
                          <ul style={{ margin: '6px 0 0', padding: 0, listStyle: 'none' }}>
                            {st.items.slice(0, 4).map((item, i) => (
                              <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '5px', marginBottom: '3px' }}>
                                <span style={{ color: '#10b981', fontSize: '0.6rem', marginTop: '4px', flexShrink: 0 }}>●</span>
                                <span style={{ fontSize: '0.68rem', color: '#94a3b8', lineHeight: 1.4 }}>{item}</span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {subtopics.length === 0 && (
                  <div style={{ padding: '24px', textAlign: 'center', color: '#525270', fontSize: '0.8rem' }}>
                    No sub-concepts extracted for this topic.
                  </div>
                )}
              </div>
            )}

            {graphTab === 'flowchart' && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0px', maxWidth: '480px', margin: '0 auto' }}>
                {flowchart_steps.length > 0 ? flowchart_steps.map((step, idx) => (
                  <div key={idx} style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                    <div style={{
                      width: '100%', padding: '12px 18px', borderRadius: '10px', textAlign: 'center',
                      background: idx === 0 ? `${typeColor}22` : '#0f0f1a',
                      border: `1px solid ${idx === 0 ? typeColor : '#2a2a3e'}`,
                      fontSize: '0.78rem', fontWeight: 600, color: idx === 0 ? '#f8fafc' : '#cbd5e1',
                      lineHeight: 1.5,
                    }}>
                      <span style={{ display: 'inline-block', marginRight: '8px', fontSize: '0.65rem', background: `${typeColor}33`, color: typeColor, borderRadius: '999px', padding: '1px 7px', fontWeight: 700 }}>
                        Step {idx + 1}
                      </span>
                      {step}
                    </div>
                    {idx < flowchart_steps.length - 1 && (
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '4px 0' }}>
                        <div style={{ width: '2px', height: '12px', background: `${typeColor}60` }} />
                        <div style={{ color: typeColor, fontSize: '1rem', lineHeight: 1 }}>▼</div>
                      </div>
                    )}
                  </div>
                )) : (
                  <div style={{ padding: '40px', textAlign: 'center', color: '#525270', fontSize: '0.8rem' }}>
                    No process steps detected for this topic.
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ── RIGHT: Sidebar panel ── */}
          <div style={{
            width: '240px', flexShrink: 0, borderLeft: '1px solid #1a1a2e',
            overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0px',
          }}>

            {/* Explanation */}
            {explanation && (
              <div style={{ padding: '16px', borderBottom: '1px solid #1a1a2e' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
                  <span style={{ fontSize: '0.9rem' }}>📖</span>
                  <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#60a5fa', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Explanation</span>
                </div>
                <p style={{ fontSize: '0.72rem', color: '#94a3b8', lineHeight: 1.6, margin: 0 }}>{explanation}</p>
              </div>
            )}

            {/* Key Takeaways */}
            {key_takeaways.length > 0 && (
              <div style={{ padding: '16px', borderBottom: '1px solid #1a1a2e', background: '#0a1a0f' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
                  <span style={{ fontSize: '0.9rem' }}>✅</span>
                  <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#10b981', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Key Takeaways</span>
                </div>
                <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {key_takeaways.map((t, i) => (
                    <li key={i} style={{ display: 'flex', gap: '7px', alignItems: 'flex-start' }}>
                      <span style={{ color: '#10b981', fontSize: '0.6rem', marginTop: '4px', flexShrink: 0 }}>●</span>
                      <span style={{ fontSize: '0.7rem', color: '#a7f3d0', lineHeight: 1.5 }}>{t}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Examples */}
            {examples.length > 0 && (
              <div style={{ padding: '16px', borderBottom: '1px solid #1a1a2e', background: '#1a1005' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
                  <span style={{ fontSize: '0.9rem' }}>🧪</span>
                  <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#f59e0b', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Example</span>
                </div>
                {examples.map((ex, i) => (
                  <p key={i} style={{ fontSize: '0.7rem', color: '#fcd34d', lineHeight: 1.55, margin: '0 0 6px', fontFamily: 'monospace' }}>{ex}</p>
                ))}
              </div>
            )}

            {/* Related Topics */}
            {related_topics.length > 0 && (
              <div style={{ padding: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
                  <span style={{ fontSize: '0.9rem' }}>🔗</span>
                  <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#a78bfa', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Related Topics</span>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {related_topics.map((rt, i) => (
                    <span key={i} style={{
                      fontSize: '0.65rem', fontWeight: 600, padding: '3px 9px', borderRadius: '999px',
                      background: '#1e1a30', border: '1px solid #3b3060', color: '#c4b5fd',
                    }}>{rt}</span>
                  ))}
                </div>
              </div>
            )}

            {/* How to use hint */}
            <div style={{ margin: '12px 16px', padding: '10px 12px', borderRadius: '8px', background: '#0f0f1a', border: '1px solid #1e1e2e' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '4px' }}>
                <span style={{ fontSize: '0.8rem' }}>💡</span>
                <span style={{ fontSize: '0.62rem', fontWeight: 700, color: '#525270' }}>How to use this?</span>
              </div>
              <p style={{ fontSize: '0.62rem', color: '#404060', lineHeight: 1.5, margin: 0 }}>
                Switch between Concept Tree and Flowchart using the tabs above.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  };




  // ── Tabs ──────────────────────────────────────────────────────────────────
  const TABS = [
    { id: 'notes', label: 'Detailed Notes', loading: isLoadingNotes },
    { id: 'flashcards', label: 'Flashcards', loading: isLoadingFlashcards },
    { id: 'quiz', label: 'Quiz', loading: isLoadingQuiz },
    { id: 'graph', label: 'Knowledge Graph', loading: isLoadingGraph },
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
      <div className="flex items-center border-b border-slate-200 dark:border-[#1a1a1a] px-3.5 py-2.5 gap-1.5 overflow-x-auto select-none bg-sky-50/70 dark:bg-transparent">
        {TABS.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            className={`relative px-4 py-2 text-xs font-extrabold rounded-xl transition-all whitespace-nowrap cursor-pointer ${
              activeTab === tab.id
                ? 'bg-gradient-to-r from-sky-600 to-indigo-600 dark:bg-[#1e1e2e] text-white dark:text-[#F5F5F5] dark:border dark:border-[#33334d] shadow-md shadow-sky-500/20'
                : 'text-slate-700 dark:text-[#A3A3A3] hover:bg-slate-200/60 dark:hover:text-[#F5F5F5] border border-transparent'
            }`}>
            {tab.label}
            {tab.loading && (
              <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-sky-500 dark:bg-[#7C3AED] animate-pulse" />
            )}
          </button>
        ))}

        {/* Play Video Button */}
        {activeTopicIdx >= 0 && onPlayVideo && (
          <div className="ml-auto pl-2">
            <button
              onClick={() => {
                const topic = topics[activeTopicIdx];
                const segmentIdx = topic?.start_segment;
                if (segmentIdx !== undefined && transcriptData?.segments?.[segmentIdx]) {
                  const startTime = transcriptData.segments[segmentIdx].start;
                  onPlayVideo(startTime);
                }
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-bold text-white rounded-md transition-all whitespace-nowrap shadow-[0_0_10px_rgba(124,58,237,0.3)] hover:shadow-[0_0_15px_rgba(124,58,237,0.5)] hover:-translate-y-0.5 active:translate-y-0 bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-500 hover:to-fuchsia-500"
            >
              <span className="text-[14px] leading-none">▶️</span> Play Video from Here
            </button>
          </div>
        )}
      </div>

      {/* Content pane */}
      <div className="flex-1 overflow-y-auto" style={{ maxHeight: '640px' }}>
        {activeTab === 'notes' && renderNotes()}
        {activeTab === 'flashcards' && renderFlashcards()}
        {activeTab === 'quiz' && renderQuiz()}
        {activeTab === 'graph' && renderGraph()}
      </div>
    </div>
  );
}

// ── Section component ─────────────────────────────────────────────────────────

const SECTION_STYLES = {
  violet:  { accent: '#7c3aed', bg: 'rgba(124,58,237,0.04)',  labelColor: '#a78bfa' },
  amber:   { accent: '#f59e0b', bg: 'rgba(245,158,11,0.04)',  labelColor: '#fbbf24' },
  cyan:    { accent: '#06b6d4', bg: 'rgba(6,182,212,0.04)',   labelColor: '#22d3ee' },
  emerald: { accent: '#10b981', bg: 'rgba(16,185,129,0.04)', labelColor: '#34d399' },
  rose:    { accent: '#f43f5e', bg: 'rgba(244,63,94,0.04)',  labelColor: '#fb7185' },
  slate:   { accent: '#64748b', bg: 'rgba(100,116,139,0.04)',labelColor: '#94a3b8' },
};

function Section({ icon, label, color = 'violet', children }) {
  const s = SECTION_STYLES[color] || SECTION_STYLES.violet;
  return (
    <div style={{
      borderRadius: '10px',
      border: `1px solid ${s.accent}22`,
      borderLeft: `3px solid ${s.accent}`,
      background: s.bg,
      padding: '16px 18px',
      marginBottom: '4px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
        <span style={{ fontSize: '1rem' }}>{icon}</span>
        <span style={{ fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.13em', color: s.labelColor }}>{label}</span>
      </div>
      {children}
    </div>
  );
}

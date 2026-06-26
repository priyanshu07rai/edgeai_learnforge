import React from 'react';
import { getTopicAccuracyStatus } from '../utils/progress';

const STATUS_DOT = {
  strong:      { cls: 'bg-emerald-500', title: 'Mastered (≥80%)' },
  medium:      { cls: 'bg-amber-500', title: 'Good (60-79%)' },
  weak:        { cls: 'bg-red-500 animate-pulse', title: 'Needs Revision (<60%)' },
  unattempted: { cls: 'bg-[#333]', title: 'Not attempted' },
};

/**
 * TopicSidebar Component (Desktop)
 * Shows accuracy status dot next to each topic (Feature 3 – Weak Topic Detection).
 */
export default function TopicSidebar({ topics, activeTopicIdx, onTopicClick, videoId = null }) {
  if (!topics || topics.length === 0) return null;

  return (
    <div className="w-[280px] shrink-0 border-r border-[#262626] h-[500px] flex flex-col bg-[#111111] text-left select-none overflow-hidden">
      <div className="flex-1 overflow-y-auto p-4 space-y-1.5 custom-scrollbar">
        {/* Course Overview button */}
        <button
          onClick={() => onTopicClick(-1)}
          className={`w-full text-left text-sm py-2 px-3 rounded-md transition-all duration-150 cursor-pointer flex items-center gap-2.5 border ${
            activeTopicIdx === -1
              ? 'border-[#262626] bg-[#0B0B0B] text-[#7C3AED] font-semibold shadow-inner'
              : 'border-transparent text-[#A3A3A3] hover:text-[#F5F5F5] hover:bg-[#0B0B0B]/50'
          }`}
        >
          <span>📌</span>
          <span className="truncate">Course Overview</span>
        </button>

        {topics.map((topic, idx) => {
          const isActive = idx === activeTopicIdx;
          const status = videoId ? getTopicAccuracyStatus(videoId, idx) : 'unattempted';
          const dot = STATUS_DOT[status];


          return (
            <button
              key={idx}
              onClick={() => onTopicClick(idx)}
              className={`w-full text-left text-sm py-2 px-3 rounded-md transition-all duration-150 cursor-pointer flex items-center gap-2.5 border ${
                isActive
                  ? 'border-[#262626] bg-[#0B0B0B] text-[#7C3AED] font-semibold shadow-inner'
                  : 'border-transparent text-[#A3A3A3] hover:text-[#F5F5F5] hover:bg-[#0B0B0B]/50'
              }`}
            >
              {/* Accuracy status dot */}
              <span
                className={`w-1.5 h-1.5 rounded-full shrink-0 ${dot.cls}`}
                title={dot.title}
              />
              <span className="truncate">{topic.title}</span>
              {topic.density_badge && (
                <span className="ml-2 shrink-0 text-[10px] select-none opacity-85" title={`Density: ${topic.density}`}>
                  {topic.density_badge}
                </span>
              )}
              {status === 'weak' && (
                <span className="ml-auto shrink-0 text-[9px] font-bold text-red-400 bg-red-500/10 border border-red-500/20 rounded px-1.5 py-0.5">
                  ↻
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Legend */}
      {videoId && (
        <div className="px-4 py-3 border-t border-[#1e1e1e] flex flex-wrap gap-x-3 gap-y-1">
          {[
            { cls: 'bg-emerald-500', label: 'Mastered' },
            { cls: 'bg-amber-500', label: 'Good' },
            { cls: 'bg-red-500', label: 'Weak' },
            { cls: 'bg-[#333]', label: 'New' },
          ].map(item => (
            <span key={item.label} className="flex items-center gap-1 text-[10px] text-[#525252]">
              <span className={`w-1.5 h-1.5 rounded-full ${item.cls}`} />
              {item.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * DifficultySelector.jsx — Pill selector for Beginner / Intermediate / Advanced.
 * Shown after video is processed, before studying.
 */
import React from 'react';

const LEVELS = [
  {
    id: 'beginner',
    label: 'Beginner',
    icon: '🌱',
    desc: 'Simple explanations, no jargon',
    color: 'emerald',
  },
  {
    id: 'intermediate',
    label: 'Intermediate',
    icon: '⚡',
    desc: 'Implementation details & examples',
    color: 'violet',
  },
  {
    id: 'advanced',
    label: 'Advanced',
    icon: '🔬',
    desc: 'Architecture, edge cases & trade-offs',
    color: 'amber',
  },
];

const COLOR_MAP = {
  emerald: {
    active: 'border-emerald-500/60 bg-emerald-500/10 text-emerald-400',
    inactive: 'border-[#262626] text-[#737373] hover:border-emerald-500/30 hover:text-emerald-400/60',
    dot: 'bg-emerald-500',
  },
  violet: {
    active: 'border-violet-500/60 bg-violet-500/10 text-violet-400',
    inactive: 'border-[#262626] text-[#737373] hover:border-violet-500/30 hover:text-violet-400/60',
    dot: 'bg-violet-500',
  },
  amber: {
    active: 'border-amber-500/60 bg-amber-500/10 text-amber-400',
    inactive: 'border-[#262626] text-[#737373] hover:border-amber-500/30 hover:text-amber-400/60',
    dot: 'bg-amber-500',
  },
};

export default function DifficultySelector({ value, onChange }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[10px] font-semibold tracking-widest text-[#525252] uppercase">
        Study Level
      </p>
      <div className="flex gap-2 flex-wrap">
        {LEVELS.map((level) => {
          const isActive = value === level.id;
          const colors = COLOR_MAP[level.color];
          return (
            <button
              key={level.id}
              onClick={() => onChange(level.id)}
              title={level.desc}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
                isActive ? colors.active : colors.inactive
              }`}
            >
              <span>{level.icon}</span>
              <span>{level.label}</span>
              {isActive && (
                <span className={`w-1.5 h-1.5 rounded-full ${colors.dot}`} />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

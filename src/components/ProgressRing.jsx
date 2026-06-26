/**
 * ProgressRing.jsx — SVG circular progress ring.
 */
import React from 'react';

export default function ProgressRing({ pct = 0, size = 80, stroke = 6, color = '#7C3AED', label = '' }) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2} cy={size / 2} r={r}
          strokeWidth={stroke} stroke="#1e1e1e" fill="none"
        />
        <circle
          cx={size / 2} cy={size / 2} r={r}
          strokeWidth={stroke} stroke={color} fill="none"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      </svg>
      <div className="text-center -mt-1" style={{ marginTop: -(size / 2 + 4) }}>
        {/* overlay text inside ring */}
      </div>
    </div>
  );
}

/** Standalone ring with centered pct text */
export function StatRing({ pct = 0, size = 88, stroke = 7, color = '#7C3AED', sublabel = '' }) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="absolute inset-0 -rotate-90">
        <circle cx={size/2} cy={size/2} r={r} strokeWidth={stroke} stroke="#1e1e1e" fill="none" />
        <circle
          cx={size/2} cy={size/2} r={r}
          strokeWidth={stroke} stroke={color} fill="none"
          strokeDasharray={circ} strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.7s ease' }}
        />
      </svg>
      <div className="flex flex-col items-center z-10">
        <span className="text-lg font-bold text-[#F5F5F5]">{pct}%</span>
        {sublabel && <span className="text-[9px] text-[#525252] uppercase tracking-wider">{sublabel}</span>}
      </div>
    </div>
  );
}

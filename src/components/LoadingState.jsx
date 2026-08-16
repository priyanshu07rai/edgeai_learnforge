import React, { useState, useEffect } from 'react';

/**
 * LoadingState — shows which phase we're in with an elapsed timer
 * and optional live Whisper progress (segments transcribed, audio position).
 */
export default function LoadingState({ phase = 'transcript', progress = null }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setElapsed(s => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  const timeStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;

  const phases = {
    transcript: {
      title: 'Transcribing audio…',
      sub: 'Whisper AI is converting speech to text. Long videos take 2–5 minutes.',
      color: '#0284C7',
    },
    topics: {
      title: 'Building Knowledge Structure…',
      sub: 'Segmenting topics and indexing content for your study guide.',
      color: '#059669',
    },
  };

  const { title, sub, color } = phases[phase] || phases.transcript;

  const formatAudio = (secs) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}m ${s}s`;
  };

  const hasProgress = progress && (progress.segments > 0 || progress.audio_pos > 0);

  return (
    <div className="flex flex-col items-center justify-center p-10 space-y-5">
      {/* Spinner */}
      <div
        className="w-12 h-12 rounded-full border-2 border-slate-300 dark:border-[#262626] animate-spin"
        style={{ borderTopColor: color }}
      />

      {/* Text */}
      <div className="text-center space-y-1.5 max-w-sm">
        <p className="text-sm font-bold tracking-wide text-slate-900 dark:text-[#F5F5F5]">{title}</p>
        <p className="text-xs font-medium text-slate-600 dark:text-[#737373]">{sub}</p>
      </div>

      {/* Live Whisper progress */}
      {hasProgress && (
        <div className="flex flex-col items-center gap-1 text-center">
          <span className="text-xs font-bold text-sky-700 dark:text-violet-300">
            {progress.segments} segments transcribed
          </span>
          {progress.audio_pos > 0 && (
            <span className="text-[11px] font-semibold text-slate-700 dark:text-neutral-400">
              Audio processed: {formatAudio(progress.audio_pos)}
            </span>
          )}
        </div>
      )}

      {/* Timer Badge */}
      <div className="px-3.5 py-1 rounded-full text-xs font-bold bg-sky-100 dark:bg-purple-950/40 text-sky-900 dark:text-purple-300 border border-sky-300 dark:border-purple-800/60 shadow-sm flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-sky-500 animate-pulse" />
        {timeStr} elapsed — please wait, do not refresh
      </div>
    </div>
  );
}

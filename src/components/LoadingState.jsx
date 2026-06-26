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
      color: '#7C3AED',
    },
    topics: {
      title: 'Building Knowledge Structure…',
      sub: 'Segmenting topics and indexing content for your study guide.',
      color: '#059669',
    },
  };

  const { title, sub, color } = phases[phase] || phases.transcript;

  // Format audio position as mm:ss
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
        className="w-12 h-12 rounded-full border-2 border-[#262626] animate-spin"
        style={{ borderTopColor: color }}
      />

      {/* Text */}
      <div className="text-center space-y-1.5 max-w-sm">
        <p className="text-sm font-semibold tracking-wide text-[#F5F5F5]">{title}</p>
        <p className="text-xs text-[#737373]">{sub}</p>
      </div>

      {/* Live Whisper progress */}
      {hasProgress && (
        <div className="flex flex-col items-center gap-1 text-center">
          <span className="text-[11px] font-mono text-violet-300/80">
            {progress.segments} segments transcribed
          </span>
          <span className="text-[10px] font-mono text-[#525252]">
            Audio processed: {formatAudio(progress.audio_pos)}
          </span>
        </div>
      )}

      {/* Elapsed timer — shows the app is alive */}
      <div
        className="flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-mono"
        style={{ background: `${color}15`, color: `${color}CC`, border: `1px solid ${color}30` }}
      >
        <span
          className="w-1.5 h-1.5 rounded-full animate-pulse"
          style={{ background: color }}
        />
        {timeStr} elapsed — please wait, do not refresh
      </div>
    </div>
  );
}

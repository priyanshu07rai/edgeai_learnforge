import React from 'react';
import { useTheme } from '../context/ThemeContext';

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isLight = theme === 'light';

  return (
    <div className="flex justify-center w-full mb-4">
      <button
        onClick={toggleTheme}
        type="button"
        aria-label="Toggle Dark and Light Theme"
        className={`group relative inline-flex items-center gap-2.5 px-4 py-2 rounded-full border-2 text-xs font-bold tracking-wide transition-all duration-300 shadow-md cursor-pointer select-none ${
          isLight
            ? 'bg-white border-slate-300 text-slate-900 hover:border-indigo-500 shadow-slate-300/50'
            : 'bg-[#161618] border-[#2e2e34] text-neutral-100 hover:border-purple-500/60 shadow-black/60'
        }`}
      >
        {/* Sun Icon for Light */}
        <span
          className={`flex items-center gap-1.5 transition-all duration-300 ${
            isLight ? 'text-amber-600 font-extrabold scale-105' : 'text-slate-500 opacity-60'
          }`}
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
          </svg>
          Light
        </span>

        {/* Sliding Pill Indicator */}
        <div className={`w-9 h-5 rounded-full p-0.5 border transition-colors duration-300 ${isLight ? 'bg-amber-100 border-amber-300' : 'bg-purple-950 border-purple-800'}`}>
          <div
            className={`w-3.5 h-3.5 rounded-full transition-transform duration-300 shadow-sm ${
              isLight
                ? 'translate-x-0 bg-amber-500'
                : 'translate-x-4 bg-purple-400'
            }`}
          />
        </div>

        {/* Moon Icon for Dark */}
        <span
          className={`flex items-center gap-1.5 transition-all duration-300 ${
            !isLight ? 'text-purple-300 font-extrabold scale-105' : 'text-slate-500 opacity-60'
          }`}
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
          </svg>
          Dark
        </span>
      </button>
    </div>
  );
}

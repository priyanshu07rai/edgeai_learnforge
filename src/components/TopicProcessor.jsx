import React from 'react';

/**
 * TopicProcessor Component
 * @param {Object} props
 * @param {boolean} props.isProcessing - Loading state indicator
 * @param {string|null} props.error - Inline error string
 */
export default function TopicProcessor({ isProcessing, error }) {
  if (!isProcessing && !error) return null;

  return (
    <div className="w-full max-w-3xl mx-auto p-4 transition-all duration-200">
      {isProcessing && (
        <div className="flex flex-col items-center justify-center p-6 space-y-4">
          {/* Simple Spinner */}
          <div className="w-8 h-8 rounded-full border-2 border-[#262626] border-t-[#7C3AED] animate-spin"></div>
          <div className="text-center space-y-1">
            <p className="text-sm font-semibold text-[#F5F5F5]">
              Processing Topics...
            </p>
            <p className="text-xs text-[#A3A3A3]">
              Creating Knowledge Structure...
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="p-4 bg-red-950/20 border border-red-900/40 text-red-200 rounded-lg text-sm text-left animate-in fade-in slide-in-from-top-1">
          {error}
        </div>
      )}
    </div>
  );
}

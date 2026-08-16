import React, { useState, useRef } from 'react';

/**
 * UploadBox Component — Theme-aware upload panel.
 */
export default function UploadBox({ onSubmit, isProcessing, error, onClearError }) {
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [file, setFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  const handleUrlChange = (e) => {
    setYoutubeUrl(e.target.value);
    if (e.target.value.trim() !== '') {
      setFile(null);
    }
    if (error) onClearError();
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0];
      validateAndSetFile(droppedFile);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const validateAndSetFile = (selectedFile) => {
    const isMp4 = selectedFile.name.toLowerCase().endsWith('.mp4') || selectedFile.type === 'video/mp4';
    if (!isMp4) {
      onSubmit({ youtubeUrl: null, file: selectedFile, triggerValidationOnly: true });
      return;
    }
    setFile(selectedFile);
    setYoutubeUrl('');
    if (error) onClearError();
  };

  const removeFile = (e) => {
    e.stopPropagation();
    setFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleGenerate = (e) => {
    e.preventDefault();
    if (isProcessing) return;

    if (!youtubeUrl.trim() && !file) {
      onSubmit({ errorOverride: 'Unable to fetch transcript.' });
      return;
    }

    onSubmit({
      youtubeUrl: youtubeUrl.trim() || null,
      file: file
    });
  };

  return (
    <div className="w-full max-w-3xl mx-auto rounded-2xl p-8 transition-all duration-300 bg-white dark:bg-[#111111] border border-slate-200 dark:border-[#262626] shadow-xl shadow-slate-200/50 dark:shadow-2xl">
      <form onSubmit={handleGenerate} className="space-y-6">
        {/* YouTube Input */}
        <div className="space-y-2">
          <input
            type="text"
            id="youtube-url"
            value={youtubeUrl}
            onChange={handleUrlChange}
            disabled={isProcessing}
            placeholder="Paste YouTube video URL..."
            className="block w-full px-4 py-3.5 rounded-xl text-sm transition-all duration-200 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-[#7C3AED] bg-slate-50 dark:bg-[#0B0B0B] border border-slate-200 dark:border-[#262626] text-slate-900 dark:text-[#F5F5F5] placeholder-slate-400 dark:placeholder-[#A3A3A3]"
          />
        </div>

        {/* Divider */}
        <div className="relative flex py-1 items-center">
          <div className="flex-grow border-t border-slate-200 dark:border-[#262626]"></div>
          <span className="flex-shrink mx-4 text-xs font-semibold tracking-wider text-slate-400 dark:text-[#A3A3A3] uppercase">OR</span>
          <div className="flex-grow border-t border-slate-200 dark:border-[#262626]"></div>
        </div>

        {/* Drag and Drop File Upload Area */}
        <div className="space-y-2">
          <div
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={() => !isProcessing && fileInputRef.current?.click()}
            className={`flex flex-col items-center justify-center w-full h-36 border-2 border-dashed rounded-xl cursor-pointer transition-all duration-200 ${
              dragActive 
                ? 'border-indigo-500 bg-indigo-50/70 dark:border-[#7C3AED] dark:bg-[#7C3AED]/10' 
                : 'border-slate-300 dark:border-[#262626] bg-slate-50/60 dark:bg-[#0B0B0B] hover:border-indigo-400 dark:hover:border-[#7C3AED]/50'
            } ${isProcessing ? 'pointer-events-none opacity-50' : ''}`}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept="video/mp4"
              className="hidden"
            />

            {!file ? (
              <div className="text-center px-4 space-y-1">
                <svg className="w-8 h-8 mx-auto mb-2 text-indigo-500 dark:text-[#7C3AED] opacity-80" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p className="text-sm font-medium text-slate-700 dark:text-[#F5F5F5]">
                  Drag & drop your MP4 file here, or <span className="text-indigo-600 dark:text-[#7C3AED] font-semibold underline decoration-indigo-300 underline-offset-2">browse</span>
                </p>
                <p className="text-xs text-slate-400 dark:text-[#A3A3A3]">Supports video/mp4 format</p>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center p-4">
                <p className="text-sm font-semibold text-slate-800 dark:text-[#F5F5F5] text-center max-w-md truncate">
                  🎬 {file.name}
                </p>
                <button
                  type="button"
                  onClick={removeFile}
                  className="mt-2 text-xs text-red-500 hover:text-red-600 dark:text-red-400 dark:hover:text-red-300 transition-colors font-medium"
                >
                  Remove File
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Error Display */}
        {error && (
          <div className="p-4 bg-red-50 border border-red-200 text-red-700 dark:bg-red-950/30 dark:border-red-800/40 dark:text-red-300 rounded-xl text-sm text-left">
            {error}
          </div>
        )}

        {/* Generate Button */}
        <button
          type="submit"
          disabled={isProcessing || (!youtubeUrl.trim() && !file)}
          className={`w-full py-3.5 px-4 rounded-xl font-semibold tracking-wide transition-all duration-300 text-sm cursor-pointer shadow-lg select-none ${
            isProcessing || (!youtubeUrl.trim() && !file)
              ? 'bg-slate-200 dark:bg-[#262626] text-slate-400 dark:text-[#A3A3A3] cursor-not-allowed border border-transparent'
              : 'bg-indigo-600 hover:bg-indigo-700 dark:bg-[#7C3AED] dark:hover:bg-[#6D28D9] text-white hover:shadow-indigo-500/25 active:scale-[0.99]'
          }`}
        >
          Generate Transcript
        </button>
      </form>
    </div>
  );
}

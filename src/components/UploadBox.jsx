import React, { useState, useRef } from 'react';

/**
 * UploadBox Component — Light Sky Blue & Mint Theme Card.
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
    <div className="w-full max-w-3xl mx-auto rounded-3xl p-8 transition-all duration-300 bg-[#F0F9FF] dark:bg-[#111111] border-2 border-[#BAE6FD] dark:border-[#262626] shadow-xl shadow-sky-200/50 dark:shadow-2xl">
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
            className="block w-full px-4 py-3.5 rounded-2xl text-sm font-semibold transition-all duration-200 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-[#0284C7] focus:border-[#0284C7] bg-white dark:bg-[#0B0B0B] border-2 border-[#93C5FD] dark:border-[#262626] text-slate-900 dark:text-[#F5F5F5] placeholder-slate-400 dark:placeholder-[#A3A3A3] shadow-sm"
          />
        </div>

        {/* Divider */}
        <div className="relative flex py-1 items-center">
          <div className="flex-grow border-t-2 border-[#BAE6FD] dark:border-[#262626]"></div>
          <span className="flex-shrink mx-4 text-xs font-extrabold tracking-wider text-sky-700 dark:text-[#A3A3A3] uppercase">OR</span>
          <div className="flex-grow border-t-2 border-[#BAE6FD] dark:border-[#262626]"></div>
        </div>

        {/* Drag and Drop File Upload Area */}
        <div className="space-y-2">
          <div
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={() => !isProcessing && fileInputRef.current?.click()}
            className={`flex flex-col items-center justify-center w-full h-36 border-2 border-dashed rounded-2xl cursor-pointer transition-all duration-200 ${
              dragActive 
                ? 'border-[#10B981] bg-[#D1FAE5] dark:border-[#7C3AED] dark:bg-[#7C3AED]/10' 
                : 'border-[#34D399] dark:border-[#262626] bg-[#ECFDF5] dark:bg-[#0B0B0B] hover:border-[#059669] dark:hover:border-[#7C3AED]/50'
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
                <svg className="w-9 h-9 mx-auto mb-2 text-[#059669] dark:text-[#7C3AED]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p className="text-sm font-bold text-slate-800 dark:text-[#F5F5F5]">
                  Drag & drop your MP4 file here, or <span className="text-[#059669] dark:text-[#7C3AED] font-extrabold underline decoration-emerald-400 underline-offset-2">browse</span>
                </p>
                <p className="text-xs font-semibold text-emerald-700 dark:text-[#A3A3A3]">Supports video/mp4 format</p>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center p-4">
                <p className="text-sm font-bold text-slate-900 dark:text-[#F5F5F5] text-center max-w-md truncate">
                  🎬 {file.name}
                </p>
                <button
                  type="button"
                  onClick={removeFile}
                  className="mt-2 text-xs text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 transition-colors font-extrabold"
                >
                  Remove File
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Error Display */}
        {error && (
          <div className="p-4 bg-red-100 border-2 border-red-300 text-red-800 dark:bg-red-950/30 dark:border-red-800/40 dark:text-red-300 rounded-2xl text-sm text-left font-semibold">
            {error}
          </div>
        )}

        {/* Generate Button */}
        <button
          type="submit"
          disabled={isProcessing || (!youtubeUrl.trim() && !file)}
          className={`w-full py-3.5 px-4 rounded-2xl font-extrabold tracking-wide transition-all duration-300 text-sm select-none shadow-md ${
            isProcessing || (!youtubeUrl.trim() && !file)
              ? 'bg-[#E2E8F0] dark:bg-[#262626] text-[#0F172A] dark:text-[#A3A3A3] cursor-not-allowed border-2 border-[#CBD5E1] dark:border-transparent opacity-90'
              : 'bg-gradient-to-r from-sky-600 via-indigo-600 to-purple-600 hover:from-sky-700 hover:to-indigo-700 text-white shadow-sky-500/25 active:scale-[0.99] cursor-pointer'
          }`}
        >
          Generate Transcript
        </button>
      </form>
    </div>
  );
}

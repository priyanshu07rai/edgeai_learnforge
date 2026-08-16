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
    <div className="w-full max-w-3xl mx-auto rounded-2xl p-8 transition-all duration-300 bg-[#111111] dark:bg-[#111111] light:bg-white border border-[#262626] dark:border-[#262626] light:border-slate-200/80 shadow-2xl light:shadow-xl light:shadow-slate-200/50">
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
            className="block w-full px-4 py-3.5 rounded-xl text-sm transition-all duration-200 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-[#7C3AED] light:focus:ring-indigo-500 bg-[#0B0B0B] dark:bg-[#0B0B0B] light:bg-slate-50 border border-[#262626] dark:border-[#262626] light:border-slate-200 text-[#F5F5F5] dark:text-[#F5F5F5] light:text-slate-900 placeholder-[#A3A3A3] light:placeholder-slate-400"
          />
        </div>

        {/* Divider */}
        <div className="relative flex py-1 items-center">
          <div className="flex-grow border-t border-[#262626] dark:border-[#262626] light:border-slate-200"></div>
          <span className="flex-shrink mx-4 text-xs font-semibold tracking-wider text-[#A3A3A3] light:text-slate-400 uppercase">OR</span>
          <div className="flex-grow border-t border-[#262626] dark:border-[#262626] light:border-slate-200"></div>
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
                ? 'border-[#7C3AED] bg-[#7C3AED]/10 light:border-indigo-500 light:bg-indigo-50/70' 
                : 'border-[#262626] dark:border-[#262626] light:border-slate-300 bg-[#0B0B0B] dark:bg-[#0B0B0B] light:bg-slate-50/60 hover:border-[#7C3AED]/50 light:hover:border-indigo-400'
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
                <svg className="w-8 h-8 mx-auto mb-2 text-[#7C3AED] light:text-indigo-500 opacity-80" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p className="text-sm font-medium text-[#F5F5F5] light:text-slate-700">
                  Drag & drop your MP4 file here, or <span className="text-[#7C3AED] light:text-indigo-600 font-semibold underline decoration-indigo-300 underline-offset-2">browse</span>
                </p>
                <p className="text-xs text-[#A3A3A3] light:text-slate-400">Supports video/mp4 format</p>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center p-4">
                <p className="text-sm font-semibold text-[#F5F5F5] light:text-slate-800 text-center max-w-md truncate">
                  🎬 {file.name}
                </p>
                <button
                  type="button"
                  onClick={removeFile}
                  className="mt-2 text-xs text-red-400 hover:text-red-300 light:text-red-500 light:hover:text-red-600 transition-colors font-medium"
                >
                  Remove File
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Error Display */}
        {error && (
          <div className="p-4 bg-red-950/30 border border-red-800/40 text-red-300 light:bg-red-50 light:border-red-200 light:text-red-700 rounded-xl text-sm text-left">
            {error}
          </div>
        )}

        {/* Generate Button */}
        <button
          type="submit"
          disabled={isProcessing || (!youtubeUrl.trim() && !file)}
          className={`w-full py-3.5 px-4 rounded-xl font-semibold tracking-wide transition-all duration-300 text-sm cursor-pointer shadow-lg select-none ${
            isProcessing || (!youtubeUrl.trim() && !file)
              ? 'bg-[#262626] dark:bg-[#262626] light:bg-slate-200 text-[#A3A3A3] light:text-slate-400 cursor-not-allowed border border-transparent'
              : 'bg-[#7C3AED] hover:bg-[#6D28D9] light:bg-indigo-600 light:hover:bg-indigo-700 text-white hover:shadow-indigo-500/25 active:scale-[0.99]'
          }`}
        >
          Generate Transcript
        </button>
      </form>
    </div>
  );
}

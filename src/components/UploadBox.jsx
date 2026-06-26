import React, { useState, useRef } from 'react';

/**
 * UploadBox Component
 * @param {Object} props
 * @param {Function} props.onSubmit - Triggered on submit, passing { youtubeUrl, file }
 * @param {boolean} props.isProcessing - True when transcript is generating
 * @param {string|null} props.error - Inline error message to display
 * @param {Function} props.onClearError - Callback to clear parent error state
 */
export default function UploadBox({ onSubmit, isProcessing, error, onClearError }) {
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [file, setFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  // Handle URL change
  const handleUrlChange = (e) => {
    setYoutubeUrl(e.target.value);
    if (e.target.value.trim() !== '') {
      setFile(null);
    }
    if (error) onClearError();
  };

  // Handle file drag
  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  // Handle file drop
  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0];
      validateAndSetFile(droppedFile);
    }
  };

  // Handle file selection
  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  // Validate and set file
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
    <div className="w-full max-w-3xl mx-auto bg-[#111111] border border-[#262626] rounded-xl p-8 transition-all duration-300">
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
            className="block w-full px-4 py-3 bg-[#0B0B0B] border border-[#262626] rounded-lg text-[#F5F5F5] placeholder-[#A3A3A3] focus:outline-none focus:ring-1 focus:ring-[#7C3AED] focus:border-transparent transition-all duration-200 text-sm disabled:opacity-50"
          />
        </div>

        {/* Divider */}
        <div className="relative flex py-1 items-center">
          <div className="flex-grow border-t border-[#262626]"></div>
          <span className="flex-shrink mx-4 text-xs tracking-wider text-[#A3A3A3]">OR</span>
          <div className="flex-grow border-t border-[#262626]"></div>
        </div>

        {/* Drag and Drop File Upload Area */}
        <div className="space-y-2">
          <div
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={() => !isProcessing && fileInputRef.current?.click()}
            className={`flex flex-col items-center justify-center w-full h-36 border border-dashed rounded-lg cursor-pointer transition-all duration-200 ${
              dragActive 
                ? 'border-[#7C3AED] bg-[#7C3AED]/5' 
                : 'border-[#262626] bg-[#0B0B0B] hover:border-[#7C3AED]/50'
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
              <div className="text-center px-4">
                <p className="text-sm text-[#F5F5F5]">
                  Drag and drop your MP4 file here, or <span className="text-[#7C3AED]">browse</span>
                </p>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center p-4">
                <p className="text-sm font-semibold text-[#F5F5F5] text-center max-w-md truncate">
                  {file.name}
                </p>
                <button
                  type="button"
                  onClick={removeFile}
                  className="mt-2 text-xs text-[#A3A3A3] hover:text-[#F5F5F5] transition-colors"
                >
                  Remove File
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Error State Display */}
        {error && (
          <div className="p-4 bg-red-950/20 border border-red-900/40 text-red-200 rounded-lg text-sm text-left">
            {error}
          </div>
        )}

        {/* Generate Button */}
        <button
          type="submit"
          disabled={isProcessing || (!youtubeUrl.trim() && !file)}
          className={`w-full py-3.5 px-4 rounded-lg font-semibold tracking-wide transition-all duration-200 text-sm cursor-pointer shadow-md select-none ${
            isProcessing || (!youtubeUrl.trim() && !file)
              ? 'bg-[#262626] text-[#A3A3A3] cursor-not-allowed border border-transparent'
              : 'bg-[#7C3AED] hover:bg-[#6D28D9] text-[#F5F5F5]'
          }`}
        >
          Generate Transcript
        </button>
      </form>
    </div>
  );
}

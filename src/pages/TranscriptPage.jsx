import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import UploadBox from '../components/UploadBox';
import LoadingState from '../components/LoadingState';
import TranscriptViewer from '../components/TranscriptViewer';
import TopicSidebar from '../components/TopicSidebar';
import TopicDropdown from '../components/TopicDropdown';
import TopicProcessor from '../components/TopicProcessor';
import DebugViewer from '../components/DebugViewer';
import FloatingAI from '../components/FloatingAI';
// Using native HTML5 <video> — no library needed
import { fetchTranscript, processVideo, generateNotesForTopic, generateFlashcardsForTopic, generateQuizForTopic, fetchOverallSummary, getVideoUrl } from '../services/api';
import { saveSession } from './DashboardPage';

const PRELOAD_AHEAD = 2;
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default function TranscriptPage() {
  const navigate = useNavigate();

  const [isProcessingTranscript, setIsProcessingTranscript] = useState(false);
  const [isProcessingTopics, setIsProcessingTopics] = useState(false);
  const [error, setError] = useState(null);

  const [transcriptData, setTranscriptData] = useState(null);
  const [topics, setTopics] = useState([]);
  const [activeTopicIdx, setActiveTopicIdx] = useState(-1);
  const [activeTab, setActiveTab] = useState('notes');

  const [notes, setNotes] = useState([]);
  const [flashcards, setFlashcards] = useState([]);
  const [quiz, setQuiz] = useState([]);

  const [overallSummary, setOverallSummary] = useState(null);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);

  const [loadingNotes, setLoadingNotes] = useState({});
  const [loadingCards, setLoadingCards] = useState({});
  const [loadingQuiz, setLoadingQuiz] = useState({});

  const reqNotes = useRef(new Set());
  const reqCards = useRef(new Set());
  const reqQuiz = useRef(new Set());

  const [showDebug, setShowDebug] = useState(false);

  // ── Video Syncing ──────────────────────────────────────────────────────────
  const videoRef = useRef(null);      // native <video> element
  const videoWrapperRef = useRef(null);
  const [localVideoUrl, setLocalVideoUrl] = useState(null); // blob URL for instant preview

  // Cleanup blob URL on unmount
  useEffect(() => {
    return () => { if (localVideoUrl) URL.revokeObjectURL(localVideoUrl); };
  }, [localVideoUrl]);

  const handlePlayVideo = useCallback((timeSecs) => {
    if (videoWrapperRef.current) {
      const y = videoWrapperRef.current.getBoundingClientRect().top + window.scrollY - 20;
      window.scrollTo({ top: y, behavior: 'smooth' });
    }
    const vid = videoRef.current;
    if (vid) {
      vid.currentTime = timeSecs;
      vid.play().catch(() => {});   // catch autoplay-policy block silently
    }
  }, []);

  // ── Live transcription progress (polls backend while Whisper runs) ──────────
  const [transcriptProgress, setTranscriptProgress] = useState(null); // { segments, audio_pos }
  const pendingVideoId = useRef(null); // video_id assigned BEFORE transcript completes

  // ── Loaders ───────────────────────────────────────────────────────────────

  const loadNotes = useCallback(async (videoId, idx, total) => {
    if (idx < 0 || idx >= total || reqNotes.current.has(idx)) return;
    reqNotes.current.add(idx);
    setLoadingNotes(p => ({ ...p, [idx]: true }));
    try {
      const res = await fetch(`${API_BASE}/notes/topic`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_id: videoId, topic_index: idx }),
      });
      const data = await res.json();
      setNotes(p => { const a = [...p]; a[idx] = data; return a; });
    } catch (e) {
      console.error(`[Notes] topic ${idx}:`, e);
      reqNotes.current.delete(idx);
    } finally {
      setLoadingNotes(p => ({ ...p, [idx]: false }));
    }
  }, []);

  const loadCards = useCallback(async (videoId, idx, total) => {
    if (idx < 0 || idx >= total || reqCards.current.has(idx)) return;
    reqCards.current.add(idx);
    setLoadingCards(p => ({ ...p, [idx]: true }));
    try {
      const data = await generateFlashcardsForTopic(videoId, idx);
      setFlashcards(p => { const a = [...p]; a[idx] = data; return a; });
    } catch (e) {
      console.error(`[Cards] topic ${idx}:`, e);
      reqCards.current.delete(idx);
    } finally {
      setLoadingCards(p => ({ ...p, [idx]: false }));
    }
  }, []);

  const loadQuiz = useCallback(async (videoId, idx, total) => {
    if (idx < 0 || idx >= total || reqQuiz.current.has(idx)) return;
    reqQuiz.current.add(idx);
    setLoadingQuiz(p => ({ ...p, [idx]: true }));
    try {
      const data = await generateQuizForTopic(videoId, idx);
      setQuiz(p => { const a = [...p]; a[idx] = data; return a; });
    } catch (e) {
      console.error(`[Quiz] topic ${idx}:`, e);
      reqQuiz.current.delete(idx);
    } finally {
      setLoadingQuiz(p => ({ ...p, [idx]: false }));
    }
  }, []);

  const loadSummary = useCallback(async (videoId) => {
    if (overallSummary || isLoadingSummary) return;
    setIsLoadingSummary(true);
    try {
      const data = await fetchOverallSummary(videoId);
      setOverallSummary(data);
    } catch (e) {
      console.error(`[Summary] fetch failed:`, e);
    } finally {
      setIsLoadingSummary(false);
    }
  }, [overallSummary, isLoadingSummary]);

  // Fetch summary if activeTopicIdx is -1 and topics have finished processing
  useEffect(() => {
    const videoId = transcriptData?.video_id;
    if (!videoId || isProcessingTopics) return;
    if (activeTopicIdx === -1) {
      loadSummary(videoId);
    }
  }, [activeTopicIdx, transcriptData, isProcessingTopics, loadSummary]);

  useEffect(() => {
    const videoId = transcriptData?.video_id;
    if (!videoId || topics.length === 0) return;
    const total = topics.length;

    // Load current topic immediately
    loadNotes(videoId, activeTopicIdx, total);
    loadCards(videoId, activeTopicIdx, total);
    loadQuiz(videoId, activeTopicIdx, total);

    // Pre-load ahead (notes first since they're highest priority)
    for (let a = 1; a <= PRELOAD_AHEAD; a++) {
      const next = activeTopicIdx + a;
      if (next < total) {
        const delay = a * 600;
        setTimeout(() => {
          loadNotes(videoId, next, total);
          loadCards(videoId, next, total);
          loadQuiz(videoId, next, total);
        }, delay);
      }
    }
  }, [activeTopicIdx, transcriptData, topics, loadNotes, loadCards, loadQuiz]);

  // Poll /transcript/progress while transcribing an MP4
  useEffect(() => {
    if (!isProcessingTranscript || !pendingVideoId.current) return;
    const vid = pendingVideoId.current;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/transcript/progress/${vid}`);
        if (res.ok) {
          const prog = await res.json();
          if (prog.segments > 0 || prog.audio_pos > 0) {
            setTranscriptProgress(prog);
          }
          if (prog.done) clearInterval(interval);
        }
      } catch (_) { /* backend not ready yet */ }
    }, 2000);
    return () => clearInterval(interval);
  }, [isProcessingTranscript]);

  // ── Reset ─────────────────────────────────────────────────────────────────

  const resetAll = () => {
    setTranscriptData(null); setTopics([]); setActiveTopicIdx(-1);
    setNotes([]); setFlashcards([]); setQuiz([]);
    setOverallSummary(null); setIsLoadingSummary(false);
    setActiveTab('notes'); setLoadingNotes({}); setLoadingCards({}); setLoadingQuiz({});
    reqNotes.current.clear(); reqCards.current.clear(); reqQuiz.current.clear();
    setError(null);
    setTranscriptProgress(null);
    pendingVideoId.current = null;
  };

  const handleSubmit = async (params) => {
    resetAll();
    setLocalVideoUrl(null);  // clear any old blob
    if (params.errorOverride) { setError(params.errorOverride); return; }
    if (params.triggerValidationOnly) { setError('Unsupported file.'); return; }

    // Instantly create a blob URL so the video player shows while processing
    if (params.file) {
      setLocalVideoUrl(URL.createObjectURL(params.file));
    }

    // Pre-generate a video_id for MP4 uploads so progress polling starts immediately
    const preVideoId = params.file
      ? crypto.randomUUID()
      : null;
    if (preVideoId) pendingVideoId.current = preVideoId;

    setIsProcessingTranscript(true);
    try {
      const data = await fetchTranscript({
        youtubeUrl: params.youtubeUrl,
        file: params.file,
        videoId: preVideoId,
      });
      setTranscriptData(data);
      setIsProcessingTranscript(false);

      if (data?.video_id) {
        setIsProcessingTopics(true);
        try {
          const processed = await processVideo(data.video_id);
          const loadedTopics = processed.topics || [];
          setTopics(loadedTopics);
          setActiveTopicIdx(-1);
          saveSession(data.video_id, loadedTopics);
        } catch (e) {
          setError(e.message || 'Topic extraction failed.');
        } finally {
          setIsProcessingTopics(false);
        }
      }
    } catch (e) {
      setError(e.message || 'Unable to fetch transcript.');
      setIsProcessingTranscript(false);
    }
  };

  const videoId = transcriptData?.video_id ?? null;
  const activeTopic = topics[activeTopicIdx];
  const isLoadingNotes = !!loadingNotes[activeTopicIdx];
  const isLoadingFlashcards = !!loadingCards[activeTopicIdx];
  const isLoadingQuiz = !!loadingQuiz[activeTopicIdx];
  const anyBackgroundLoading = Object.values(loadingNotes).some(Boolean) ||
    Object.values(loadingCards).some(Boolean) || Object.values(loadingQuiz).some(Boolean);

  return (
    <div className="min-h-screen bg-[#0B0B0B] text-[#F5F5F5] flex flex-col items-center justify-start px-4 py-16 sm:px-6 md:py-20">
      <div className="w-full max-w-5xl flex flex-col space-y-10">

        {/* Header */}
        <div className="text-center space-y-3">
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-[#F5F5F5] select-none">
            LearnForge AI
          </h1>
          <p className="text-sm text-[#525252] max-w-lg mx-auto">
            Transform educational videos into structured study guides
          </p>
          <div className="flex items-center justify-center gap-3">
            <button
              onClick={() => navigate('/dashboard')}
              className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium text-[#737373] border border-[#262626] rounded-full hover:border-[#7C3AED]/40 hover:text-[#7C3AED] transition-all"
            >
              📊 Dashboard
            </button>
          </div>
        </div>

        {/* Upload */}
        <UploadBox
          onSubmit={handleSubmit}
          isProcessing={isProcessingTranscript || isProcessingTopics}
          error={error}
          onClearError={() => setError(null)}
        />

        {isProcessingTranscript && <LoadingState phase="transcript" progress={transcriptProgress} />}
        {isProcessingTopics && <LoadingState phase="topics" />}
        {/* TopicProcessor only for error display */}
        {!isProcessingTopics && <TopicProcessor isProcessing={false} error={null} />}

        {/* Main study panel */}
        {!isProcessingTranscript && !isProcessingTopics && transcriptData && (
          <div className="w-full flex flex-col gap-6">

            {/* Video Player */}
            {(localVideoUrl || transcriptData?.youtube_video_id || (videoId && !transcriptData?.youtube_video_id)) && (
              <div
                ref={videoWrapperRef}
                className="w-full max-w-3xl mx-auto bg-black rounded-xl overflow-hidden border border-[#2a2a2a] shadow-lg flex justify-center transition-all mb-4"
              >
                {transcriptData?.youtube_video_id ? (
                  <iframe
                    src={`https://www.youtube.com/embed/${transcriptData.youtube_video_id}?enablejsapi=1`}
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                    allowFullScreen
                    style={{ width: '100%', aspectRatio: '16/9', border: 'none' }}
                  />
                ) : (
                  <video
                    ref={videoRef}
                    src={localVideoUrl || (videoId ? getVideoUrl(videoId) : '')}
                    controls
                    preload="metadata"
                    style={{ width: '100%', display: 'block', background: '#000' }}
                  />
                )}
              </div>
            )}

            {/* Toolbar */}
            <div className="flex items-center justify-end gap-2">
              {anyBackgroundLoading && (
                <span className="flex items-center gap-1.5 text-[10px] text-emerald-400/60 mr-auto">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Loading remaining topics in background…
                </span>
              )}
              {videoId && (
                <button
                  onClick={() => navigate('/dashboard')}
                  className="px-3 py-1.5 text-xs font-medium text-[#737373] border border-[#262626] rounded-lg hover:border-[#7C3AED]/40 hover:text-[#7C3AED] transition-all"
                >
                  📊 Dashboard
                </button>
              )}
              {videoId && (
                <button
                  onClick={() => setShowDebug(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono text-amber-400/60 border border-amber-400/20 rounded-lg bg-amber-400/5 hover:bg-amber-400/10 hover:text-amber-400 transition-all"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                  Debug
                </button>
              )}
            </div>

            {/* Mobile topic dropdown */}
            {topics.length > 0 && (
              <div className="md:hidden">
                <TopicDropdown topics={topics} activeTopicIdx={activeTopicIdx} onTopicClick={setActiveTopicIdx} />
              </div>
            )}

            {/* Panel */}
            <div className="w-full flex flex-col bg-[#111111] border border-[#1e1e1e] rounded-xl overflow-hidden shadow-2xl">
              {/* Column header */}
              {topics.length > 0 && (
                <div className="hidden md:flex items-center border-b border-[#1e1e1e] text-[10px] font-bold tracking-widest text-[#404040] uppercase">
                  <div className="w-[260px] shrink-0 border-r border-[#1e1e1e] px-5 py-3">Topics</div>
                  <div className="flex-1 px-5 py-3">Study Space</div>
                </div>
              )}

              <div className="flex">
                {topics.length > 0 && (
                  <div className="hidden md:block">
                    <TopicSidebar
                      topics={topics}
                      activeTopicIdx={activeTopicIdx}
                      onTopicClick={setActiveTopicIdx}
                      videoId={videoId}
                    />
                  </div>
                )}

                <TranscriptViewer
                  topics={topics}
                  activeTopicIdx={activeTopicIdx}
                  activeTab={activeTab}
                  setActiveTab={setActiveTab}
                  notes={notes}
                  flashcards={flashcards}
                  quiz={quiz}
                  isLoadingNotes={isLoadingNotes}
                  isLoadingFlashcards={isLoadingFlashcards}
                  isLoadingQuiz={isLoadingQuiz}
                  videoId={videoId}
                  overallSummary={overallSummary}
                  isLoadingSummary={isLoadingSummary}
                  onTopicClick={setActiveTopicIdx}
                  transcriptData={transcriptData}
                  onPlayVideo={handlePlayVideo}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Floating AI tutor */}
      {videoId && (
        <FloatingAI
          videoId={videoId}
          topicIndex={activeTopicIdx}
          topicTitle={activeTopic?.title ?? ''}
        />
      )}

      {/* Debug overlay */}
      {showDebug && videoId && (
        <div className="fixed inset-0 z-50">
          <DebugViewer videoId={videoId} />
          <button
            onClick={() => setShowDebug(false)}
            className="fixed top-4 right-4 z-[60] px-3 py-1.5 text-xs font-semibold bg-[#1a1a1a] border border-[#404040] rounded-lg text-[#A3A3A3] hover:text-[#F5F5F5] transition-all"
          >✕ Close</button>
        </div>
      )}
    </div>
  );
}

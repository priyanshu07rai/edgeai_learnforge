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
import ThemeToggle from '../components/ThemeToggle';
import { fetchTranscript, processVideo, generateNotesForTopic, generateFlashcardsForTopic, generateQuizForTopic, fetchOverallSummary, getVideoUrl } from '../services/api';
import { saveSession } from './DashboardPage';

const PRELOAD_AHEAD = 2;
const API_BASE = import.meta.env.VITE_API_BASE_URL !== undefined ? import.meta.env.VITE_API_BASE_URL : '';
const TRANSCRIPT_CACHE_KEY = 'lf_transcript_cache';

function getTranscriptCache() {
  try {
    const raw = sessionStorage.getItem(TRANSCRIPT_CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function getSession() {
  try {
    const raw = sessionStorage.getItem('lf_session');
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}


function saveTranscriptCache(data, topicsList, activeIdx = -1) {
  try {
    sessionStorage.setItem(TRANSCRIPT_CACHE_KEY, JSON.stringify({
      transcriptData: data,
      topics: topicsList,
      activeTopicIdx: activeIdx
    }));
  } catch {}
}

function clearTranscriptCache() {
  try {
    sessionStorage.removeItem(TRANSCRIPT_CACHE_KEY);
  } catch {}
}

export default function TranscriptPage() {
  const navigate = useNavigate();

  const [isProcessingTranscript, setIsProcessingTranscript] = useState(false);
  const [isProcessingTopics, setIsProcessingTopics] = useState(false);
  const [error, setError] = useState(null);

  const cachedSession = getTranscriptCache();
  const [transcriptData, setTranscriptData] = useState(cachedSession?.transcriptData ?? null);
  const [topics, setTopics] = useState(cachedSession?.topics ?? []);
  const [activeTopicIdx, setActiveTopicIdx] = useState(cachedSession?.activeTopicIdx ?? -1);
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
  const videoRef = useRef(null);
  const videoWrapperRef = useRef(null);
  const [localVideoUrl, setLocalVideoUrl] = useState(null);
  const [isPiP, setIsPiP] = useState(false);
  const [dismissPiP, setDismissPiP] = useState(false);

  useEffect(() => {
    if (!videoWrapperRef.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) {
          setIsPiP(true);
        } else {
          setIsPiP(false);
          setDismissPiP(false);
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(videoWrapperRef.current);
    return () => observer.disconnect();
  }, [transcriptData, localVideoUrl]);

  useEffect(() => {
    return () => { if (localVideoUrl) URL.revokeObjectURL(localVideoUrl); };
  }, [localVideoUrl]);

  // Restore session from sessionStorage on mount if state is empty but videoId exists
  useEffect(() => {
    const session = getSession();
    const vid = session?.videoId;
    if (vid && !transcriptData) {
      setIsProcessingTranscript(true);
      fetch(`${API_BASE}/transcript/cached/${vid}`)
        .then(res => {
          if (!res.ok) throw new Error('Not found');
          return res.json();
        })
        .then(data => {
          setTranscriptData(data);
          setTopics(session.topics || []);
          setActiveTopicIdx(session.topics?.length ? 0 : -1);
        })
        .catch(err => {
          console.error('[Session Restore] Failed:', err);
          clearTranscriptCache();
          sessionStorage.removeItem('lf_session');
        })
        .finally(() => {
          setIsProcessingTranscript(false);
        });
    }
  }, []);


  const handlePlayVideo = useCallback((timeSecs) => {
    if (videoWrapperRef.current) {
      const y = videoWrapperRef.current.getBoundingClientRect().top + window.scrollY - 20;
      window.scrollTo({ top: y, behavior: 'smooth' });
    }
    const vid = videoRef.current;
    if (vid) {
      vid.currentTime = timeSecs;
      vid.play().catch(() => {});
    }
  }, []);

  const [transcriptProgress, setTranscriptProgress] = useState(null);
  const pendingVideoId = useRef(null);

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

    loadNotes(videoId, activeTopicIdx, total);
    loadCards(videoId, activeTopicIdx, total);
    loadQuiz(videoId, activeTopicIdx, total);

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
      } catch (_) {}
    }, 2000);
    return () => clearInterval(interval);
  }, [isProcessingTranscript]);

  const resetAll = () => {
    clearTranscriptCache();
    setTranscriptData(null); setTopics([]); setActiveTopicIdx(-1);
    setNotes([]); setFlashcards([]); setQuiz([]);
    setOverallSummary(null); setIsLoadingSummary(false);
    setActiveTab('notes'); setLoadingNotes({}); setLoadingCards({}); setLoadingQuiz({});
    reqNotes.current.clear(); reqCards.current.clear(); reqQuiz.current.clear();
    setError(null);
    setTranscriptProgress(null);
    pendingVideoId.current = null;
  };

  const handleTopicSelect = (idx) => {
    setActiveTopicIdx(idx);
    saveTranscriptCache(transcriptData, topics, idx);
  };

  const handleSubmit = async (params) => {
    resetAll();
    setLocalVideoUrl(null);
    if (params.errorOverride) { setError(params.errorOverride); return; }
    if (params.triggerValidationOnly) { setError('Unsupported file.'); return; }

    if (params.file) {
      setLocalVideoUrl(URL.createObjectURL(params.file));
    }

    const preVideoId = params.file ? crypto.randomUUID() : null;
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
          setActiveTopicIdx(loadedTopics.length ? 0 : -1);
          saveSession(data.video_id, loadedTopics);
          saveTranscriptCache(data, loadedTopics, loadedTopics.length ? 0 : -1);
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

  return (
    <div className="min-h-screen bg-[#F1F5F9] dark:bg-[#0B0B0B] text-slate-900 dark:text-[#F5F5F5] flex flex-col items-center justify-start px-4 py-8 sm:px-6 md:py-12 transition-colors duration-300">
      <div className="w-full max-w-6xl flex flex-col space-y-8">

        {/* Top Header & Theme Toggle */}
        <div className="flex flex-col items-center text-center space-y-3">
          <ThemeToggle />
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-slate-900 dark:text-[#F5F5F5] select-none">
            LearnForge AI
          </h1>
          <p className="text-sm font-semibold text-slate-600 dark:text-[#A3A3A3] max-w-lg mx-auto">
            Transform educational videos into interactive study guides
          </p>

          {/* Action Pills */}
          <div className="flex items-center justify-center gap-3 pt-2">
            <button
              onClick={() => navigate('/dashboard')}
              className="flex items-center gap-2 px-5 py-2 text-xs font-extrabold text-white bg-indigo-600 hover:bg-indigo-700 dark:bg-[#7C3AED] dark:hover:bg-[#6D28D9] rounded-xl shadow-md transition-all cursor-pointer"
            >
              📊 Analytics Dashboard
            </button>
            {transcriptData && (
              <button
                onClick={resetAll}
                className="flex items-center gap-2 px-4 py-2 text-xs font-bold text-slate-700 dark:text-[#A3A3A3] bg-white dark:bg-[#111] border-2 border-slate-300 dark:border-[#262626] rounded-xl hover:border-indigo-500 hover:text-indigo-600 dark:hover:text-white shadow-sm transition-all cursor-pointer"
              >
                ➕ Process Another Video
              </button>
            )}
          </div>
        </div>

        {/* Upload Box (Shown when no active transcript is loaded) */}
        {!transcriptData && !isProcessingTranscript && !isProcessingTopics && (
          <UploadBox
            onSubmit={handleSubmit}
            isProcessing={isProcessingTranscript || isProcessingTopics}
            error={error}
            onClearError={() => setError(null)}
          />
        )}

        {isProcessingTranscript && <LoadingState phase="transcript" progress={transcriptProgress} />}
        {isProcessingTopics && <LoadingState phase="topics" />}
        {!isProcessingTopics && <TopicProcessor isProcessing={false} error={null} />}

        {/* Main study panel */}
        {!isProcessingTranscript && !isProcessingTopics && transcriptData && (
          <div className="w-full flex flex-col gap-6">

            {/* Video Player */}
            {(localVideoUrl || transcriptData?.youtube_video_id || (videoId && !transcriptData?.youtube_video_id)) && (
              <div ref={videoWrapperRef} className="w-full max-w-4xl mx-auto mb-4 relative">
                {isPiP && !dismissPiP && (
                  <div className="w-full h-[360px] rounded-2xl border-2 border-dashed border-slate-300 dark:border-[#262626] bg-slate-100 dark:bg-[#0d0d0d] flex flex-col items-center justify-center gap-2 text-xs font-bold text-slate-600 dark:text-[#525252]">
                    <span>🎬 Video playing in mini player below</span>
                    <button
                      onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
                      className="px-3 py-1.5 text-[11px] font-extrabold text-indigo-700 bg-indigo-100 dark:text-purple-400 dark:bg-purple-500/10 border border-indigo-300 dark:border-purple-500/20 rounded-lg hover:bg-indigo-200 transition-all cursor-pointer"
                    >
                      Scroll to Top
                    </button>
                  </div>
                )}

                <div
                  className={
                    isPiP && !dismissPiP
                      ? "fixed bottom-6 left-6 z-50 w-80 sm:w-96 bg-white dark:bg-[#0a0a0a] rounded-2xl overflow-hidden border-2 border-indigo-500 dark:border-[#7C3AED]/50 shadow-2xl shadow-indigo-500/30 transition-all duration-300 flex flex-col"
                      : "w-full bg-black rounded-2xl overflow-hidden border-2 border-slate-300 dark:border-[#2a2a2a] shadow-xl flex flex-col justify-center transition-all"
                  }
                >
                  {isPiP && !dismissPiP && (
                    <div className="flex items-center justify-between px-3 py-1.5 bg-slate-100 dark:bg-[#141414] border-b border-slate-200 dark:border-[#262626]">
                      <span className="flex items-center gap-1.5 text-indigo-700 dark:text-purple-400 font-extrabold text-[11px]">
                        <span className="w-2 h-2 rounded-full bg-indigo-600 dark:bg-purple-500 animate-pulse" />
                        Mini Player
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
                          className="text-[10px] text-indigo-600 dark:text-[#A3A3A3] hover:underline font-bold"
                        >
                          Expand
                        </button>
                        <button
                          onClick={() => setDismissPiP(true)}
                          className="text-[11px] text-slate-500 dark:text-[#525252] hover:text-slate-900 dark:hover:text-white font-bold"
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  )}

                  {localVideoUrl ? (
                    <video
                      ref={videoRef}
                      src={localVideoUrl}
                      controls
                      className="w-full aspect-video object-contain bg-black"
                    />
                  ) : transcriptData?.youtube_video_id ? (
                    <iframe
                      src={`https://www.youtube.com/embed/${transcriptData.youtube_video_id}`}
                      title={transcriptData.title || "YouTube Video"}
                      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                      allowFullScreen
                      className="w-full aspect-video border-none"
                    />
                  ) : (
                    <video
                      ref={videoRef}
                      src={getVideoUrl(videoId)}
                      controls
                      className="w-full aspect-video object-contain bg-black"
                    />
                  )}
                </div>
              </div>
            )}

            {/* Mobile topic dropdown */}
            <TopicDropdown
              topics={topics}
              activeTopicIdx={activeTopicIdx}
              onTopicClick={handleTopicSelect}
            />

            {/* 2-Column layout: Sidebar + Study Space */}
            <div className="flex gap-6 items-start">
              <TopicSidebar
                topics={topics}
                activeTopicIdx={activeTopicIdx}
                onTopicClick={handleTopicSelect}
                videoId={videoId}
                overallSummary={overallSummary}
                isLoadingSummary={isLoadingSummary}
              />


              <div className="flex-1 bg-white dark:bg-[#111111] border-2 border-slate-300 dark:border-[#262626] rounded-3xl p-6 shadow-xl shadow-slate-200/50 dark:shadow-2xl">
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
                  onTopicClick={handleTopicSelect}
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
          topicTitle={activeTopic?.title ?? (activeTopicIdx === -1 ? 'Full Video' : '')}
        />
      )}
    </div>
  );
}

/**
 * progress.js — localStorage helpers for tracking learning progress.
 * Handles: quiz results, topic completion, flashcard reviews, difficulty settings.
 */

const KEY = (videoId) => `lf_progress_${videoId}`;

const _get = (videoId) => {
  try {
    const raw = localStorage.getItem(KEY(videoId));
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
};

const _set = (videoId, data) => {
  try {
    localStorage.setItem(KEY(videoId), JSON.stringify(data));
  } catch {}
};

// ── Quiz Results ──────────────────────────────────────────────────────────────

/**
 * Save quiz result for a topic.
 * @param {string} videoId
 * @param {number} topicIdx
 * @param {number} correct - number of correct answers
 * @param {number} total   - total questions
 */
export function saveQuizResult(videoId, topicIdx, correct, total) {
  const data = _get(videoId);
  if (!data.quizResults) data.quizResults = {};
  data.quizResults[topicIdx] = {
    correct,
    total,
    accuracy: total > 0 ? Math.round((correct / total) * 100) : 0,
    timestamp: Date.now(),
  };
  _set(videoId, data);
}

/**
 * Get quiz result for a topic.
 * Returns null if not attempted.
 */
export function getQuizResult(videoId, topicIdx) {
  const data = _get(videoId);
  return data.quizResults?.[topicIdx] ?? null;
}

/**
 * Get all quiz results for a video.
 * @returns { [topicIdx]: { correct, total, accuracy } }
 */
export function getAllQuizResults(videoId) {
  return _get(videoId).quizResults ?? {};
}

// ── Topic Completion ──────────────────────────────────────────────────────────

/**
 * Mark a topic as viewed (completed notes).
 */
export function markTopicViewed(videoId, topicIdx) {
  const data = _get(videoId);
  if (!data.viewedTopics) data.viewedTopics = [];
  if (!data.viewedTopics.includes(topicIdx)) {
    data.viewedTopics.push(topicIdx);
  }
  _set(videoId, data);
}

export function getViewedTopics(videoId) {
  return _get(videoId).viewedTopics ?? [];
}

// ── Flashcard Reviews ─────────────────────────────────────────────────────────

/**
 * Record a flashcard review.
 */
export function recordFlashcardReview(videoId, topicIdx) {
  const data = _get(videoId);
  if (!data.flashcardReviews) data.flashcardReviews = {};
  data.flashcardReviews[topicIdx] = (data.flashcardReviews[topicIdx] ?? 0) + 1;
  _set(videoId, data);
}

export function getTotalFlashcardReviews(videoId) {
  const data = _get(videoId).flashcardReviews ?? {};
  return Object.values(data).reduce((sum, n) => sum + n, 0);
}

// ── Difficulty ────────────────────────────────────────────────────────────────

export function saveDifficulty(videoId, difficulty) {
  const data = _get(videoId);
  data.difficulty = difficulty;
  _set(videoId, data);
}

export function getDifficulty(videoId) {
  return _get(videoId).difficulty ?? 'intermediate';
}

// ── Dashboard Summary ─────────────────────────────────────────────────────────

/**
 * Compute a full summary for the dashboard.
 * @param {string} videoId
 * @param {number} totalTopics
 */
export function getDashboardSummary(videoId, totalTopics) {
  const data = _get(videoId);
  const quizResults = data.quizResults ?? {};
  const viewedTopics = data.viewedTopics ?? [];
  const flashcardReviews = data.flashcardReviews ?? {};

  const attempted = Object.keys(quizResults).length;
  const totalCorrect = Object.values(quizResults).reduce((s, r) => s + r.correct, 0);
  const totalQs = Object.values(quizResults).reduce((s, r) => s + r.total, 0);
  const avgAccuracy = totalQs > 0 ? Math.round((totalCorrect / totalQs) * 100) : 0;

  const weakTopics = Object.entries(quizResults)
    .filter(([, r]) => r.accuracy < 60)
    .map(([idx]) => parseInt(idx));

  const strongTopics = Object.entries(quizResults)
    .filter(([, r]) => r.accuracy >= 80)
    .map(([idx]) => parseInt(idx));

  const completionPct = totalTopics > 0
    ? Math.round((viewedTopics.length / totalTopics) * 100)
    : 0;

  const totalReviews = Object.values(flashcardReviews).reduce((s, n) => s + n, 0);

  return {
    totalTopics,
    viewedTopics: viewedTopics.length,
    completionPct,
    quizAttempted: attempted,
    avgAccuracy,
    weakTopics,
    strongTopics,
    totalFlashcardReviews: totalReviews,
    difficulty: data.difficulty ?? 'intermediate',
  };
}

/**
 * Get accuracy status for a specific topic.
 * Returns: 'weak' | 'medium' | 'strong' | 'unattempted'
 */
export function getTopicAccuracyStatus(videoId, topicIdx) {
  const result = getQuizResult(videoId, topicIdx);
  if (!result) return 'unattempted';
  if (result.accuracy < 60) return 'weak';
  if (result.accuracy < 80) return 'medium';
  return 'strong';
}

/**
 * Clear all progress for a video (reset).
 */
export function clearProgress(videoId) {
  try {
    localStorage.removeItem(KEY(videoId));
  } catch {}
}

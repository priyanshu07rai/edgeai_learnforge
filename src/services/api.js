import axios from 'axios';

// Configure base URL from environment variables if present
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 90000, // 90 seconds timeout for quick endpoints
});

// No timeout for file uploads — Whisper transcription can take many minutes
const uploadClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 0, // unlimited — Whisper may take 5–15+ min for long videos
});

// Long timeout for /process — topic segmentation + FAISS indexing can take minutes
const processClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 1200000, // 20 minutes
});

/**
 * Sends a request to POST /transcript
 * @param {Object} params
 * @param {string} [params.youtubeUrl]
 * @param {File} [params.file]
 * @returns {Promise<{video_id: string, transcript: string, duration: number, segments: Array}>}
 */
export const fetchTranscript = async ({ youtubeUrl, file, videoId }) => {
  try {
    if (file) {
      const isMp4 = file.name.toLowerCase().endsWith('.mp4') || file.type === 'video/mp4';
      if (!isMp4) {
        throw new Error('Unsupported file.');
      }

      // MP4 uploads require multipart form data
      const formData = new FormData();
      formData.append('file', file);
      // Send pre-generated video_id so backend progress can be polled immediately
      if (videoId) formData.append('video_id', videoId);

      // Use uploadClient (no timeout) — Whisper can take many minutes for long videos
      const response = await uploadClient.post('/transcript', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return response.data;
    } else if (youtubeUrl) {
      const isYoutube = youtubeUrl.includes('youtube.com') || youtubeUrl.includes('youtu.be');
      if (!isYoutube) {
        throw new Error('Unsupported file.');
      }

      // FastAPI Form uploads youtube_url as a Form field or application/x-www-form-urlencoded
      const formData = new FormData();
      formData.append('youtube_url', youtubeUrl);

      const response = await apiClient.post('/transcript', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return response.data;
    } else {
      throw new Error('Unable to fetch transcript.');
    }
  } catch (error) {
    if (error.response) {
      const status = error.response.status;
      const detail = error.response.data?.detail || '';

      if (status === 413 || detail.toLowerCase().includes('too long')) {
        throw new Error('Video too long.');
      }
      if (status === 400 && detail.toLowerCase().includes('unsupported')) {
        throw new Error('Unsupported file.');
      }
      // Show the actual error from backend if it's informative
      if (detail && detail.length < 200) {
        throw new Error(detail);
      }
      throw new Error('Unable to fetch transcript.');
    }
    
    if (error.message === 'Unsupported file.' || error.message === 'Video too long.') {
      throw error;
    }

    // Network error — backend is likely down
    if (error.code === 'ERR_NETWORK' || error.code === 'ECONNREFUSED') {
      throw new Error('Cannot connect to server. Please make sure the backend is running.');
    }

    // Axios timeout
    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      throw new Error('Transcription timed out. The video may be too long. Please try a shorter clip.');
    }

    throw new Error('Unable to fetch transcript.');
  }
};

/**
 * Sends a request to POST /process to segment topics and build the FAISS index
 * @param {string} videoId 
 * @returns {Promise<{topic_count: number, topics: Array}>}
 */
export const processVideo = async (videoId) => {
  try {
    // Use processClient (20-min timeout) — topic segmentation + FAISS can be slow
    const response = await processClient.post('/process', {
      video_id: videoId
    }, {
      headers: {
        'Content-Type': 'application/json',
      }
    });
    return response.data;
  } catch (error) {
    if (error.response) {
      const status = error.response.status;
      const detail = error.response.data?.detail || '';

      if (status === 404) {
        throw new Error('Unable to process transcript.');
      }
      if (detail.includes('extraction')) {
        throw new Error('Topic extraction failed.');
      }
      if (detail.includes('Index')) {
        throw new Error('Index creation failed.');
      }
    }
    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      throw new Error('Topic processing timed out. Please try again.');
    }
    throw new Error('Unable to process transcript.');
  }
};

/**
 * Sends a request to POST /notes/generate
 * @param {string} videoId 
 * @returns {Promise<{topics: Array}>}
 */
export const generateNotes = async (videoId) => {
  try {
    const response = await apiClient.post('/notes/generate', {
      video_id: videoId
    }, {
      headers: {
        'Content-Type': 'application/json',
      }
    });
    return response.data;
  } catch (error) {
    throw new Error('Notes generation failed.');
  }
};

/**
 * Sends a request to POST /flashcards/generate
 * @param {string} videoId 
 * @returns {Promise<{topics: Array}>}
 */
export const generateFlashcards = async (videoId) => {
  try {
    const response = await apiClient.post('/flashcards/generate', {
      video_id: videoId
    }, {
      headers: {
        'Content-Type': 'application/json',
      }
    });
    return response.data;
  } catch (error) {
    throw new Error('Flashcards generation failed.');
  }
};

/**
 * Sends a request to POST /quiz/generate
 * @param {string} videoId 
 * @returns {Promise<{topics: Array}>}
 */
export const generateQuiz = async (videoId) => {
  try {
    const response = await apiClient.post('/quiz/generate', {
      video_id: videoId
    }, {
      headers: {
        'Content-Type': 'application/json',
      }
    });
    return response.data;
  } catch (error) {
    throw new Error('Quiz generation failed.');
  }
};


// ── Per-topic streaming API (progressive loading) ─────────────────────────────

/**
 * Generate notes for ONE specific topic.
 * @param {string} videoId
 * @param {number} topicIndex
 * @returns {Promise<{topic, topic_index, summary, key_points, important_terms}>}
 */
export const generateNotesForTopic = async (videoId, topicIndex) => {
  const response = await apiClient.post('/notes/topic', {
    video_id: videoId,
    topic_index: topicIndex,
  }, { headers: { 'Content-Type': 'application/json' } });
  return response.data;
};

/**
 * Generate flashcards for ONE specific topic.
 * @param {string} videoId
 * @param {number} topicIndex
 * @returns {Promise<{topic, topic_index, cards}>}
 */
export const generateFlashcardsForTopic = async (videoId, topicIndex) => {
  const response = await apiClient.post('/flashcards/topic', {
    video_id: videoId,
    topic_index: topicIndex,
  }, { headers: { 'Content-Type': 'application/json' } });
  return response.data;
};

/**
 * Generate quiz for ONE specific topic.
 * @param {string} videoId
 * @param {number} topicIndex
 * @returns {Promise<{topic, topic_index, quiz}>}
 */
export const generateQuizForTopic = async (videoId, topicIndex) => {
  const response = await apiClient.post('/quiz/topic', {
    video_id: videoId,
    topic_index: topicIndex,
  }, { headers: { 'Content-Type': 'application/json' } });
  return response.data;
};


/**
 * Fetch overall MapReduce summary for a video.
 * @param {string} videoId
 * @returns {Promise<{title: string, cohesive_summary: string, key_takeaways: Array<string>}>}
 */
export const fetchOverallSummary = async (videoId) => {
  // Use processClient (20m timeout) because MapReduce on a 1-hour video can take ~2-3 mins.
  const response = await processClient.get(`/summary/${videoId}`);
  return response.data;
};




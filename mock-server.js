import express from 'express';
import cors from 'cors';
import multer from 'multer';
import { v4 as uuidv4 } from 'uuid';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = 3000;

app.use(cors());
app.use(express.json());

// Create storage and upload directory structures
const STORAGE_DIR = path.join(__dirname, 'storage');
if (!fs.existsSync(STORAGE_DIR)) {
  fs.mkdirSync(STORAGE_DIR, { recursive: true });
}

const UPLOADS_DIR = path.join(__dirname, 'uploads');
if (!fs.existsSync(UPLOADS_DIR)) {
  fs.mkdirSync(UPLOADS_DIR, { recursive: true });
}

// Multer storage
const upload = multer({ dest: 'uploads/' });

app.post('/transcript', upload.single('file'), (req, res) => {
  const videoId = uuidv4();
  let transcript = '';
  let duration = 65.5;

  if (req.file) {
    const filename = req.file.originalname;
    // Check if mp4
    if (!filename.toLowerCase().endsWith('.mp4')) {
      return res.status(400).json({ message: 'Unsupported file.' });
    }
    
    transcript = `[00:00] [System Log: Processing raw audio from file "${filename}"]
[00:04] This is the raw transcript extracted from the uploaded MP4 source.
[00:10] For Phase 2, we will partition this text file into discrete topic boundaries.
[00:16] Once chunked, we pass these vectors through the sentence-transformers model.
[00:22] A FAISS index is built on disk to allow semantic querying later.
[00:30] LearnForge AI maintains zero complexity in the user viewport.
[00:36] All technical artifacts, like embeddings, are hidden from developer view.
[00:44] The system processes files without analytical overlays or charts.`;
    duration = 120.0;
    
    // Remove the temp file
    try {
      fs.unlinkSync(req.file.path);
    } catch (e) {
      // Ignore cleanup error
    }
  } else if (req.body && req.body.youtube_url) {
    const url = req.body.youtube_url;
    const isYoutube = url.includes('youtube.com') || url.includes('youtu.be');
    if (!isYoutube) {
      return res.status(400).json({ message: 'Unsupported file.' });
    }
    
    transcript = `[00:00] [System Log: Resolving feed stream from YouTube URL]
[00:05] Initiating transcribing process for URL query parameters.
[00:12] We map audio frames directly to text embeddings in our server storage.
[00:20] The backend persists these JSON maps into structural files under storage.
[00:28] Each segment contains start and end boundaries for precise indexing.
[00:35] When a topic partition is selected, the frontend triggers anchors to scroll.
[00:43] Phase 2 will execute segment classification using Llama 3.2.`;
    duration = 180.0;
  } else {
    return res.status(400).json({ message: 'Unable to fetch transcript.' });
  }

  const responsePayload = {
    video_id: videoId,
    transcript: transcript,
    duration: duration,
    segments: [
      { start: 0, end: 10, text: "Intro segment" },
      { start: 10, end: 40, text: "Technical segment" }
    ]
  };

  // Persist into storage/<video_id>/transcript.json
  const videoDir = path.join(STORAGE_DIR, videoId);
  try {
    fs.mkdirSync(videoDir, { recursive: true });
    fs.writeFileSync(
      path.join(videoDir, 'transcript.json'),
      JSON.stringify(responsePayload, null, 2),
      'utf-8'
    );
  } catch (err) {
    console.error('Failed to write transcript to storage:', err);
  }

  return res.json(responsePayload);
});

app.listen(PORT, () => {
  console.log(`Mock transcript server running at http://localhost:${PORT}`);
});

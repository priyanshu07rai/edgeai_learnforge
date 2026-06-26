# LearnForge AI 🧠⚙️

**Transform educational videos into structured, interactive study guides using Local AI.**

LearnForge AI is an advanced, edge-AI powered educational application designed to process long-form lectures, tutorials, and educational videos. By leveraging local transcription and Large Language Models, it breaks down hours of video content into digestible knowledge units, comprehensive notes, flashcards, quizzes, and even provides an interactive AI tutor for Q&A.

![LearnForge Hero](src/assets/hero.png) *(UI Screenshot / Placeholder)*

---

## ✨ Key Features

* **Multi-Source Video Ingestion:** Upload local `.mp4` files or provide a YouTube URL. LearnForge handles both seamlessly.
* **Edge-Optimized Local Transcription:** Utilizes `faster_whisper` optimized for CPU (`beam_size=1`) to transcribe audio locally. It includes intelligent auto-translation (e.g., automatically translating Hindi chemistry lectures into clean English).
* **Semantic Topic Segmentation:** Dynamically chunks the video into logical "Knowledge Units" using heuristic modeling and semantic boundary detection, extracting meaningful topic titles based on the actual transcript content.
* **Automated Study Materials (RAG pipeline):** 
  * 📝 **Detailed Notes:** In-depth summaries, key points, and terminology for each topic.
  * 📇 **Flashcards:** Auto-generated Q&A cards for active recall testing.
  * 🎯 **Quizzes:** Multiple-choice questions to test your comprehension.
* **Ask AI (Interactive RAG Tutor):** Chat with your video! LearnForge builds a local `FAISS` vector database from the transcript. Ask questions, and the AI will answer using *only* the context from the video.
* **MapReduce Summarization:** Processes hour-long videos into a cohesive, high-level summary using parallel threaded LLM chunking.

---

## 🛠️ Tech Stack

### Frontend
* **Framework:** React 19 + Vite
* **Styling:** Tailwind CSS v4
* **Routing:** React Router v7
* **HTTP Client:** Axios (Custom tuned interceptors for long-polling tasks)
* **Icons:** Lucide React

### Backend (Local AI Engine)
* **Framework:** FastAPI / Uvicorn (Python)
* **Transcription:** `faster_whisper` (Tiny model, optimized for local CPU inference)
* **Vector Database:** `FAISS` (Facebook AI Similarity Search) + `sentence-transformers` (all-MiniLM-L6-v2)
* **NLP & Processing:** `spaCy` (text cleaning), `youtube-transcript-api` (YouTube scraping)
* **LLM Integration:** 
  * Primary: Local **Ollama** (`llama3.2:1b`) for complete offline privacy.
  * Fallback: Google **Gemini API** for cloud processing if local LLM is offline.

---

## 🚀 Getting Started

### Prerequisites
* Node.js (v18+)
* Python (3.9+)
* (Optional but Recommended) [Ollama](https://ollama.com/) installed locally with the `llama3.2:1b` model pulled (`ollama run llama3.2:1b`).
* (Optional) FFmpeg installed on your system PATH for local video processing.

### 1. Clone the Repository
```bash
git clone https://github.com/priyanshu07rai/edgeai_learnforge.git
cd edgeai_learnforge
```

### 2. Backend Setup
```bash
# Navigate to the project root (the backend code is inside src/backend, but we run from root's venv)
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# (Optional) Create a .env file in the root if you want to use the Gemini fallback
# GEMINI_API_KEY=your_google_api_key_here

# Start the FastAPI server
cd src/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 3. Frontend Setup
Open a new terminal window:
```bash
# In the project root directory
npm install

# Start the Vite development server
npm run dev
```

### 4. Open the App
Navigate to `http://localhost:5173` in your browser. 

---

## 🧠 How the AI Pipeline Works
1. **Ingestion & ASR:** Audio is extracted via FFmpeg and transcribed using Whisper. If the audio is not in English, it automatically executes a translation pass to guarantee clean English text.
2. **Segmentation:** The raw transcript is passed through a universal heuristic segmenter that extracts noun phrases and splits the text into logical chapters.
3. **Indexing:** Transcripts are chunked (600 words, 100 overlap) and embedded into a local FAISS Vector DB.
4. **Generation:** As the user navigates, background tasks prefetch Notes, Flashcards, and Quizzes by querying the local Ollama instance (or Gemini API) with the specific semantic chunks for that topic.

---

## 🛡️ Privacy First
LearnForge is designed with an **Edge AI philosophy**. By default, if you are running Ollama locally, **zero data** (audio, text, or prompts) leaves your machine. Your educational content and queries remain 100% private.

## 📄 License
MIT License

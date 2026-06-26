import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import TranscriptPage from './pages/TranscriptPage';
import DashboardPage from './pages/DashboardPage';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<TranscriptPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
      </Routes>
    </Router>
  );
}

export default App;

import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import TranscriptPage from './pages/TranscriptPage';
import DashboardPage from './pages/DashboardPage';

function App() {
  const getBasename = () => {
    const match = window.location.pathname.match(/^\/user\/[^/]+\/proxy\/5173/);
    return match ? match[0] : '/';
  };

  return (
    <Router basename={getBasename()}>
      <Routes>
        <Route path="/" element={<TranscriptPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
      </Routes>
    </Router>
  );
}

export default App;

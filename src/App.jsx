import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from './context/ThemeContext';
import TranscriptPage from './pages/TranscriptPage';
import DashboardPage from './pages/DashboardPage';

function App() {
  const getBasename = () => {
    const match = window.location.pathname.match(/^.*\/proxy\/5173/);
    return match ? match[0] : '/';
  };

  return (
    <ThemeProvider>
      <Router basename={getBasename()}>
        <Routes>
          <Route path="/" element={<TranscriptPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
        </Routes>
      </Router>
    </ThemeProvider>
  );
}

export default App;

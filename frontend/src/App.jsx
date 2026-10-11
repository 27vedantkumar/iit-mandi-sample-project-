import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { Navbar } from './components/layout/Navbar';
import { Sidebar } from './components/layout/Sidebar';
import { IngestionModal } from './components/common/IngestionModal';

import { DashboardPage } from './pages/DashboardPage';
import { GroundedTutorPage } from './pages/GroundedTutorPage';
import { KnowledgeGraphPage } from './pages/KnowledgeGraphPage';
import { SourceExplorerPage } from './pages/SourceExplorerPage';
import { AssessmentsPage } from './pages/AssessmentsPage';
import { PlannerPage } from './pages/PlannerPage';
import { FlashcardsPage } from './pages/FlashcardsPage';
import { ExamPage } from './pages/ExamPage';
import { CodingLabPage } from './pages/CodingLabPage';
import { GamesPage } from './pages/GamesPage';

const AppLayout = () => {
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      <Navbar onOpenUpload={() => setIsUploadOpen(true)} />
      
      <div className="flex-1 flex overflow-hidden">
        <Sidebar />
        
        <main className="flex-1 overflow-y-auto">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/courses/:courseId" element={<DashboardPage />} />
            <Route path="/tutor" element={<GroundedTutorPage />} />
            <Route path="/tutor/:mode" element={<GroundedTutorPage />} />
            <Route path="/graph" element={<KnowledgeGraphPage />} />
            <Route path="/sources" element={<SourceExplorerPage />} />
            <Route path="/assessment" element={<AssessmentsPage />} />
            <Route path="/planner" element={<PlannerPage />} />
            <Route path="/flashcards" element={<FlashcardsPage />} />
            <Route path="/flashcards/:deckId" element={<FlashcardsPage />} />
            <Route path="/exams" element={<ExamPage />} />
            <Route path="/coding" element={<CodingLabPage />} />
            <Route path="/games" element={<GamesPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>

      <IngestionModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onUploadComplete={() => {
          // Re-render or refresh data
        }}
      />
    </div>
  );
};

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppLayout />
      </AuthProvider>
    </BrowserRouter>
  );
}


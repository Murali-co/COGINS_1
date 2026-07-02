import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './context/AuthContext';
import Navbar from './components/Navbar';
import Landing from './pages/Landing';
import Auth from './pages/Auth';
import Dashboard from './pages/Dashboard';
import ResumeUpload from './pages/ResumeUpload';
import SkillGap from './pages/SkillGap';
import CoverLetter from './pages/CoverLetter';
import JobBoard from './pages/JobBoard';
import JobMatch from './pages/JobMatch';
import ApplyAssistant from './pages/ApplyAssistant';
import ApplicationsHistory from './pages/ApplicationsHistory';
import CareerCopilot from './pages/CareerCopilot';
import InterviewCoach from './pages/InterviewCoach';
import VerifyEmail from './pages/VerifyEmail';
import ResendVerification from './pages/ResendVerification';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import AppliedJobs from './pages/AppliedJobs';
import VerificationSuccess from './pages/VerificationSuccess';
import { LoadingSpinner } from './components/LoadingSpinner';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

// Route protector for secure pages
const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-950 flex items-center justify-center">
        <LoadingSpinner text="Verifying credentials..." />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/auth" replace />;
  }

  return children;
};

function AppContent() {
  return (
    <div className="min-h-screen bg-dark-950 text-dark-50 flex flex-col font-sans">
      <Navbar />
      <div className="flex-grow">
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/auth" element={<Auth />} />
          
          {/* Email Verification Routes (Public) */}
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route path="/resend-verification" element={<ResendVerification />} />
          <Route path="/verification-success" element={<VerificationSuccess />} />
          
          {/* Password Reset Routes (Public) */}
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          
          {/* Protected Routes */}
          <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/upload" element={<ProtectedRoute><ResumeUpload /></ProtectedRoute>} />
          <Route path="/skill-gap" element={<ProtectedRoute><SkillGap /></ProtectedRoute>} />
          <Route path="/cover-letter" element={<ProtectedRoute><CoverLetter /></ProtectedRoute>} />
          <Route path="/jobs" element={<ProtectedRoute><JobBoard /></ProtectedRoute>} />
          <Route path="/match" element={<ProtectedRoute><JobMatch /></ProtectedRoute>} />
          <Route path="/apply-assistant" element={<ProtectedRoute><ApplyAssistant /></ProtectedRoute>} />
          <Route path="/applications" element={<ProtectedRoute><ApplicationsHistory /></ProtectedRoute>} />
          <Route path="/applied-jobs" element={<ProtectedRoute><AppliedJobs /></ProtectedRoute>} />
          <Route path="/copilot" element={<ProtectedRoute><CareerCopilot /></ProtectedRoute>} />
          <Route path="/interview" element={<ProtectedRoute><InterviewCoach /></ProtectedRoute>} />
          
          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
      
      {/* Toast Notification Container */}
      <Toaster 
        position="top-right" 
        toastOptions={{
          className: 'glass-panel text-dark-50 border border-dark-800 text-xs font-semibold py-3 px-4 rounded-xl',
          style: {
            background: 'rgba(15, 23, 42, 0.9)',
            backdropFilter: 'blur(8px)',
            color: '#f8fafc',
            border: '1px solid rgba(255, 255, 255, 0.08)'
          },
          success: {
            iconTheme: {
              primary: '#34d399',
              secondary: '#0f172a',
            },
          },
          error: {
            iconTheme: {
              primary: '#f87171',
              secondary: '#0f172a',
            },
          },
        }}
      />
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <AppContent />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

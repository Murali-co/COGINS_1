import React, { useState } from 'react';
import { useProfile } from '../hooks/useProfile';
import { useJobs } from '../hooks/useJobs';
import { LoadingSpinner } from '../components/LoadingSpinner';
import apiClient from '../api/client';
import toast from 'react-hot-toast';

export const InterviewCoach = () => {
  const { profile, hasProfile, isLoading: isLoadingProfile } = useProfile();
  const { matchedJobs } = useJobs();

  // Interview States
  const [isStaging, setIsStaging] = useState(true);
  const [focusType, setFocusType] = useState('general'); // general | role | job
  const [targetRole, setTargetRole] = useState('');
  const [selectedJobId, setSelectedJobId] = useState('');

  // Active Session
  const [session, setSession] = useState(null); // { session_id, question, question_index }
  const [answer, setAnswer] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGeneratingStart, setIsGeneratingStart] = useState(false);

  // Report Card
  const [report, setReport] = useState(null);
  const [isLoadingReport, setIsLoadingReport] = useState(false);

  const handleStartInterview = async () => {
    setIsGeneratingStart(true);
    try {
      const payload = {};
      if (focusType === 'job' && selectedJobId) {
        payload.job_id = selectedJobId;
      } else if (focusType === 'role' && targetRole) {
        payload.target_role = targetRole;
      }

      const res = await apiClient.post('/interview/start', payload);
      setSession(res.data);
      setIsStaging(false);
      setReport(null);
      setAnswer('');
      toast.success('Interview session initiated!');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to start interview.');
    } finally {
      setIsGeneratingStart(false);
    }
  };

  const handleSubmitAnswer = async () => {
    if (!answer.trim()) {
      toast.error('Please write an answer first.');
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await apiClient.post('/interview/answer', {
        session_id: session.session_id,
        answer: answer
      });

      const data = res.data;
      if (data.is_finished) {
        toast.success('Interview complete! Generating your report...');
        const finishedSessionId = session.session_id; // capture BEFORE clearing state
        setSession(null);
        handleGetReport(finishedSessionId);           // use captured value
      } else {
        setSession({
          session_id: data.session_id,
          question: data.next_question,
          question_index: data.question_index
        });
        setAnswer('');
        toast.success('Answer submitted! Loaded next question.');
      }
    } catch (err) {
      toast.error('Failed to submit answer. Please try again.');
      console.error(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleGetReport = async (sessionId) => {
    setIsLoadingReport(true);
    try {
      const res = await apiClient.get(`/interview/report?session_id=${sessionId}`);
      setReport(res.data);
    } catch (err) {
      toast.error('Failed to compile report card.');
    } finally {
      setIsLoadingReport(false);
    }
  };

  const resetSession = () => {
    setIsStaging(true);
    setSession(null);
    setReport(null);
    setAnswer('');
  };

  if (isLoadingProfile) {
    return (
      <div className="max-w-4xl mx-auto py-20">
        <LoadingSpinner text="Retrieving candidate profile details..." />
      </div>
    );
  }

  if (!hasProfile || !profile?.resume_text) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-20 text-center">
        <div className="glass-panel border rounded-2xl p-12 space-y-4">
          <span className="text-5xl block">📝</span>
          <h2 className="text-xl font-bold text-dark-100">Resume Needed</h2>
          <p className="text-xs text-dark-400 max-w-md mx-auto leading-relaxed">
            Interview Coach requires an uploaded resume to generate custom, context-aware questions mapping to your background. Please upload a resume on the Dashboard first.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Title */}
      <div className="pb-4 border-b border-dark-800">
        <h1 className="text-2xl md:text-3xl font-extrabold text-dark-50">🗣️ AI Interview Coach</h1>
        <p className="text-xs text-dark-400 mt-1">
          Interactive multi-turn technical & behavioral mock interviews with detailed report cards and grading.
        </p>
      </div>

      {/* 1. Staging / Setup Selection */}
      {isStaging && !isLoadingReport && !report && (
        <div className="glass-panel border rounded-2xl p-6 space-y-6">
          <h3 className="text-sm font-bold text-dark-200">Set Up Mock Interview Focus</h3>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* General Resume Focus */}
            <div 
              onClick={() => setFocusType('general')}
              className={`p-4 border rounded-xl cursor-pointer transition-all space-y-1.5 ${
                focusType === 'general' 
                  ? 'bg-indigo-600/10 border-indigo-500/30 text-indigo-400' 
                  : 'bg-dark-900/40 border-dark-800 text-dark-300 hover:bg-dark-900/60'
              }`}
            >
              <span className="text-xl block">📄</span>
              <h4 className="font-bold text-xs text-dark-100">General Review</h4>
              <p className="text-[10px] text-dark-400 leading-relaxed font-medium">
                Standard technical & soft skills interview based strictly on your uploaded resume.
              </p>
            </div>

            {/* Custom Target Role */}
            <div 
              onClick={() => setFocusType('role')}
              className={`p-4 border rounded-xl cursor-pointer transition-all space-y-1.5 ${
                focusType === 'role' 
                  ? 'bg-indigo-600/10 border-indigo-500/30 text-indigo-400' 
                  : 'bg-dark-900/40 border-dark-800 text-dark-300 hover:bg-dark-900/60'
              }`}
            >
              <span className="text-xl block">🎯</span>
              <h4 className="font-bold text-xs text-dark-100">Target Role</h4>
              <p className="text-[10px] text-dark-400 leading-relaxed font-medium">
                Tailored interview focusing on matching your background with a specific title.
              </p>
            </div>

            {/* ChromaDB Matched Jobs */}
            <div 
              onClick={() => setFocusType('job')}
              className={`p-4 border rounded-xl cursor-pointer transition-all space-y-1.5 ${
                focusType === 'job' 
                  ? 'bg-indigo-600/10 border-indigo-500/30 text-indigo-400' 
                  : 'bg-dark-900/40 border-dark-800 text-dark-300 hover:bg-dark-900/60'
              }`}
            >
              <span className="text-xl block">💼</span>
              <h4 className="font-bold text-xs text-dark-100">Matched Job Listing</h4>
              <p className="text-[10px] text-dark-400 leading-relaxed font-medium">
                Simulated role interview for an active indexed job description from your board.
              </p>
            </div>
          </div>

          {/* Conditional Input Fields */}
          {focusType === 'role' && (
            <div className="space-y-2 text-xs">
              <label className="font-bold text-dark-300">Target Job Title</label>
              <input
                type="text"
                placeholder="e.g. Lead React Engineer, AI Platform Developer"
                value={targetRole}
                onChange={(e) => setTargetRole(e.target.value)}
                className="w-full px-3 py-2 bg-dark-900 border border-dark-800 focus:border-indigo-500/40 rounded-xl outline-none text-dark-200"
              />
            </div>
          )}

          {focusType === 'job' && (
            <div className="space-y-2 text-xs">
              <label className="font-bold text-dark-300">Choose Scraped Position</label>
              {matchedJobs.length > 0 ? (
                <select
                  value={selectedJobId}
                  onChange={(e) => setSelectedJobId(e.target.value)}
                  className="w-full px-3 py-2 bg-dark-900 border border-dark-800 focus:border-indigo-500/40 rounded-xl outline-none text-dark-200"
                >
                  <option value="">Select a listing...</option>
                  {matchedJobs.map(job => (
                    <option key={job.id} value={job.id}>
                      {job.title} at {job.company} ({job.match_score}%)
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-[10px] text-red-400 font-semibold">
                  No jobs found in matches. Run a Job Scraping task on the board first.
                </p>
              )}
            </div>
          )}

          <div className="pt-2 border-t border-dark-800 flex justify-end">
            <button
              onClick={handleStartInterview}
              disabled={isGeneratingStart || (focusType === 'role' && !targetRole) || (focusType === 'job' && !selectedJobId)}
              className="px-6 py-2.5 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 disabled:from-dark-900 disabled:to-dark-900 text-white rounded-xl text-xs font-bold transition-all flex items-center space-x-2"
            >
              {isGeneratingStart ? (
                <>
                  <LoadingSpinner size="sm" text="" />
                  <span>Prompting Coach...</span>
                </>
              ) : (
                <>
                  <span>🚀</span>
                  <span>Start Mock Interview</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* 2. Active Interview Chat Console */}
      {session && !isStaging && (
        <div className="space-y-6">
          <div className="glass-panel border rounded-2xl flex flex-col min-h-[400px] text-xs">
            {/* Header */}
            <div className="px-5 py-4 border-b border-dark-800 flex justify-between items-center bg-dark-900/20">
              <span className="font-extrabold text-indigo-400 uppercase tracking-wider text-[10px]">Active Mock Interview</span>
              <span className="font-bold text-dark-400 bg-dark-900 px-2 py-0.5 rounded border border-dark-800">
                Question {session.question_index} of 3
              </span>
            </div>

            {/* Content area */}
            <div className="flex-grow p-6 space-y-6">
              <div className="p-4 bg-dark-900 border border-dark-800 rounded-xl space-y-2">
                <span className="text-[10px] font-extrabold text-indigo-400 uppercase tracking-wider block">Interviewer Question</span>
                <p className="text-dark-100 font-bold leading-relaxed whitespace-pre-line text-sm">
                  {session.question}
                </p>
              </div>

              <div className="space-y-2">
                <span className="text-[10px] font-extrabold text-dark-400 uppercase tracking-wider block">Your Response</span>
                <textarea
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  disabled={isSubmitting}
                  placeholder="Type your structured answer here. (Tip: Try using the STAR method: Situation, Task, Action, Result)"
                  rows={6}
                  className="w-full p-4 bg-dark-900 border border-dark-800 focus:border-indigo-500/40 rounded-xl outline-none text-dark-100 leading-relaxed font-semibold focus:ring-1 focus:ring-indigo-500/20 transition-all resize-none"
                />
              </div>
            </div>

            {/* Footer Buttons */}
            <div className="p-4 border-t border-dark-800 bg-dark-950/40 flex justify-between items-center">
              <button
                onClick={resetSession}
                className="px-4 py-2 border border-dark-800 hover:bg-dark-800 text-dark-400 hover:text-dark-200 font-bold rounded-xl"
              >
                Quit Interview
              </button>
              
              <button
                onClick={handleSubmitAnswer}
                disabled={isSubmitting || !answer.trim()}
                className="px-6 py-2 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 disabled:from-dark-900 disabled:to-dark-900 text-white font-bold rounded-xl flex items-center space-x-2"
              >
                {isSubmitting ? (
                  <>
                    <LoadingSpinner size="sm" text="" />
                    <span>Analyzing Answer...</span>
                  </>
                ) : (
                  <>
                    <span>Submit Answer</span>
                    <span>→</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* STAR Method Helper Panel */}
          <div className="p-4 bg-indigo-950/10 border border-indigo-500/10 rounded-xl text-[11px] text-dark-300 leading-relaxed space-y-1.5">
            <span className="font-bold text-indigo-400 block">💡 Pro-Tip: The STAR Method</span>
            <p className="font-semibold">
              Structure behavioral answers cleanly:
            </p>
            <ul className="list-disc pl-4 space-y-0.5 font-medium">
              <li><strong>Situation:</strong> Set the context for the project or task.</li>
              <li><strong>Task:</strong> Describe your specific responsibility or problem.</li>
              <li><strong>Action:</strong> Explain the exact steps and technology stacks you used to resolve it.</li>
              <li><strong>Result:</strong> State the outcomes, efficiency boosts, or latency reductions (ideally quantified!).</li>
            </ul>
          </div>
        </div>
      )}

      {/* 3. Generating Report Loader */}
      {isLoadingReport && (
        <div className="glass-panel border rounded-2xl p-12 text-center space-y-4">
          <LoadingSpinner text="" />
          <h3 className="text-lg font-bold text-dark-100 animate-pulse">Compiling Report Card</h3>
          <p className="text-xs text-dark-400 max-w-sm mx-auto leading-relaxed">
            The coach is grading your interview transcript. We are calculating performance scores, isolating strengths, and generating actionable improvement recommendations...
          </p>
        </div>
      )}

      {/* 4. Complete Report Card View */}
      {report && !isLoadingReport && (
        <div className="space-y-6 text-xs">
          
          {/* Header & Overall Score Block */}
          <div className="glass-panel border rounded-2xl p-6 grid grid-cols-1 md:grid-cols-4 gap-6 items-center">
            <div className="md:col-span-1 flex flex-col items-center justify-center p-6 bg-dark-900 border border-dark-800 rounded-2xl text-center">
              <span className="text-[10px] font-bold text-dark-400 uppercase tracking-wider pb-3">Evaluation Score</span>
              
              {/* Score circle */}
              <div className="relative w-24 h-24 flex items-center justify-center">
                <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                  <path
                    className="text-dark-800"
                    strokeWidth="3.5"
                    stroke="currentColor"
                    fill="none"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                  <path
                    className="text-indigo-500"
                    strokeDasharray={`${report.score}, 100`}
                    strokeWidth="3.5"
                    strokeLinecap="round"
                    stroke="currentColor"
                    fill="none"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                </svg>
                <div className="absolute text-2xl font-extrabold text-dark-50">
                  {report.score}
                </div>
              </div>
            </div>

            <div className="md:col-span-3 space-y-3">
              <span className="px-2 py-0.5 bg-indigo-950/55 border border-indigo-500/20 text-indigo-400 rounded-full font-extrabold text-[9px] uppercase tracking-wider">
                Mock Interview Concluded
              </span>
              <h3 className="text-lg font-bold text-dark-50">Performance Overview</h3>
              <p className="text-dark-300 leading-relaxed font-semibold text-xs">
                {report.feedback}
              </p>
            </div>
          </div>

          {/* Strengths & Weaknesses Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            
            {/* Strengths Panel */}
            <div className="glass-panel border border-emerald-500/10 bg-emerald-950/5 rounded-2xl p-5 space-y-4">
              <h4 className="font-extrabold text-emerald-400 flex items-center space-x-1.5 text-xs">
                <span>✓</span>
                <span>Core Strengths</span>
              </h4>
              <ul className="space-y-2.5 font-medium text-dark-300">
                {report.strengths.map((str, i) => (
                  <li key={i} className="flex items-start space-x-2">
                    <span className="text-emerald-500 shrink-0">•</span>
                    <span>{str}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Weaknesses Panel */}
            <div className="glass-panel border border-red-500/10 bg-red-950/5 rounded-2xl p-5 space-y-4">
              <h4 className="font-extrabold text-red-400 flex items-center space-x-1.5 text-xs">
                <span>⚠</span>
                <span>Areas for Improvement</span>
              </h4>
              <ul className="space-y-2.5 font-medium text-dark-300">
                {report.weaknesses.map((weak, i) => (
                  <li key={i} className="flex items-start space-x-2">
                    <span className="text-red-500 shrink-0">•</span>
                    <span>{weak}</span>
                  </li>
                ))}
              </ul>
            </div>

          </div>

          {/* Actionable Suggestions Panel */}
          <div className="glass-panel border border-indigo-500/10 bg-indigo-950/5 rounded-2xl p-5 space-y-4">
            <h4 className="font-extrabold text-indigo-400 flex items-center space-x-1.5 text-xs">
              <span>🚀</span>
              <span>Improvement Recommendations</span>
            </h4>
            <ul className="space-y-2.5 font-medium text-dark-300 pl-2">
              {report.suggestions.map((sug, i) => (
                <li key={i} className="flex items-start space-x-3">
                  <span className="w-5 h-5 flex items-center justify-center bg-indigo-600/20 text-indigo-400 font-extrabold rounded-full text-[10px] shrink-0">
                    {i + 1}
                  </span>
                  <span className="pt-0.5">{sug}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Action controls */}
          <div className="flex justify-end pt-2">
            <button
              onClick={resetSession}
              className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl shadow-md transition-all text-xs"
            >
              Start New Mock Session
            </button>
          </div>

        </div>
      )}

    </div>
  );
};

export default InterviewCoach;

import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useProfile } from '../hooks/useProfile';
import { useJobs } from '../hooks/useJobs';
import { LoadingSpinner } from '../components/LoadingSpinner';
import MarketInsights from '../components/MarketInsights';
import SavedJobsPipeline from '../components/SavedJobsPipeline';
import apiClient from '../api/client';
import toast from 'react-hot-toast';

export const Dashboard = () => {
  const navigate = useNavigate();
  const { profile, isLoading: isLoadingProfile, refetch: refetchProfile } = useProfile();
  const { jobs, appHistory, isLoadingJobs, isLoadingHistory } = useJobs();

  // Tab State: 'overview', 'customize', 'versions', 'admin'
  const [activeTab, setActiveTab] = useState('overview');
  
  // Customization Form State
  const [editSkills, setEditSkills] = useState('');
  const [editText, setEditText] = useState('');
  const [savingProfile, setSavingProfile] = useState(false);

  // Versions State
  const [versions, setVersions] = useState([]);
  const [loadingVersions, setLoadingVersions] = useState(false);

  // Admin Stats State
  const [adminStats, setAdminStats] = useState(null);
  const [loadingAdmin, setLoadingAdmin] = useState(false);

  // Initialize edit form when profile changes
  useEffect(() => {
    if (profile) {
      setEditSkills(profile.skills ? profile.skills.join(', ') : '');
      setEditText(profile.resume_text || '');
    }
  }, [profile]);

  // Load versions
  const fetchVersions = async () => {
    setLoadingVersions(true);
    try {
      const res = await apiClient.get('/resume/versions');
      setVersions(res.data || []);
    } catch (err) {
      toast.error('Failed to load resume versions.');
    } finally {
      setLoadingVersions(false);
    }
  };

  // Load admin stats
  const fetchAdminStats = async () => {
    setLoadingAdmin(true);
    try {
      const res = await apiClient.get('/auth/admin/stats');
      setAdminStats(res.data);
    } catch (err) {
      toast.error('Failed to load system diagnostics.');
    } finally {
      setLoadingAdmin(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'versions') {
      fetchVersions();
    } else if (activeTab === 'admin') {
      fetchAdminStats();
    }
  }, [activeTab]);

  const handleSaveProfile = async (e) => {
    e.preventDefault();
    setSavingProfile(true);
    try {
      const skillsArray = editSkills
        .split(',')
        .map(s => s.trim())
        .filter(s => s.length > 0);
      
      await apiClient.post('/resume/profile/edit', {
        skills: skillsArray,
        resume_text: editText
      });
      
      toast.success('Profile vectors updated successfully!');
      refetchProfile();
    } catch (err) {
      toast.error('Failed to save profile updates.');
    } finally {
      setSavingProfile(false);
    }
  };

  const handleRestoreVersion = async (versionId) => {
    try {
      const load = toast.loading('Restoring chosen version...');
      await apiClient.post(`/resume/versions/restore/${versionId}`);
      toast.dismiss(load);
      toast.success('Historical version restored successfully!');
      refetchProfile();
      fetchVersions();
    } catch (err) {
      toast.error('Failed to restore selected version.');
    }
  };

  if (isLoadingProfile || isLoadingJobs || isLoadingHistory) {
    return <LoadingSpinner text="Retrieving dashboard metrics..." />;
  }

  const hasResume = !!profile;
  const skillsCount = profile?.skills?.length || 0;
  const jobsCount = jobs?.length || 0;
  const appliedCount = appHistory?.length || 0;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Welcome Banner */}
      <div className="glass-panel border rounded-3xl p-6 md:p-8 flex flex-col md:flex-row justify-between items-start md:items-center gap-6 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-80 h-80 rounded-full bg-indigo-500/5 blur-[80px] pointer-events-none"></div>
        
        <div className="space-y-2 relative z-10">
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-dark-50">
            Welcome to COGNIS, Jobseeker
          </h1>
          <p className="text-sm text-dark-400 max-w-lg">
            Manage your personal profile vectors, set local scraping pipelines, and analyze matches privately.
          </p>
        </div>

        {!hasResume && (
          <button
            onClick={() => navigate('/upload')}
            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-sm transition-all shadow-lg relative z-10"
          >
            Upload Your Resume
          </button>
        )}
      </div>

      {/* Tabs Selector */}
      <div className="flex border-b border-dark-800 space-x-6">
        {[
          { id: 'overview', name: 'Dashboard Overview', icon: '🧭' },
          { id: 'customize', name: 'Customize Profile', icon: '⚙️' },
          { id: 'versions', name: 'Version Control', icon: '📜' },
          { id: 'admin', name: 'System Diagnostics', icon: '📊' }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`pb-4 text-sm font-semibold flex items-center space-x-2 border-b-2 transition-all duration-200 ${
              activeTab === tab.id
                ? 'border-indigo-500 text-indigo-400 font-bold'
                : 'border-transparent text-dark-400 hover:text-dark-200'
            }`}
          >
            <span>{tab.icon}</span>
            <span>{tab.name}</span>
          </button>
        ))}
      </div>

      {/* TAB CONTENTS: Overview */}
      {activeTab === 'overview' && (
        <div className="space-y-8">
          {/* Metrics Row */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            <div className="glass-panel border rounded-2xl p-5 flex items-center space-x-4">
              <span className="text-3xl p-3 bg-dark-900 rounded-xl">📄</span>
              <div>
                <p className="text-xs text-dark-400 font-semibold uppercase tracking-wider">Profile Vector Status</p>
                <p className="text-lg font-bold text-dark-100 mt-0.5">
                  {hasResume ? `${skillsCount} Skills Indexed` : 'Not Created'}
                </p>
              </div>
            </div>

            <div className="glass-panel border rounded-2xl p-5 flex items-center space-x-4">
              <span className="text-3xl p-3 bg-dark-900 rounded-xl">💼</span>
              <div>
                <p className="text-xs text-dark-400 font-semibold uppercase tracking-wider">Local Jobs Logged</p>
                <p className="text-lg font-bold text-dark-100 mt-0.5">{jobsCount} Listings</p>
              </div>
            </div>

            <div className="glass-panel border rounded-2xl p-5 flex items-center space-x-4">
              <span className="text-3xl p-3 bg-dark-900 rounded-xl">🚀</span>
              <div>
                <p className="text-xs text-dark-400 font-semibold uppercase tracking-wider">Active Applications</p>
                <p className="text-lg font-bold text-dark-100 mt-0.5">{appliedCount} Submitted</p>
              </div>
            </div>
          </div>

          {/* Two-Column Phase Details */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Phase 1 Panel */}
            <div className="glass-panel border rounded-2xl p-6 flex flex-col justify-between space-y-6">
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-bold text-dark-100">Phase 1: Resume Profile Intelligence</h3>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${hasResume ? 'bg-emerald-950/20 text-emerald-400 border-emerald-500/20' : 'bg-red-950/20 text-red-400 border-red-500/20'}`}>
                    {hasResume ? 'Completed' : 'Pending'}
                  </span>
                </div>
                
                <p className="text-xs text-dark-400 leading-relaxed">
                  Processes raw doc text, formats sections, indexes tags, and runs LLM intelligence diagnostics on target positions.
                </p>
                
                {hasResume ? (
                  <div className="bg-dark-950/40 p-4 rounded-xl border border-dark-900/60 max-h-32 overflow-y-auto">
                    <p className="text-xs font-semibold text-dark-300 mb-2">Parsed Competencies:</p>
                    <div className="flex flex-wrap gap-1.5">
                      {profile.skills.slice(0, 8).map((skill) => (
                        <span key={skill} className="text-[10px] font-medium px-2 py-0.5 bg-indigo-950/30 text-indigo-400 border border-indigo-500/10 rounded-md">
                          {skill}
                        </span>
                      ))}
                      {skillsCount > 8 && (
                        <span className="text-[10px] font-medium px-2 py-0.5 bg-dark-900 text-dark-400 border border-dark-800 rounded-md">
                          +{skillsCount - 8} more
                        </span>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center justify-center p-8 bg-dark-950/20 border border-dashed border-dark-800 rounded-xl text-center text-xs text-dark-400">
                    Please upload a resume first to extract skills.
                  </div>
                )}
              </div>

              <div className="flex items-center space-x-3 pt-2">
                <button
                  onClick={() => navigate('/upload')}
                  className="px-4 py-2 bg-dark-900 border border-dark-800 hover:bg-dark-800 text-dark-100 text-xs font-bold rounded-xl transition-all"
                >
                  Manage Document
                </button>
                {hasResume && (
                  <button
                    onClick={() => navigate('/upload?analyze=true')}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded-xl transition-all"
                  >
                    Analyze Gaps
                  </button>
                )}
              </div>
            </div>

            {/* Phase 2 Panel */}
            <div className="glass-panel border rounded-2xl p-6 flex flex-col justify-between space-y-6">
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-bold text-dark-100">Phase 2: Autonomous Market Sourcing</h3>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${jobsCount > 0 ? 'bg-emerald-950/20 text-emerald-400 border-emerald-500/20' : 'bg-amber-950/20 text-amber-400 border-amber-500/20'}`}>
                    {jobsCount > 0 ? 'Active' : 'Setup Required'}
                  </span>
                </div>
                
                <p className="text-xs text-dark-400 leading-relaxed">
                  Scrapes web postings under 48 hours old, matches profiles, drafts tailored letters, and compiles application files.
                </p>

                <div className="bg-dark-950/40 p-4 rounded-xl border border-dark-900/60 text-xs text-dark-300 space-y-1.5">
                  <div className="flex justify-between">
                    <span>Total Matched Positions:</span>
                    <span className="font-bold text-indigo-400">{jobsCount}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Scraping Sources:</span>
                    <span className="text-[10px] font-bold text-dark-400">LinkedIn, Indeed</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center space-x-3 pt-2">
                <button
                  onClick={() => navigate('/jobs')}
                  className="px-4 py-2 bg-dark-900 border border-dark-800 hover:bg-dark-800 text-dark-100 text-xs font-bold rounded-xl transition-all"
                >
                  Scraper Pipeline
                </button>
                {hasResume && (
                  <button
                    onClick={() => navigate('/match')}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded-xl transition-all"
                  >
                    Calculate Matches
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Market Intelligence Charts */}
          <div className="space-y-4">
            <div className="flex items-center space-x-2">
              <span className="text-xl">📊</span>
              <h2 className="text-lg font-bold text-dark-100">Market Intelligence</h2>
            </div>
            <MarketInsights />
          </div>

          {/* Recent Applications Log */}
          <div className="glass-panel border rounded-2xl p-6 space-y-4">
            <h3 className="text-lg font-bold text-dark-100">Application Log History</h3>
            
            {appliedCount > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-dark-800 text-dark-400 font-semibold">
                      <th className="pb-3">Job Title</th>
                      <th className="pb-3">Company</th>
                      <th className="pb-3">Date Logged</th>
                      <th className="pb-3 text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {appHistory.slice(0, 5).map((app) => (
                      <tr key={app.id} className="border-b border-dark-900/60 hover:bg-dark-900/10 transition-all">
                        <td className="py-3 font-semibold text-dark-100">{app.job_title}</td>
                        <td className="py-3 text-dark-300">{app.company}</td>
                        <td className="py-3 text-dark-400">{app.applied_at.split(' ')[0]}</td>
                        <td className="py-3 text-right">
                          <span className="px-2 py-0.5 bg-emerald-950/20 text-emerald-400 border border-emerald-500/20 rounded-md font-bold uppercase tracking-wider text-[9px]">
                            {app.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="flex flex-col items-center justify-center p-8 bg-dark-950/20 border border-dashed border-dark-800 rounded-xl text-center text-xs text-dark-400 space-y-2">
                  <span>No applications logged in history yet.</span>
                  <Link to="/match" className="text-indigo-400 hover:underline font-bold">Find jobs to match and apply</Link>
                </div>

                <SavedJobsPipeline />
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB CONTENTS: Customize Profile */}
      {activeTab === 'customize' && (
        <div className="glass-panel border rounded-2xl p-6 space-y-6">
          <div className="space-y-1">
            <h3 className="text-lg font-bold text-dark-50">Profile Customizer</h3>
            <p className="text-xs text-dark-400">
              Directly edit your vector database profile. This regenerates matches immediately without full resume parses.
            </p>
          </div>

          {!hasResume ? (
            <div className="text-center p-8 text-xs text-dark-400">
              Please upload a resume first to populate your profile.
            </div>
          ) : (
            <form onSubmit={handleSaveProfile} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-dark-300 mb-1.5">Parsed Skills (Comma Separated)</label>
                <input
                  type="text"
                  required
                  value={editSkills}
                  onChange={(e) => setEditSkills(e.target.value)}
                  className="w-full px-4 py-2.5 bg-dark-950 border border-dark-800 focus:border-indigo-500/40 rounded-xl text-sm text-dark-100 focus:outline-none transition-all"
                  placeholder="Python, React, FastAPI, Machine Learning..."
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-dark-300 mb-1.5">Active Resume Plain Text</label>
                <textarea
                  rows={10}
                  required
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  className="w-full px-4 py-2.5 bg-dark-950 border border-dark-800 focus:border-indigo-500/40 rounded-xl text-xs text-dark-100 focus:outline-none transition-all font-mono leading-relaxed"
                  placeholder="Paste resume content here..."
                />
              </div>

              <button
                type="submit"
                disabled={savingProfile}
                className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-sm transition-all disabled:opacity-50"
              >
                {savingProfile ? 'Updating Vectors...' : 'Save Vector Updates'}
              </button>
            </form>
          )}
        </div>
      )}

      {/* TAB CONTENTS: Versions */}
      {activeTab === 'versions' && (
        <div className="glass-panel border rounded-2xl p-6 space-y-6">
          <div className="space-y-1">
            <h3 className="text-lg font-bold text-dark-50">Resume Version Control</h3>
            <p className="text-xs text-dark-400">
              Select and restore older versions of your parsed resume from the local history log.
            </p>
          </div>

          {loadingVersions ? (
            <LoadingSpinner text="Retrieving versions history..." />
          ) : versions.length === 0 ? (
            <div className="text-center p-8 text-xs text-dark-400">
              No historic resume versions found. Upload a resume or save custom edits to begin.
            </div>
          ) : (
            <div className="space-y-4">
              {versions.map((ver) => (
                <div key={ver.id} className="p-4 bg-dark-950/40 border border-dark-800 rounded-xl flex justify-between items-center hover:border-dark-700/60 transition-all">
                  <div className="space-y-1">
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-dark-950 text-indigo-400 border border-indigo-500/10">
                      Version #{ver.id}
                    </span>
                    <h4 className="text-xs font-semibold text-dark-100">{ver.label}</h4>
                    <p className="text-[10px] text-dark-400">
                      Captured: {new Date(ver.created_at + 'Z').toLocaleString()}
                    </p>
                  </div>
                  <button
                    onClick={() => handleRestoreVersion(ver.id)}
                    className="px-3.5 py-1.5 bg-indigo-600/10 hover:bg-indigo-600 hover:text-white border border-indigo-500/20 text-indigo-400 text-xs font-bold rounded-lg transition-all"
                  >
                    Restore Version
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB CONTENTS: Admin Diagnostics */}
      {activeTab === 'admin' && (
        <div className="glass-panel border rounded-2xl p-6 space-y-6">
          <div className="space-y-1">
            <h3 className="text-lg font-bold text-dark-50">System Analytics Diagnostics</h3>
            <p className="text-xs text-dark-400">
              Live PostgreSQL database stats and indexing diagnostics.
            </p>
          </div>

          {loadingAdmin ? (
            <LoadingSpinner text="Loading system metrics..." />
          ) : !adminStats ? (
            <div className="text-center p-8 text-xs text-dark-400">
              Failed to query telemetry database.
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              {[
                { name: 'Total Users', value: adminStats.total_users, icon: '👥' },
                { name: 'Total Applications', value: adminStats.total_applications, icon: '📤' },
                { name: 'System Chat Messages', value: adminStats.total_chats, icon: '💬' },
                { name: 'Simulated Interviews', value: adminStats.total_interviews, icon: '🎙️' }
              ].map(stat => (
                <div key={stat.name} className="p-4 bg-dark-950/40 border border-dark-800 rounded-xl text-center space-y-2">
                  <span className="text-3xl">{stat.icon}</span>
                  <div>
                    <h4 className="text-[10px] uppercase font-bold text-dark-400 tracking-wide">{stat.name}</h4>
                    <p className="text-xl font-extrabold text-indigo-400 mt-1">{stat.value}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
export default Dashboard;

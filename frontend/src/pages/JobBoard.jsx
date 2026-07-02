import React, { useState, useEffect } from 'react';
import { useJobs } from '../hooks/useJobs';
import JobCard from '../components/JobCard';
import { LoadingSpinner } from '../components/LoadingSpinner';
import toast from 'react-hot-toast';

const LOCATION_OPTIONS = [
  { value: 'Any', label: '🌍 Any Location' },
  { value: 'Remote', label: '🏠 Remote' },
  { value: 'Bangalore', label: '🇮🇳 Bangalore' },
  { value: 'Hyderabad', label: '🇮🇳 Hyderabad' },
  { value: 'Chennai', label: '🇮🇳 Chennai' },
  { value: 'Pune', label: '🇮🇳 Pune' },
  { value: 'Mumbai', label: '🇮🇳 Mumbai' },
  { value: 'Delhi', label: '🇮🇳 Delhi' },
  { value: 'San Francisco', label: '🇺🇸 San Francisco' },
  { value: 'New York', label: '🇺🇸 New York' },
  { value: 'London', label: '🇬🇧 London' },
  { value: 'Toronto', label: '🇨🇦 Toronto' },
  { value: 'Singapore', label: '🇸🇬 Singapore' },
  { value: 'Dubai', label: '🇦🇪 Dubai' },
];

const AGE_OPTIONS = [
  { value: 24, label: 'Last 24 Hours' },
  { value: 48, label: 'Last 48 Hours' },
  { value: 168, label: 'Last 7 Days' },
  { value: 720, label: 'Last 30 Days' },
];

const JOB_TYPE_OPTIONS = [
  { value: 'remote', label: 'Remote' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'onsite', label: 'On-site' },
];

export const JobBoard = () => {
  const {
    jobs,
    isLoadingJobs,
    refetchJobs,
    criteria,
    saveCriteria,
    fetchJobs,
    isFetchingJobs,
    pollJobStatus,
    saveJob,
  } = useJobs();

  const [title, setTitle] = useState('');
  const [location, setLocation] = useState('Any');
  const [hoursOld, setHoursOld] = useState(48);
  const [jobTypeFilters, setJobTypeFilters] = useState({
    remote: true,
    hybrid: true,
    onsite: true,
  });
  const [pollingJobId, setPollingJobId] = useState(null);
  const [lastScrapeTime, setLastScrapeTime] = useState(null);
  const [lastScrapeResult, setLastScrapeResult] = useState(null);

  // Sync criteria on load
  useEffect(() => {
    if (criteria) {
      setTitle(criteria.title || '');
      setLocation(criteria.location || 'Any');
      setHoursOld(criteria.hours_old || 48);
      if (criteria.job_type) {
        setJobTypeFilters({
          remote: criteria.job_type === 'remote',
          hybrid: criteria.job_type === 'hybrid',
          onsite: criteria.job_type === 'onsite',
        });
      } else {
        setJobTypeFilters({ remote: true, hybrid: true, onsite: true });
      }
    }
  }, [criteria]);

  const getSelectedJobType = () => {
    const selected = Object.keys(jobTypeFilters).filter((key) => jobTypeFilters[key]);
    return selected.length === 1 ? selected[0] : undefined;
  };

  const handleSaveCriteria = async (e) => {
    e.preventDefault();
    const loadingToast = toast.loading('Saving search parameters...');
    try {
      await saveCriteria({
        title,
        location,
        is_remote: location === 'Remote',
        job_type: getSelectedJobType(),
        hours_old: hoursOld,
      });
      toast.success('Search filters updated!', { id: loadingToast });
    } catch (err) {
      toast.error('Failed to save search parameters.', { id: loadingToast });
    }
  };

  const handleToggleJobType = (type) => {
    setJobTypeFilters(prev => ({ ...prev, [type]: !prev[type] }));
  };

  const handleTriggerScrape = async () => {
    try {
      const response = await fetchJobs({
      title,
      location,
      hours_old: hoursOld,
      job_type: getSelectedJobType(),
    });
      const { job_id } = response;
      setPollingJobId(job_id);

      pollJobStatus(
        job_id,
        (result) => {
          const msg = result.matched_count
            ? `Fetched ${result.count} jobs, ${result.matched_count} matched to your profile!`
            : `Successfully fetched ${result.count} new job listings!`;
          toast.success(msg);
          setPollingJobId(null);
          setLastScrapeTime(new Date().toLocaleString());
          setLastScrapeResult(result);
          refetchJobs();
        },
        (errorMsg) => {
          toast.error(errorMsg || 'Scraping failed.');
          setPollingJobId(null);
        }
      );
    } catch (err) {
      toast.error('Failed to trigger job scraper.');
    }
  };

  const handleSaveJob = async (job) => {
    try {
      await saveJob({
        job_id: job.id,
        title: job.title,
        company: job.company,
        location: job.location,
        job_url: job.url,
        notes: '',
      });
      toast.success(`"${job.title}" saved!`);
    } catch (err) {
      toast.error('Failed to save job.');
    }
  };

  // Client-side job type filter
  const filteredJobs = jobs.filter(job => {
    const jt = (job.job_type || 'onsite').toLowerCase().replace('-', '').replace('_', '');
    if (jt === 'remote' && !jobTypeFilters.remote) return false;
    if (jt === 'hybrid' && !jobTypeFilters.hybrid) return false;
    if (jt === 'onsite' && !jobTypeFilters.onsite) return false;
    return true;
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8 relative">
      {/* Scraping Progress overlay */}
      {pollingJobId && (
        <div className="absolute inset-0 bg-dark-950/80 backdrop-blur-md z-50 flex items-center justify-center rounded-3xl">
          <div className="text-center space-y-4 max-w-sm p-6 bg-dark-900 border border-dark-800 rounded-2xl shadow-2xl">
            <LoadingSpinner size="lg" text="" />
            <h3 className="text-lg font-bold text-dark-100 animate-pulse">Running Phase-2 Pipeline</h3>
            <p className="text-xs text-dark-400 leading-relaxed">
              Scraping LinkedIn & Indeed → Deduplicating → Storing → Semantic Matching → Ranking. This can take 15-40 seconds...
            </p>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 pb-4 border-b border-dark-800">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-dark-50">Market Sourcing Pipeline</h1>
          <p className="text-xs text-dark-400 mt-1">Configure filters, scrape live job boards, and view match-ranked results.</p>
        </div>

        <button
          onClick={handleTriggerScrape}
          disabled={isFetchingJobs || pollingJobId}
          className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-bold rounded-xl transition-all shadow-md flex items-center space-x-2"
        >
          <span>🔍</span>
          <span>Scrape New Listings</span>
        </button>
      </div>

      {/* Pipeline Stats Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="glass-panel border rounded-xl p-3 text-center">
          <p className="text-[10px] text-dark-400 font-semibold uppercase tracking-wider">Total Jobs</p>
          <p className="text-xl font-extrabold text-indigo-400 mt-1">{jobs.length}</p>
        </div>
        <div className="glass-panel border rounded-xl p-3 text-center">
          <p className="text-[10px] text-dark-400 font-semibold uppercase tracking-wider">Showing</p>
          <p className="text-xl font-extrabold text-emerald-400 mt-1">{filteredJobs.length}</p>
        </div>
        <div className="glass-panel border rounded-xl p-3 text-center">
          <p className="text-[10px] text-dark-400 font-semibold uppercase tracking-wider">Last Scrape</p>
          <p className="text-xs font-bold text-dark-200 mt-1">{lastScrapeTime || 'Not run yet'}</p>
        </div>
        <div className="glass-panel border rounded-xl p-3 text-center">
          <p className="text-[10px] text-dark-400 font-semibold uppercase tracking-wider">Active Filters</p>
          <p className="text-xs font-bold text-dark-200 mt-1">
            {[
              location !== 'Any' ? location : null,
              hoursOld !== 720 ? `<${hoursOld}h` : null,
              ...JOB_TYPE_OPTIONS.filter(o => !jobTypeFilters[o.value]).map(o => `No ${o.label}`),
            ].filter(Boolean).join(', ') || 'None'}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
        {/* Sidebar Filters */}
        <div className="lg:col-span-1 space-y-6">
          <div className="glass-panel border rounded-2xl p-5 space-y-5">
            <h3 className="text-sm font-bold text-dark-100 pb-3 border-b border-dark-800">Scraper Parameters</h3>

            <form onSubmit={handleSaveCriteria} className="space-y-4 text-xs">
              {/* Job Title */}
              <div>
                <label className="block text-xs font-semibold text-dark-300 mb-1.5">Job Title Keywords</label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full px-3 py-2 bg-dark-950 border border-dark-800 focus:border-indigo-500/40 rounded-xl text-dark-100 focus:outline-none transition-all"
                  placeholder="e.g. Software Engineer, React"
                />
              </div>

              {/* Preferred Location — Dropdown */}
              <div>
                <label className="block text-xs font-semibold text-dark-300 mb-1.5">Preferred Location</label>
                <select
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  className="w-full px-3 py-2 bg-dark-950 border border-dark-800 focus:border-indigo-500/40 rounded-xl text-dark-100 focus:outline-none transition-all appearance-none cursor-pointer"
                >
                  {LOCATION_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              {/* Job Age Filter */}
              <div>
                <label className="block text-xs font-semibold text-dark-300 mb-1.5">Job Posting Age</label>
                <select
                  value={hoursOld}
                  onChange={(e) => setHoursOld(Number(e.target.value))}
                  className="w-full px-3 py-2 bg-dark-950 border border-dark-800 focus:border-indigo-500/40 rounded-xl text-dark-100 focus:outline-none transition-all appearance-none cursor-pointer"
                >
                  {AGE_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              {/* Job Type Filters */}
              <div>
                <label className="block text-xs font-semibold text-dark-300 mb-2">Job Type Filters</label>
                <div className="space-y-2">
                  {JOB_TYPE_OPTIONS.map(opt => (
                    <div key={opt.value} className="flex items-center space-x-2.5">
                      <input
                        type="checkbox"
                        id={`type-${opt.value}`}
                        checked={jobTypeFilters[opt.value]}
                        onChange={() => handleToggleJobType(opt.value)}
                        className="w-4 h-4 rounded text-indigo-600 bg-dark-950 border-dark-800 focus:ring-indigo-500/40 focus:ring-2 focus:ring-offset-dark-950 cursor-pointer"
                      />
                      <label htmlFor={`type-${opt.value}`} className="font-semibold text-dark-300 cursor-pointer">
                        {opt.label}
                      </label>
                    </div>
                  ))}
                </div>
              </div>

              <button
                type="submit"
                className="w-full py-2 bg-dark-900 border border-dark-800 hover:bg-dark-800 text-dark-100 font-bold rounded-xl transition-all"
              >
                Save Parameters
              </button>
            </form>
          </div>
        </div>

        {/* Listings column */}
        <div className="lg:col-span-3 space-y-4">
          <div className="flex justify-between items-center text-xs">
            <span className="text-dark-400 font-semibold uppercase tracking-wider">
              Job Listings ({filteredJobs.length})
            </span>
            <button onClick={() => refetchJobs()} className="text-indigo-400 font-bold hover:underline">
              Refresh List
            </button>
          </div>

          {isLoadingJobs ? (
            <LoadingSpinner text="Retrieving job database..." />
          ) : filteredJobs.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {filteredJobs.map((job) => (
                <JobCard
                  key={job.id}
                  job={job}
                  onAction={null}
                  onSave={() => handleSaveJob(job)}
                  showApplyLink
                />
              ))}
            </div>
          ) : (
            <div className="glass-panel border rounded-2xl p-12 text-center text-xs text-dark-400 space-y-3">
              <span className="text-4xl block">🔍</span>
              <p className="font-bold text-dark-200">No Job Postings Found</p>
              <p className="max-w-xs mx-auto text-[11px]">
                Click "Scrape New Listings" at the top to start scraping job boards for matching positions.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
export default JobBoard;

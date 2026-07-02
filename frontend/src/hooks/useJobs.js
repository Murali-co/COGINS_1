import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../api/client';

export const useJobs = () => {
  const queryClient = useQueryClient();

  // 1. Get raw/filtered job list
  const jobsQuery = useQuery({
    queryKey: ['jobs'],
    queryFn: async () => {
      const response = await apiClient.get('/jobs/list');
      return response.data.jobs;
    },
  });

  // 2. Get matched jobs
  const matchedJobsQuery = useQuery({
    queryKey: ['matchedJobs'],
    queryFn: async () => {
      const response = await apiClient.post('/jobs/match');
      return response.data.jobs;
    },
  });

  // 3. Get filter criteria
  const criteriaQuery = useQuery({
    queryKey: ['criteria'],
    queryFn: async () => {
      const response = await apiClient.get('/jobs/criteria');
      return response.data;
    },
  });

  // 4. Save filter criteria mutation
  const saveCriteriaMutation = useMutation({
    mutationFn: async (criteriaData) => {
      const response = await apiClient.post('/jobs/criteria', criteriaData);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['criteria'] });
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      queryClient.invalidateQueries({ queryKey: ['matchedJobs'] });
    },
  });

  // 5. Fetch jobs manually mutation (returns background job_id)
  const fetchJobsMutation = useMutation({
    mutationFn: async ({ title, location, hours_old, job_type } = {}) => {
      const params = {};
      if (title) params.title = title;
      if (location) params.location = location;
      if (hours_old) params.hours_old = hours_old;
      if (job_type) params.job_type = job_type;
      const response = await apiClient.get('/jobs/fetch', { params });
      return response.data; // { job_id: ..., status: ... }
    },
  });

  // 6. Generate application package mutation (returns background job_id)
  const generateApplicationMutation = useMutation({
    mutationFn: async ({ jobId }) => {
      const response = await apiClient.post(`/apply/generate/${jobId}`);
      return response.data; // { job_id: ..., status: ... }
    },
  });

  // 7. Submit application record
  const submitApplicationMutation = useMutation({
    mutationFn: async (submitData) => {
      const response = await apiClient.post('/apply/submit', submitData);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['appHistory'] });
    },
  });

  // 8. Application history list
  const historyQuery = useQuery({
    queryKey: ['appHistory'],
    queryFn: async () => {
      const response = await apiClient.get('/apply/history');
      return response.data;
    },
  });

  // 9. Saved jobs list
  const savedJobsQuery = useQuery({
    queryKey: ['savedJobs'],
    queryFn: async () => {
      const response = await apiClient.get('/jobs/saved/list');
      return response.data;
    },
  });

  // 10. Save job mutation
  const saveJobMutation = useMutation({
    mutationFn: async (jobData) => {
      const response = await apiClient.post('/jobs/saved/save', jobData);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['savedJobs'] });
    },
  });

  // 11. Remove saved job mutation
  const removeSavedJobMutation = useMutation({
    mutationFn: async (savedJobId) => {
      const response = await apiClient.delete(`/jobs/saved/${savedJobId}`);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['savedJobs'] });
    },
  });

  // 12. Update saved job notes mutation
  const updateSavedJobNotesMutation = useMutation({
    mutationFn: async ({ savedJobId, notes }) => {
      const response = await apiClient.patch(
        `/jobs/saved/${savedJobId}/notes`,
        { notes }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['savedJobs'] });
    },
  });

  // Polling helper
  const pollJobStatus = async (jobId, onComplete, onError, intervalMs = 3000) => {
    const timer = setInterval(async () => {
      try {
        const response = await apiClient.get(`/jobs/${jobId}/status`);
        const { status, result, error } = response.data;
        
        if (status === 'completed') {
          clearInterval(timer);
          onComplete(result);
        } else if (status === 'failed') {
          clearInterval(timer);
          onError(error || 'Task execution failed.');
        }
      } catch (err) {
        clearInterval(timer);
        onError(err.message || 'Error checking task status.');
      }
    }, intervalMs);
    
    return () => clearInterval(timer);
  };

  return {
    jobs: jobsQuery.data || [],
    isLoadingJobs: jobsQuery.isLoading,
    refetchJobs: jobsQuery.refetch,
    
    matchedJobs: matchedJobsQuery.data || [],
    isLoadingMatchedJobs: matchedJobsQuery.isLoading,
    refetchMatchedJobs: matchedJobsQuery.refetch,
    
    criteria: criteriaQuery.data,
    isLoadingCriteria: criteriaQuery.isLoading,
    saveCriteria: saveCriteriaMutation.mutateAsync,
    
    fetchJobs: fetchJobsMutation.mutateAsync,
    isFetchingJobs: fetchJobsMutation.isPending,
    
    generateApplication: generateApplicationMutation.mutateAsync,
    isGeneratingApp: generateApplicationMutation.isPending,
    
    submitApplication: submitApplicationMutation.mutateAsync,
    isSubmittingApp: submitApplicationMutation.isPending,
    
    appHistory: historyQuery.data || [],
    isLoadingHistory: historyQuery.isLoading,

    savedJobs: savedJobsQuery.data || [],
    isLoadingSavedJobs: savedJobsQuery.isLoading,
    refetchSavedJobs: savedJobsQuery.refetch,
    saveJob: saveJobMutation.mutateAsync,
    isSavingJob: saveJobMutation.isPending,
    removeSavedJob: removeSavedJobMutation.mutateAsync,
    isRemovingSavedJob: removeSavedJobMutation.isPending,
    updateSavedJobNotes: updateSavedJobNotesMutation.mutateAsync,
    isUpdatingSavedJobNotes: updateSavedJobNotesMutation.isPending,
    
    pollJobStatus,
  };
};

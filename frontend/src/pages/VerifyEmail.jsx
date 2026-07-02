import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import apiClient from '../api/client';

export const VerifyEmail = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  
  const [verifying, setVerifying] = useState(true);
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState('');
  const token = searchParams.get('token');

  useEffect(() => {
    const verifyEmailToken = async () => {
      if (!token) {
        setError('No verification token provided');
        setVerifying(false);
        return;
      }

      try {
        const res = await apiClient.get(`/auth/verify-email/${token}`);
        setVerified(true);
        setError('');
        toast.success('Email verified successfully!');
        
        // Redirect to login after 2 seconds
        setTimeout(() => {
          navigate('/auth?mode=login');
        }, 2000);
      } catch (err) {
        const errorMsg = err.response?.data?.detail || 'Email verification failed';
        setError(errorMsg);
        setVerified(false);
        toast.error(errorMsg);
      } finally {
        setVerifying(false);
      }
    };

    verifyEmailToken();
  }, [token, navigate]);

  if (verifying) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-slate-800 rounded-lg shadow-lg p-8 border border-purple-500/30">
          <div className="flex flex-col items-center gap-4">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
            <h2 className="text-xl font-semibold text-white">Verifying Your Email...</h2>
            <p className="text-slate-400 text-center">Please wait while we verify your email address.</p>
          </div>
        </div>
      </div>
    );
  }

  if (verified) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-slate-800 rounded-lg shadow-lg p-8 border border-green-500/30">
          <div className="flex flex-col items-center gap-4">
            <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center">
              <svg className="w-8 h-8 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white">Email Verified!</h2>
            <p className="text-slate-400 text-center">Your email has been successfully verified. You can now log in to your account.</p>
            <p className="text-slate-500 text-sm">Redirecting you to login...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-slate-800 rounded-lg shadow-lg p-8 border border-red-500/30">
        <div className="flex flex-col items-center gap-4">
          <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center">
            <svg className="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-white">Verification Failed</h2>
          <p className="text-slate-400 text-center">{error}</p>
          <div className="flex gap-3 w-full pt-4">
            <button
              onClick={() => navigate('/auth?mode=register')}
              className="flex-1 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors"
            >
              Register Again
            </button>
            <button
              onClick={() => navigate('/')}
              className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg font-medium transition-colors"
            >
              Go Home
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VerifyEmail;

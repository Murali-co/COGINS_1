import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';
import apiClient from '../api/client';

// Email validation helper
const isValidEmail = (email) =>
  /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

export const Auth = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { login, register, isAuthenticated } = useAuth();

  // Mode can be: 'login', 'register', 'forgot', 'reset'
  const [authMode, setAuthMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const mode = searchParams.get('mode');
    if (mode === 'register') {
      setAuthMode('register');
    } else {
      setAuthMode('login');
    }
  }, [searchParams]);

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard');
    }
  }, [isAuthenticated, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (authMode === 'login') {
      if (!email || !password) {
        toast.error('Please fill in all required fields.');
        return;
      }
      if (!isValidEmail(email)) {
        toast.error('Please enter a valid email address.');
        return;
      }
      setSubmitting(true);
      try {
        await login(email, password);
        toast.success('Logged in successfully!');
        navigate('/dashboard');
      } catch (err) {
        toast.error(err || 'Authentication failed. Please try again.');
      } finally {
        setSubmitting(false);
      }
    } else if (authMode === 'register') {
      if (!email || !password || !fullName) {
        toast.error('Please fill in all required fields.');
        return;
      }
      if (!isValidEmail(email)) {
        toast.error('Please enter a valid email address.');
        return;
      }
      if (password.length < 6) {
        toast.error('Password must be at least 6 characters.');
        return;
      }
      setSubmitting(true);
      try {
        const res = await register(email, password, fullName);
        toast.success(res?.message || 'Registration successful! Please check your email to verify.');
        setAuthMode('login');
        setPassword('');
      } catch (err) {
        toast.error(err || 'Registration failed. Please try again.');
      } finally {
        setSubmitting(false);
      }
    } else if (authMode === 'forgot') {
      if (!email) {
        toast.error('Please enter your email.');
        return;
      }
      if (!isValidEmail(email)) {
        toast.error('Please enter a valid email address.');
        return;
      }
      setSubmitting(true);
      try {
        const res = await apiClient.post('/auth/forgot-password', { email });
        toast.success('Reset token generated! Auto-populated below.');
        if (res.data && res.data.reset_token) {
          setResetToken(res.data.reset_token);
        }
        setAuthMode('reset');
      } catch (err) {
        toast.error(err.response?.data?.detail || 'Failed to request reset. Verify your email.');
      } finally {
        setSubmitting(false);
      }
    } else if (authMode === 'reset') {
      if (!resetToken || !password) {
        toast.error('Please enter the token and your new password.');
        return;
      }
      if (password.length < 6) {
        toast.error('Password must be at least 6 characters.');
        return;
      }
      setSubmitting(true);
      try {
        await apiClient.post('/auth/reset-password', {
          token: resetToken,
          new_password: password
        });
        toast.success('Password updated successfully. You can now login.');
        setAuthMode('login');
        setPassword('');
      } catch (err) {
        toast.error(err.response?.data?.detail || 'Invalid or expired token.');
      } finally {
        setSubmitting(false);
      }
    }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center px-4 sm:px-6 lg:px-8 py-12 relative">
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80 h-80 rounded-full bg-indigo-600/5 blur-[80px] pointer-events-none"></div>

      <div className="max-w-md w-full space-y-8 glass-panel border p-8 rounded-2xl relative z-10">
        {/* Title */}
        <div className="text-center">
          <h2 className="text-3xl font-extrabold tracking-tight text-dark-50">
            {authMode === 'login' && 'Welcome Back'}
            {authMode === 'register' && 'Create Account'}
            {authMode === 'forgot' && 'Reset Password'}
            {authMode === 'reset' && 'Enter New Password'}
          </h2>
          <p className="mt-2 text-xs text-dark-400">
            {authMode === 'login' && 'Enter credentials to access your Career Copilot'}
            {authMode === 'register' && 'Sign up to build your local resume database'}
            {authMode === 'forgot' && 'We will generate an access token to update your password'}
            {authMode === 'reset' && 'Please provide your security token and select a new password'}
          </p>
        </div>

        {/* Form */}
        <form className="mt-8 space-y-4" onSubmit={handleSubmit}>
          {authMode === 'register' && (
            <div>
              <label className="block text-xs font-semibold text-dark-300 mb-1.5">Full Name</label>
              <input
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full px-4 py-2.5 bg-dark-950 border border-dark-800 focus:border-indigo-500/40 rounded-xl text-sm text-dark-100 focus:outline-none transition-all"
                placeholder="John Doe"
              />
            </div>
          )}

          {(authMode === 'login' || authMode === 'register' || authMode === 'forgot') && (
            <div>
              <label className="block text-xs font-semibold text-dark-300 mb-1.5">Email Address</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-2.5 bg-dark-950 border border-dark-800 focus:border-indigo-500/40 rounded-xl text-sm text-dark-100 focus:outline-none transition-all"
                placeholder="name@example.com"
              />
            </div>
          )}

          {authMode === 'reset' && (
            <div>
              <label className="block text-xs font-semibold text-dark-300 mb-1.5">Security Token</label>
              <textarea
                rows={3}
                required
                value={resetToken}
                onChange={(e) => setResetToken(e.target.value)}
                className="w-full px-4 py-2.5 bg-dark-950 border border-dark-800 focus:border-indigo-500/40 rounded-xl text-xs text-dark-100 focus:outline-none transition-all font-mono"
                placeholder="Paste your reset token here"
              />
            </div>
          )}

          {(authMode === 'login' || authMode === 'register' || authMode === 'reset') && (
            <div>
              <label className="block text-xs font-semibold text-dark-300 mb-1.5">
                {authMode === 'reset' ? 'New Password' : 'Password'}
              </label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-2.5 bg-dark-950 border border-dark-800 focus:border-indigo-500/40 rounded-xl text-sm text-dark-100 focus:outline-none transition-all"
                placeholder="••••••••"
              />
            </div>
          )}

          {authMode === 'login' && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => setAuthMode('forgot')}
                className="text-xs text-indigo-400 hover:text-indigo-300 hover:underline"
              >
                Forgot Password?
              </button>
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full py-3 mt-4 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-sm transition-all disabled:opacity-50 flex justify-center items-center"
          >
            {submitting ? (
              <span className="w-5 h-5 border-2 border-t-transparent border-white rounded-full animate-spin"></span>
            ) : (
              <>
                {authMode === 'login' && 'Sign In'}
                {authMode === 'register' && 'Register'}
                {authMode === 'forgot' && 'Generate Reset Token'}
                {authMode === 'reset' && 'Save New Password'}
              </>
            )}
          </button>
        </form>

        {/* Toggle Mode */}
        <div className="text-center text-xs text-dark-400 pt-2 flex flex-col space-y-2">
          {authMode === 'login' && (
            <div>
              Don't have an account?
              <button
                onClick={() => setAuthMode('register')}
                className="text-indigo-400 hover:text-indigo-300 font-bold ml-1 transition-all"
              >
                Sign up now
              </button>
            </div>
          )}
          {authMode === 'register' && (
            <div>
              Already have an account?
              <button
                onClick={() => setAuthMode('login')}
                className="text-indigo-400 hover:text-indigo-300 font-bold ml-1 transition-all"
              >
                Sign in instead
              </button>
            </div>
          )}
          {(authMode === 'forgot' || authMode === 'reset') && (
            <div>
              Back to
              <button
                onClick={() => setAuthMode('login')}
                className="text-indigo-400 hover:text-indigo-300 font-bold ml-1 transition-all"
              >
                Sign In
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
export default Auth;

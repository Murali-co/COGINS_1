import React, { createContext, useState, useEffect, useContext } from 'react';
import apiClient from '../api/client';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Restore session on mount
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const response = await apiClient.get('/auth/me');
        setUser(response.data);
      } catch (error) {
        setUser(null);
      } finally {
        setLoading(false);
      }
    };
    checkAuth();
  }, []);

  const login = async (email, password) => {
    setLoading(true);
    try {
      const response = await apiClient.post('/auth/login', { email, password });
      if (response.data?.requires_2fa) {
        setLoading(false);
        return { requires_2fa: true, pending_token: response.data.pending_token };
      }

      const { access_token } = response.data;
      if (access_token) {
        localStorage.setItem('token', access_token);
      }
      
      // Fetch user details
      const userRes = await apiClient.get('/auth/me');
      setUser(userRes.data);
      setLoading(false);
      return userRes.data;
    } catch (error) {
      setLoading(false);
      throw error.response?.data?.detail || "Invalid credentials. Please try again.";
    }
  };

  const verify2FA = async (pendingToken, code) => {
    setLoading(true);
    try {
      const response = await apiClient.post('/auth/2fa/verify', {
        pending_token: pendingToken,
        code,
      });
      const { access_token } = response.data;
      if (access_token) {
        localStorage.setItem('token', access_token);
      }
      const userRes = await apiClient.get('/auth/me');
      setUser(userRes.data);
      setLoading(false);
      return userRes.data;
    } catch (error) {
      setLoading(false);
      throw error.response?.data?.detail || "2FA verification failed.";
    }
  };

  const register = async (email, password, fullName) => {
    setLoading(true);
    try {
      const response = await apiClient.post('/auth/register', {
        email,
        password,
        full_name: fullName,
      });
      setLoading(false);
      return response.data;
    } catch (error) {
      setLoading(false);
      throw error.response?.data?.detail || "Registration failed. Try again.";
    }
  };

  const logout = async () => {
    try {
      await apiClient.post('/auth/logout');
    } catch (error) {
      console.error("Logout request failed:", error);
    }
    localStorage.removeItem('token');
    setUser(null);
  };

  const value = {
    user,
    loading,
    login,
    verify2FA,
    register,
    logout,
    isAuthenticated: !!user,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

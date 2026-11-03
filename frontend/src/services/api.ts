import axios from 'axios';
import { OptimizationResultItem, BatchJobResponse } from '../types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

const client = axios.create({
  baseURL: `${API_BASE_URL}/api/v2`,
});

client.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('isp_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

export const api = {
  uploadFiles: async (files: File[]) => {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    const response = await client.post('/uploads', formData);
    return response.data;
  },

  submitJob: async (formData: FormData) => {
    const response = await client.post('/optimization-jobs', formData);
    return response.data;
  },

  getJobStatus: async (jobId: string) => {
    const response = await client.get(`/jobs/${jobId}`);
    return response.data;
  },

  getJobResults: async (jobId: string) => {
    const response = await client.get(`/jobs/${jobId}/results`);
    return response.data;
  },

  getDownloadZipUrl: (jobId: string) => `${API_BASE_URL}/api/v2/downloads/${jobId}`,
  getDownloadCsvUrl: (jobId: string) => `${API_BASE_URL}/api/v2/downloads/${jobId}/csv`,
  getDownloadFileUrl: (jobId: string, imageId: string) => `${API_BASE_URL}/api/v2/downloads/${jobId}/file/${imageId}`,
};


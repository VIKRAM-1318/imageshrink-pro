export interface ImageOptimizationJob {
  batch_id: string;
  total_files: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  mode: 'lossless' | 'visual' | 'custom';
  progress_percentage: number;
}

export interface OptimizationResultItem {
  image_id: string;
  original_filename: string;
  original_format: string;
  original_size: number;
  output_filename?: string;
  output_format?: string;
  output_size?: number;
  bytes_saved: number;
  percentage_saved: number;
  ssim_score?: number;
  psnr_score?: number;
  status: string;
}

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  plan: 'free' | 'pro' | 'business';
  is_admin: boolean;
}


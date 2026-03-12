
import React from 'react';
import {
  Zap,
  ShieldCheck,
  Globe,
  Cpu,
  Database,
  BriefcaseBusiness,
  HandCoins,
  GitBranch,
  Siren,
} from 'lucide-react';

export const THEME = {
  colors: {
    primary: '#2563eb',
    background: '#030712',
    surface: '#0f172a',
    accent: '#8b5cf6',
  },
  animation: {
    pulse: 'animate-pulse',
    spin: 'animate-spin',
  }
};

export const CATEGORIES = [
  { id: 'research', label: 'Research', icon: <Database className="w-4 h-4" /> },
  { id: 'product', label: 'Product', icon: <Zap className="w-4 h-4" /> },
  { id: 'company', label: 'Company', icon: <BriefcaseBusiness className="w-4 h-4" /> },
  { id: 'funding', label: 'Funding', icon: <HandCoins className="w-4 h-4" /> },
  { id: 'policy', label: 'Policy', icon: <ShieldCheck className="w-4 h-4" /> },
  { id: 'open-source', label: 'Open Source', icon: <GitBranch className="w-4 h-4" /> },
  { id: 'hardware', label: 'Hardware', icon: <Cpu className="w-4 h-4" /> },
  { id: 'security', label: 'Security', icon: <Siren className="w-4 h-4" /> },
  { id: 'general', label: 'General', icon: <Globe className="w-4 h-4" /> },
];

export interface CategoryConfig {
  color: string;
  borderColor: string;
  bgMuted: string;
}

const CATEGORY_COLOR_MAP: Record<string, CategoryConfig> = {
  Research: { color: '#1d4ed8', borderColor: '#1d4ed8', bgMuted: 'rgba(29, 78, 216, 0.2)' },
  Product: { color: '#ef4444', borderColor: '#ef4444', bgMuted: 'rgba(239, 68, 68, 0.2)' },
  Company: { color: '#14b8a6', borderColor: '#14b8a6', bgMuted: 'rgba(20, 184, 166, 0.2)' },
  Funding: { color: '#8b5cf6', borderColor: '#8b5cf6', bgMuted: 'rgba(139, 92, 246, 0.2)' },
  Policy: { color: '#d97706', borderColor: '#d97706', bgMuted: 'rgba(217, 119, 6, 0.2)' },
  'Open Source': { color: '#16a34a', borderColor: '#16a34a', bgMuted: 'rgba(22, 163, 74, 0.2)' },
  Hardware: { color: '#2563eb', borderColor: '#2563eb', bgMuted: 'rgba(37, 99, 235, 0.2)' },
  Security: { color: '#c026d3', borderColor: '#c026d3', bgMuted: 'rgba(192, 38, 211, 0.2)' },
  General: { color: '#6b7280', borderColor: '#6b7280', bgMuted: 'rgba(107, 114, 128, 0.18)' },
};

const DEFAULT_CATEGORY: CategoryConfig = {
  color: 'var(--ink)',
  borderColor: 'var(--ink)',
  bgMuted: 'transparent',
};

export function getCategoryConfig(category: string): CategoryConfig {
  return CATEGORY_COLOR_MAP[category] || DEFAULT_CATEGORY;
}

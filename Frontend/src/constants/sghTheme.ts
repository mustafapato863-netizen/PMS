/**
 * Saudi German Health (SGH) Design System - Brand Color & Theme Tokens
 * Ported from official enterprise healthcare design system contract.
 * WCAG AAA / AA compliant contrast ratios.
 */

export const sghColors = {
  // 1. Primary Brand Identity Tokens
  brand: {
    cyan: {
      light: '#38BDF8',   // Light cyan for dark mode highlights
      default: '#00A3E0', // Official SGH Cyan
      dark: '#0084CE',    // Deep Cyan for borders / action accents
      deep: '#0069B4',    // Royal Cyan-Blue wing shadow
    },
    emerald: {
      lime: '#43B02A',    // Lime crest accent
      default: '#00A859', // Official SGH Emerald Green
      dark: '#00843D',    // Deep Hospital Emerald
      forest: '#005A2B',  // Forest green wing shadow
    },
    navy: {
      light: '#1E293B',
      default: '#0F172A',
      dark: '#0B132B',    // Deep Healthcare Space Navy (dark mode canvas)
      deepest: '#030712',
    },
  },

  // 2. Semantic Status Tokens
  status: {
    success: {
      bg: 'rgba(0, 168, 89, 0.1)',
      border: 'rgba(0, 168, 89, 0.3)',
      text: '#00A859',
      textDark: '#34D399',
    },
    info: {
      bg: 'rgba(0, 163, 224, 0.1)',
      border: 'rgba(0, 163, 224, 0.3)',
      text: '#0084CE',
      textDark: '#38BDF8',
    },
    warning: {
      bg: 'rgba(245, 158, 11, 0.1)',
      border: 'rgba(245, 158, 11, 0.3)',
      text: '#D97706',
      textDark: '#FBBF24',
    },
    error: {
      bg: 'rgba(239, 68, 68, 0.1)',
      border: 'rgba(239, 68, 68, 0.3)',
      text: '#DC2626',
      textDark: '#F87171',
    },
    neutral: {
      bg: 'rgba(100, 116, 139, 0.1)',
      border: 'rgba(100, 116, 139, 0.2)',
      text: '#64748B',
      textDark: '#94A3B8',
    },
  },

  // 3. Surface & Neutral Tokens
  surfaces: {
    light: {
      bg: '#F8FAFC',
      card: '#FFFFFF',
      cardHover: '#F1F5F9',
      border: '#E2E8F0',
      textPrimary: '#0F172A',
      textSecondary: '#475569',
      textMuted: '#64748B',
    },
    dark: {
      bg: '#0B132B',
      card: '#0F1A2E',
      cardElevated: '#152236',
      cardHover: '#182638',
      border: 'rgba(255, 255, 255, 0.12)',
      textPrimary: '#F8FAFC',
      textSecondary: '#CBD5E1',
      textMuted: '#94A3B8',
    },
  },
} as const;

export const sghGradients = {
  // Brand Text Gradient
  brandText: 'linear-gradient(135deg, #00A3E0 0%, #00A859 100%)',

  // Brand Surface & Button Gradient
  brandButton: 'linear-gradient(135deg, #0084CE 0%, #00A3E0 45%, #00A859 100%)',
  brandButtonHover: 'linear-gradient(135deg, #0072CE 0%, #0092D0 45%, #00974E 100%)',

  // Left Wing (Cyan -> Blue)
  leftWing: 'linear-gradient(135deg, #00B5F1 0%, #00A3E0 45%, #0069B4 100%)',

  // Right Wing (Lime -> Emerald -> Forest Green)
  rightWing: 'linear-gradient(135deg, #43B02A 0%, #00A859 35%, #00843D 80%, #005A2B 100%)',

  // Ambient Mesh Background Gradients
  ambientMeshLight:
    'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 163, 224, 0.15), transparent 70%), radial-gradient(ellipse 60% 40% at 100% 100%, rgba(0, 168, 89, 0.1), transparent 60%)',
  ambientMeshDark:
    'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 163, 224, 0.22), transparent 70%), radial-gradient(ellipse 60% 40% at 100% 100%, rgba(0, 168, 89, 0.15), transparent 60%)',

  // Rotating Card Border Frame
  conicBorder:
    'conic-gradient(from var(--border-angle, 0deg) at 50% 50%, #00A3E0 0%, #00A859 25%, #0069B4 50%, #43B02A 75%, #00A3E0 100%)',
} as const;

export type SghColors = typeof sghColors;
export type SghGradients = typeof sghGradients;

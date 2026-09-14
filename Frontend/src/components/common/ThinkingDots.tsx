import React, { useEffect, useRef } from 'react';

export interface ThinkingDotsProps {
  dotSize?: number;
  spacing?: number;
  speed?: number;
  className?: string;
  isDark?: boolean;
}

/**
 * ThinkingDots - Ambient canvas particle grid wave effect.
 * Renders an ethereal, pulsing matrix of dots with responsive resize and high-DPI scaling.
 * Interpolates between SGH Cyan (#00A3E0) and SGH Emerald (#00A859).
 */
export const ThinkingDots: React.FC<ThinkingDotsProps> = ({
  dotSize = 1.6,
  spacing = 30,
  speed = 0.0014,
  className = '',
  isDark = true,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    // Check prefers-reduced-motion
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (mediaQuery.matches) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return;

    let animationFrameId: number;
    let isPaused = document.visibilityState !== 'visible';

    const handleResize = () => {
      if (!canvas) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    handleResize();
    window.addEventListener('resize', handleResize);

    const handleVisibility = () => {
      isPaused = document.visibilityState !== 'visible';
    };
    document.addEventListener('visibilitychange', handleVisibility);

    let time = 0;

    const draw = () => {
      if (!isPaused && canvas) {
        const displayW = window.innerWidth;
        const displayH = window.innerHeight;

        ctx.clearRect(0, 0, displayW, displayH);

        const cols = Math.ceil(displayW / spacing) + 1;
        const rows = Math.ceil(displayH / spacing) + 1;

        for (let i = 0; i < cols; i++) {
          for (let j = 0; j < rows; j++) {
            const x = i * spacing;
            const y = j * spacing;

            // Fluid dual-sine wave equation
            const dist = Math.sin(i * 0.16 + time) + Math.cos(j * 0.16 + time);
            const normalized = (dist + 2) / 4; // 0 to 1

            const currentDotSize = dotSize * (0.6 + normalized * 0.9);

            // Interpolate between SGH Cyan (0, 163, 224) and Emerald (0, 168, 89)
            if (isDark) {
              const opacity = 0.07 + normalized * 0.32;
              const isCyan = (i + j) % 2 === 0;
              ctx.fillStyle = `rgba(${isCyan ? '0, 163, 224' : '0, 168, 89'}, ${opacity})`;
            } else {
              const opacity = 0.05 + normalized * 0.22;
              const isCyan = (i + j) % 2 === 0;
              ctx.fillStyle = `rgba(${isCyan ? '0, 132, 206' : '0, 168, 89'}, ${opacity})`;
            }

            ctx.beginPath();
            ctx.arc(x, y, currentDotSize, 0, Math.PI * 2);
            ctx.fill();
          }
        }

        time += speed;
      }

      animationFrameId = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      window.removeEventListener('resize', handleResize);
      document.removeEventListener('visibilitychange', handleVisibility);
      cancelAnimationFrame(animationFrameId);
    };
  }, [dotSize, spacing, speed, isDark]);

  return (
    <canvas
      ref={canvasRef}
      className={`fixed inset-0 pointer-events-none z-0 ${className}`.trim()}
      style={{ width: '100%', height: '100%' }}
      aria-hidden="true"
    />
  );
};

export default ThinkingDots;

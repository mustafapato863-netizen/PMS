import React, { useState } from 'react';
import { motion } from 'framer-motion';
import SghHeartSvg from './SghHeartSvg';

export interface SghAnimatedLogoProps {
  size?: number;
  showText?: boolean;
  title?: string;
  subtitle?: string;
  className?: string;
}

export const SghAnimatedLogo: React.FC<SghAnimatedLogoProps> = ({
  size = 72,
  showText = true,
  title = 'SGH Hub',
  subtitle = 'Performance Intelligence Portal',
  className = '',
}) => {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <div
      className={`login-brand flex flex-col items-center justify-center select-none text-center group cursor-pointer ${className}`.trim()}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* 1. Interactive Animated Vector Emblem */}
      <div className="relative flex items-center justify-center" style={{ width: size * 1.35, height: size * 1.25 }}>
        {/* Pulsing Cyan / Emerald Ambient Glow Halo */}
        <motion.div
          animate={{
            scale: isHovered ? [1.08, 1.28, 1.08] : [1, 1.16, 1],
            opacity: isHovered ? [0.65, 0.9, 0.65] : [0.38, 0.58, 0.38],
          }}
          transition={{
            duration: isHovered ? 1.6 : 3,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
          className="absolute inset-0 rounded-full bg-gradient-to-tr from-[#00A3E0]/45 via-[#00A859]/35 to-[#00843D]/25 blur-2xl pointer-events-none"
        />

        {/* Floating Dual-Wing Heart with Spring Hover Effect */}
        <motion.div
          animate={{
            y: isHovered ? [0, -6, 0] : [0, -4, 0],
            rotate: isHovered ? [0, 1.8, -1.8, 0] : [0, 0.8, -0.8, 0],
          }}
          whileHover={{ scale: 1.08 }}
          whileTap={{ scale: 0.96 }}
          transition={{
            duration: isHovered ? 1.8 : 3.4,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
          className="relative z-10 filter drop-shadow-[0_8px_20px_rgba(0,163,224,0.45)]"
        >
          <SghHeartSvg size={size} glow />
        </motion.div>
      </div>

      {/* 2. Brand Typography with Smooth Staggered Reveal */}
      {showText && (
        <div className="mt-3 flex flex-col items-center">
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.15 }}
            className="flex items-center gap-1.5 font-black tracking-tight text-[var(--text-primary,#f8fafc)] text-2xl sm:text-[26px]"
          >
            <span>{title}</span>
          </motion.div>

          {subtitle && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.3 }}
              className="mt-1 text-[11px] font-bold uppercase tracking-[0.22em] text-[var(--sgh-cyan-primary,#00A3E0)]"
            >
              {subtitle}
            </motion.p>
          )}
        </div>
      )}
    </div>
  );
};

export default SghAnimatedLogo;

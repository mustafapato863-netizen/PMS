import * as React from 'react';

export interface SghHeartSvgProps extends React.SVGProps<SVGSVGElement> {
  size?: number;
  className?: string;
  glow?: boolean;
}

/**
 * Pure Vector SVG of the Saudi German Hospital Dual-Wing Heart Emblem.
 * - Left Wing: Royal Blue to Cyan Gradient (#00B5F1 -> #0069B4)
 * - Right Wing: Lime to Emerald to Forest Green (#43B02A -> #005A2B)
 */
export function SghHeartSvg({
  size = 40,
  className = '',
  glow = false,
  ...props
}: SghHeartSvgProps) {
  const uniqueId = React.useId().replace(/:/g, '-');

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 130 115"
      width={size}
      height={Math.round((size * 115) / 130)}
      fill="none"
      className={`inline-block shrink-0 transition-transform duration-300 ${
        glow ? 'filter drop-shadow-[0_4px_16px_rgba(0,163,224,0.45)]' : ''
      } ${className}`.trim()}
      {...props}
    >
      <defs>
        {/* Left Wing Linear Gradient: Cyan -> Royal Blue */}
        <linearGradient id={`sgh-left-grad-${uniqueId}`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#00B5F1" />
          <stop offset="45%" stopColor="#00A3E0" />
          <stop offset="100%" stopColor="#0069B4" />
        </linearGradient>

        {/* Left Wing 3D Volume Shadow */}
        <linearGradient id={`sgh-left-vol-${uniqueId}`} x1="20%" y1="0%" x2="80%" y2="100%">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.25" />
          <stop offset="60%" stopColor="#0080C8" stopOpacity="0" />
          <stop offset="100%" stopColor="#004A80" stopOpacity="0.45" />
        </linearGradient>

        {/* Right Wing Linear Gradient: Vivid Lime/Emerald -> Deep Forest Green */}
        <linearGradient id={`sgh-right-grad-${uniqueId}`} x1="30%" y1="0%" x2="70%" y2="100%">
          <stop offset="0%" stopColor="#43B02A" />
          <stop offset="35%" stopColor="#00A859" />
          <stop offset="80%" stopColor="#00843D" />
          <stop offset="100%" stopColor="#005A2B" />
        </linearGradient>

        {/* Right Wing 3D Crest Highlight */}
        <linearGradient id={`sgh-right-crest-${uniqueId}`} x1="0%" y1="0%" x2="100%" y2="70%">
          <stop offset="0%" stopColor="#8AE356" stopOpacity="0.8" />
          <stop offset="40%" stopColor="#00A859" stopOpacity="0" />
          <stop offset="100%" stopColor="#003E1C" stopOpacity="0.5" />
        </linearGradient>

        {/* Soft Drop Filter */}
        <filter id={`sgh-soft-shadow-${uniqueId}`} x="-15%" y="-15%" width="130%" height="130%">
          <feDropShadow dx="0" dy="2" stdDeviation="2" floodColor="#0069B4" floodOpacity="0.2" />
        </filter>
      </defs>

      {/* Left Cyan Heart Wing */}
      <g filter={`url(#sgh-soft-shadow-${uniqueId})`}>
        <path
          d="M 57 26.5 C 50 21.5 39 16 26 17 C 14 18 5 26.5 4.5 38.5 C 4 50 12.5 60.5 22.5 68 C 34 76.5 48 81 56 81.5 C 49 78 37 72 27.5 64 C 18.5 56.5 13.5 48 14 38.5 C 14.5 29.5 21 23.5 30 23 C 38.5 22.5 48.5 26.5 57 26.5 Z"
          fill={`url(#sgh-left-grad-${uniqueId})`}
        />
        <path
          d="M 57 26.5 C 50 21.5 39 16 26 17 C 14 18 5 26.5 4.5 38.5 C 4 50 12.5 60.5 22.5 68 C 34 76.5 48 81 56 81.5 C 49 78 37 72 27.5 64 C 18.5 56.5 13.5 48 14 38.5 C 14.5 29.5 21 23.5 30 23 C 38.5 22.5 48.5 26.5 57 26.5 Z"
          fill={`url(#sgh-left-vol-${uniqueId})`}
        />
      </g>

      {/* Right Emerald Green Heart Wing */}
      <g filter={`url(#sgh-soft-shadow-${uniqueId})`}>
        <path
          d="M 57 36 C 65.5 28.5 78 14 93.5 7.5 C 109 1 122 7.5 126.5 20 C 131 32 126.5 45.5 118.5 58.5 C 107.5 77 87 97 55.5 116.5 C 81.5 99 103 80 112 63.5 C 120 49.5 122 37.5 118.5 28 C 114 17 104 11.5 92 15 C 78.5 19 66.5 29 57 36 Z"
          fill={`url(#sgh-right-grad-${uniqueId})`}
        />
        <path
          d="M 57 36 C 65.5 28.5 78 14 93.5 7.5 C 109 1 122 7.5 126.5 20 C 131 32 126.5 45.5 118.5 58.5 C 107.5 77 87 97 55.5 116.5 C 81.5 99 103 80 112 63.5 C 120 49.5 122 37.5 118.5 28 C 114 17 104 11.5 92 15 C 78.5 19 66.5 29 57 36 Z"
          fill={`url(#sgh-right-crest-${uniqueId})`}
        />
      </g>
    </svg>
  );
}

export default SghHeartSvg;

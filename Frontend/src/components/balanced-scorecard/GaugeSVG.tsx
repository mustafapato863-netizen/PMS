import { useId } from "react";
import { getGaugeTone } from "./gaugeTone";

interface GaugeSVGProps {
  score: number | null | undefined;
  size?: number;
  label?: string;
  className?: string;
}

const ARC_PATH = "M12 48 A36 36 0 0 1 84 48";
const VIEWBOX_WIDTH = 96;
const VIEWBOX_HEIGHT = 60;
const CENTER = { x: 48, y: 48 };

function clampScore(score: number | null | undefined) {
  if (score == null || !Number.isFinite(score)) return 0;
  return Math.min(100, Math.max(0, score));
}

function polarPoint(angle: number, radius: number) {
  const radians = (angle * Math.PI) / 180;
  return {
    x: CENTER.x + radius * Math.cos(radians),
    y: CENTER.y + radius * Math.sin(radians),
  };
}

export function GaugeSVG({
  score,
  size = 112,
  label = "Performance score",
  className,
}: GaugeSVGProps) {
  const titleId = useId();
  const gradientId = useId();
  const filterId = useId();
  const hasScore = score != null && Number.isFinite(score);
  const normalizedScore = clampScore(score);
  const tone = getGaugeTone(score);
  const needle = polarPoint(180 + (normalizedScore / 100) * 180, 25.5);
  const gaugeHeight = Math.round(size * (VIEWBOX_HEIGHT / VIEWBOX_WIDTH));
  const ticks = [0, 25, 50, 75, 100];

  return (
    <svg
      width={size}
      height={gaugeHeight}
      viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
      role="img"
      aria-labelledby={titleId}
      className={className}
      style={{ overflow: "visible", display: "block" }}
    >
      <title id={titleId}>
        {hasScore
          ? `${label}: ${normalizedScore.toFixed(1)}%`
          : `${label}: no data available`}
      </title>

      <defs>
        <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor={tone.color} stopOpacity="0.56" />
          <stop offset="58%" stopColor={tone.color} stopOpacity="0.84" />
          <stop offset="100%" stopColor={tone.color} stopOpacity="1" />
        </linearGradient>
        <filter id={filterId} x="-35%" y="-40%" width="170%" height="180%">
          <feDropShadow
            dx="0"
            dy="1.5"
            stdDeviation="2.2"
            floodColor={tone.color}
            floodOpacity="0.28"
          />
        </filter>
      </defs>

      {/* Scale markers provide a quick visual anchor without competing with the score. */}
      {ticks.map((tick) => {
        const angle = 180 + (tick / 100) * 180;
        const outer = polarPoint(angle, 41.5);
        const inner = polarPoint(
          angle,
          tick === 0 || tick === 50 || tick === 100 ? 37.8 : 39.2,
        );

        return (
          <line
            key={tick}
            x1={outer.x}
            y1={outer.y}
            x2={inner.x}
            y2={inner.y}
            stroke="var(--bsc-panel-muted, #94A3B8)"
            strokeWidth={tick === 0 || tick === 50 || tick === 100 ? 1.15 : 0.8}
            strokeLinecap="round"
            opacity={tick === 50 ? 0.68 : 0.4}
          />
        );
      })}

      <path
        d={ARC_PATH}
        fill="none"
        stroke={tone.glow}
        strokeWidth="12"
        strokeLinecap="round"
        opacity={hasScore ? 0.74 : 0.34}
        pathLength="100"
        strokeDasharray={`${hasScore ? normalizedScore : 0} 100`}
        style={{
          transition: "stroke-dasharray 420ms cubic-bezier(.22,1,.36,1)",
        }}
      />

      <path
        d={ARC_PATH}
        fill="none"
        stroke="var(--bsc-table-row, rgba(148, 163, 184, 0.22))"
        strokeWidth="7"
        strokeLinecap="round"
        pathLength="100"
      />

      <path
        d={ARC_PATH}
        fill="none"
        stroke={`url(#${gradientId})`}
        strokeWidth="7"
        strokeLinecap="round"
        pathLength="100"
        strokeDasharray={`${hasScore ? normalizedScore : 0} 100`}
        filter={`url(#${filterId})`}
        style={{
          transition:
            "stroke-dasharray 420ms cubic-bezier(.22,1,.36,1), stroke 220ms ease",
        }}
      />

      {hasScore && (
        <>
          <line
            x1={CENTER.x}
            y1={CENTER.y}
            x2={needle.x}
            y2={needle.y}
            stroke={tone.glow}
            strokeWidth="5.6"
            strokeLinecap="round"
            opacity="0.7"
            style={{
              transition:
                "x2 420ms cubic-bezier(.22,1,.36,1), y2 420ms cubic-bezier(.22,1,.36,1)",
            }}
          />
          <line
            x1={CENTER.x}
            y1={CENTER.y}
            x2={needle.x}
            y2={needle.y}
            stroke="var(--bsc-panel-text, #0F172A)"
            strokeWidth="2.1"
            strokeLinecap="round"
            style={{
              transition:
                "x2 420ms cubic-bezier(.22,1,.36,1), y2 420ms cubic-bezier(.22,1,.36,1)",
            }}
          />
        </>
      )}

      <circle
        cx={CENTER.x}
        cy={CENTER.y}
        r="5.7"
        fill="var(--bsc-panel-bg, #FFFFFF)"
        stroke={tone.color}
        strokeWidth="1.55"
        opacity={hasScore ? 0.7 : 0.45}
      />
      <circle
        cx={CENTER.x}
        cy={CENTER.y}
        r="3.4"
        fill="var(--bsc-panel-bg, #FFFFFF)"
        stroke="var(--bsc-panel-text, #0F172A)"
        strokeWidth="1.7"
        opacity={hasScore ? 1 : 0.55}
      />
      <circle
        cx={CENTER.x}
        cy={CENTER.y}
        r="1.45"
        fill="var(--bsc-panel-text, #0F172A)"
        opacity={hasScore ? 1 : 0.55}
      />

      <text
        x="10"
        y="58"
        textAnchor="middle"
        fontSize="5"
        fontWeight="700"
        fill="var(--bsc-panel-muted, #94A3B8)"
      >
        0
      </text>
      <text
        x="48"
        y="8"
        textAnchor="middle"
        fontSize="5"
        fontWeight="700"
        fill="var(--bsc-panel-muted, #94A3B8)"
      >
        50
      </text>
      <text
        x="86"
        y="58"
        textAnchor="middle"
        fontSize="5"
        fontWeight="700"
        fill="var(--bsc-panel-muted, #94A3B8)"
      >
        100
      </text>
    </svg>
  );
}

export default GaugeSVG;

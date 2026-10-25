'use client';

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import {
  AnimatePresence,
  motion,
  useMotionValue,
  useReducedMotion,
  useSpring,
  useTransform,
  type MotionValue,
  type SpringOptions,
} from 'framer-motion';

function cn(...classes: Array<string | undefined | null | false>): string {
  return classes.filter(Boolean).join(' ');
}

const DEFAULT_BASE_WIDTH = 44;
const DEFAULT_MAGNIFICATION = 68;
const DEFAULT_DISTANCE = 130;
const DEFAULT_PANEL_HEIGHT = 58;

export interface DockProps {
  children: ReactNode;
  className?: string;
  distance?: number;
  panelHeight?: number;
  baseWidth?: number;
  magnification?: number;
  spring?: SpringOptions;
  ariaLabel?: string;
  hidden?: boolean;
  inert?: boolean;
  bare?: boolean;
  'data-testid'?: string;
}

export interface DockItemProps {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
  ariaLabel?: string;
  isActive?: boolean;
  /** Resting width in px. Height still follows the shared icon spring so the row grows as one piece. */
  restWidth?: number;
  'data-testid'?: string;
}

export interface DockLabelProps {
  children: ReactNode;
  className?: string;
  isHovered?: MotionValue<number>;
}

export interface DockIconProps {
  children: ReactNode;
  className?: string;
  width?: MotionValue<number>;
}

interface DocContextType {
  mouseX: MotionValue<number>;
  spring: SpringOptions;
  magnification: number;
  baseWidth: number;
  distance: number;
}

interface DockItemContextType {
  width: MotionValue<number>;
  isHovered: MotionValue<number>;
}

const DockContext = createContext<DocContextType | undefined>(undefined);
const DockItemContext = createContext<DockItemContextType | undefined>(undefined);

function useDock() {
  const context = useContext(DockContext);
  if (!context) {
    throw new Error('useDock must be used within an DockProvider');
  }
  return context;
}

function useDockItem() {
  return useContext(DockItemContext);
}

function Dock({
  children,
  className,
  spring = { mass: 0.1, stiffness: 150, damping: 12 },
  magnification = DEFAULT_MAGNIFICATION,
  baseWidth = DEFAULT_BASE_WIDTH,
  distance = DEFAULT_DISTANCE,
  panelHeight = DEFAULT_PANEL_HEIGHT,
  ariaLabel = 'Quick navigation',
  hidden = false,
  inert = false,
  bare = false,
  'data-testid': dataTestId,
}: DockProps) {
  const mouseX = useMotionValue(Infinity);
  const isHovered = useMotionValue(0);

  return (
    <motion.nav
      onMouseMove={({ pageX }) => {
        isHovered.set(1);
        mouseX.set(pageX);
      }}
      onMouseLeave={() => {
        isHovered.set(0);
        mouseX.set(Infinity);
      }}
      className={cn(
        'mx-auto flex w-fit items-end gap-2',
        bare
          ? 'bg-transparent'
          : 'rounded-2xl border border-slate-200/90 bg-slate-50/90 px-2.5 pb-1.5 shadow-[0_10px_32px_rgba(15,23,42,0.14)] backdrop-blur-xl dark:border-neutral-800 dark:bg-neutral-900/90',
        className,
      )}
      style={{ height: panelHeight }}
      aria-label={ariaLabel}
      hidden={hidden}
      inert={inert}
      data-testid={dataTestId}
    >
      <DockContext.Provider value={{ mouseX, spring, distance, magnification, baseWidth }}>
        {children}
      </DockContext.Provider>
    </motion.nav>
  );
}

function DockItem({
  children,
  className,
  onClick,
  ariaLabel,
  isActive = false,
  restWidth,
  'data-testid': dataTestId,
}: DockItemProps) {
  const ref = useRef<HTMLDivElement>(null);
  const { distance, magnification, baseWidth, mouseX, spring } = useDock();
  const reduceMotion = useReducedMotion();

  const isHovered = useMotionValue(0);

  const mouseDistance = useTransform(mouseX, (val) => {
    const domRect = ref.current?.getBoundingClientRect() ?? { x: 0, width: 0 };
    return val - domRect.x - domRect.width / 2;
  });

  const restingWidth = restWidth ?? baseWidth;
  const peakWidth = reduceMotion ? restingWidth : restingWidth * (magnification / baseWidth);
  const peakHeight = reduceMotion ? baseWidth : magnification;

  const widthTransform = useTransform(
    mouseDistance,
    [-distance, 0, distance],
    [restingWidth, peakWidth, restingWidth],
  );
  const heightTransform = useTransform(
    mouseDistance,
    [-distance, 0, distance],
    [baseWidth, peakHeight, baseWidth],
  );

  const width = useSpring(widthTransform, spring);
  const height = useSpring(heightTransform, spring);
  const iconSize = restWidth == null ? width : height;

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!onClick) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onClick();
    }
  };

  const interactiveProps = onClick
    ? {
        onClick,
        onKeyDown: handleKeyDown,
        tabIndex: 0,
        role: 'button' as const,
        'aria-label': ariaLabel,
        'aria-current': isActive ? ('page' as const) : undefined,
      }
    : {};

  return (
    <DockItemContext.Provider value={{ width: iconSize, isHovered }}>
      <motion.div
        ref={ref}
        style={{ width, height: restWidth == null ? width : height }}
        onHoverStart={() => isHovered.set(1)}
        onHoverEnd={() => isHovered.set(0)}
        onFocusCapture={() => isHovered.set(1)}
        onBlurCapture={() => isHovered.set(0)}
        className={cn(
          'relative inline-flex shrink-0 items-center justify-center rounded-full',
          restWidth == null && 'aspect-square',
          onClick &&
            'cursor-pointer focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none',
          className,
        )}
        data-testid={dataTestId}
        {...interactiveProps}
      >
        {children}
        {isActive && (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute -bottom-1 left-1/2 size-1 -translate-x-1/2 rounded-full bg-[var(--sgh-cyan-primary,#0284c7)]"
          />
        )}
      </motion.div>
    </DockItemContext.Provider>
  );
}

function DockLabel({ children, className, isHovered: propIsHovered }: DockLabelProps) {
  const itemContext = useDockItem();
  const isHovered = propIsHovered ?? itemContext?.isHovered;
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (!isHovered) return;
    const unsubscribe = isHovered.on('change', (latest) => {
      setIsVisible(latest === 1);
    });
    return () => unsubscribe();
  }, [isHovered]);

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0, y: 0 }}
          animate={{ opacity: 1, y: -10 }}
          exit={{ opacity: 0, y: 0 }}
          transition={{ duration: 0.16 }}
          className={cn(
            'pointer-events-none absolute -top-7 left-1/2 z-30 w-fit -translate-x-1/2 rounded-md border border-slate-200/90 bg-white/95 px-2 py-0.5 text-xs font-semibold whitespace-pre text-slate-700 shadow-xs backdrop-blur-md dark:border-neutral-800 dark:bg-neutral-900/95 dark:text-neutral-200',
            className,
          )}
          role="tooltip"
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function DockIcon({ children, className, width: propWidth }: DockIconProps) {
  const itemContext = useDockItem();
  const fallbackWidth = useMotionValue(DEFAULT_BASE_WIDTH);
  const width = propWidth ?? itemContext?.width ?? fallbackWidth;
  const widthTransform = useTransform(width, (val) => Math.round(val * 0.46));

  return (
    <motion.span
      style={{ width: widthTransform, height: widthTransform }}
      className={cn('flex items-center justify-center', className)}
      aria-hidden="true"
    >
      {children}
    </motion.span>
  );
}

export { Dock, DockIcon, DockItem, DockLabel };

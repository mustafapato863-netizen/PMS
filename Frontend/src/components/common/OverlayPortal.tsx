import { useEffect, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

let activeOverlays = 0;
let previousBodyOverflow = '';

export default function OverlayPortal({ children }: { children: ReactNode }) {
  useEffect(() => {
    if (activeOverlays === 0) {
      previousBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
    }
    activeOverlays += 1;

    return () => {
      activeOverlays = Math.max(0, activeOverlays - 1);
      if (activeOverlays === 0) {
        document.body.style.overflow = previousBodyOverflow;
      }
    };
  }, []);

  return createPortal(children, document.body);
}

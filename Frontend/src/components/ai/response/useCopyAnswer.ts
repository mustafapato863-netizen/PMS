import { useEffect, useRef, useState } from 'react';

export function useCopyAnswer() {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const timeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timeout.current), []);

  async function copyAnswer(text: string) {
    clearTimeout(timeout.current);
    setCopyError(false);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      timeout.current = setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
      setCopyError(true);
    }
  }
  return { copied, copyError, copyAnswer };
}

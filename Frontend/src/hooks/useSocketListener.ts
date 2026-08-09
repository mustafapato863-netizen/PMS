/**
 * Socket.io Event Listener Hook
 * Simplified hook for listening to socket events
 */

import { useCallback } from 'react';
import { useSocket } from './useSocket';

interface UseSocketListenerOptions {
  autoConnect?: boolean;
  namespace?: string;
  url?: string;
}

/**
 * Hook to listen to socket events
 * 
 * @example
 * const { on, off } = useSocketListener();
 * 
 * useEffect(() => {
 *   on('notification', (data) => {
 *     console.log('Got notification:', data);
 *   });
 * 
 *   return () => {
 *     off('notification');
 *   };
 * }, [on, off]);
 */
export function useSocketListener(
  options: UseSocketListenerOptions = {}
) {
  const { socket } = useSocket(options);

  const on = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (event: string, handler: (...args: any[]) => void) => {
      if (!socket) return;
      socket.on(event, handler);
    },
    [socket]
  );

  const off = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (event: string, handler?: (...args: any[]) => void) => {
      if (!socket) return;
      if (handler) {
        socket.off(event, handler);
      } else {
        socket.off(event);
      }
    },
    [socket]
  );

  const once = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (event: string, handler: (...args: any[]) => void) => {
      if (!socket) return;
      socket.once(event, handler);
    },
    [socket]
  );

  const emit = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (event: string, data?: any) => {
      if (!socket?.connected) {
        console.warn(`Socket not connected, cannot emit "${event}"`);
        return;
      }
      socket.emit(event, data);
    },
    [socket]
  );

  return {
    socket,
    on,
    off,
    once,
    emit,
  };
}

export default useSocketListener;

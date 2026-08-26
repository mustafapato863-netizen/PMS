/**
 * Socket.io Connection Hook
 * Manages real-time WebSocket connection to backend
 */

import { useEffect, useState } from 'react';
import { io, Socket } from 'socket.io-client';
import { SOCKET_URL } from '../config';
import { getAccessToken } from '../lib/apiClient';

interface UseSocketOptions {
  autoConnect?: boolean;
  namespace?: string;
  url?: string;
}

interface UseSocketReturn {
  socket: Socket | null;
  isConnected: boolean;
  isConnecting: boolean;
  error: Error | null;
}

const DEFAULT_URL = SOCKET_URL;

/**
 * Hook to manage Socket.io connection
 * 
 * @example
 * const { socket, isConnected } = useSocket();
 * 
 * useEffect(() => {
 *   if (socket) {
 *     socket.on('notification', (data) => {
 *       console.log('Notification:', data);
 *     });
 *   }
 * }, [socket]);
 */
export function useSocket({
  autoConnect = true,
  namespace = '/notifications',
  url = DEFAULT_URL,
}: UseSocketOptions = {}): UseSocketReturn {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Initialize socket connection
  useEffect(() => {
    if (!autoConnect) {
      return;
    }

    let client: Socket | null = null;
    try {
      queueMicrotask(() => {
        setIsConnecting(true);
        setError(null);
      });

      const connectionUrl = namespace ? `${url.replace(/\/$/, '')}${namespace}` : url;
      client = io(connectionUrl, {
        auth: {
          token: getAccessToken(),
        },
        withCredentials: true,
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        reconnectionAttempts: 5,
        transports: ['websocket', 'polling'],
      });
      const activeClient = client;
      queueMicrotask(() => setSocket(activeClient));

      activeClient.on('connect', () => {
        console.log('Socket connected:', activeClient.id);
        setIsConnected(true);
        setIsConnecting(false);
      });

      activeClient.on('disconnect', () => {
        console.log('Socket disconnected');
        setIsConnected(false);
        setIsConnecting(false);
      });

      activeClient.on('connect_error', (err) => {
        console.error('Socket connection error:', err);
        setError(err instanceof Error ? err : new Error(String(err)));
        setIsConnecting(false);
      });

      activeClient.on('error', (err) => {
        console.error('Socket error:', err);
        setError(err instanceof Error ? err : new Error(String(err)));
      });
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      queueMicrotask(() => {
        setError(error);
        setIsConnecting(false);
      });
      console.error('Failed to create socket connection:', error);
    }

    // Keep the socket alive while the tab is in the background so presence
    // reflects an open signed-in session rather than only the visible tab.
    const handleVisibility = () => {
      if (!document.hidden && client && !client.connected && autoConnect) {
        client.connect();
      }
    };
    const handlePageHide = () => {
      client?.disconnect();
    };
    const handlePageShow = () => {
      if (autoConnect && client && !client.connected) {
        client.connect();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    window.addEventListener('pagehide', handlePageHide);
    window.addEventListener('pageshow', handlePageShow);

    // Cleanup on unmount
    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener('pagehide', handlePageHide);
      window.removeEventListener('pageshow', handlePageShow);
      if (client?.connected) {
        client.disconnect();
      }
    };
  }, [autoConnect, url, namespace]);

  return {
    socket,
    isConnected,
    isConnecting,
    error,
  };
}

export default useSocket;

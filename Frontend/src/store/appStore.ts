/**
 * Global Application State Store
 * Manages navigation state, UI state, and notifications using Zustand.
 * This replaces prop drilling and manual useState management.
 */

import { create } from 'zustand';
import { apiFetch } from '../lib/apiClient';

export interface Notification {
  id: string;
  type: 'upload' | 'action' | 'error' | 'success' | 'info';
  message: string;
  timestamp: string;
  read: boolean;
  meta?: string;
  link?: string;
}

export interface AppStore {
  // Navigation State
  activeMonth: string;
  activeTeam: string | null;
  activeRegion: 'All' | 'EGY' | 'UAE';

  // Notification State
  notifications: Notification[];
  unreadCount: number;

  // UI State
  sidebarOpen: boolean;

  // Navigation Actions
  setMonth: (month: string) => void;
  setTeam: (team: string | null) => void;
  setRegion: (region: 'All' | 'EGY' | 'UAE') => void;

  // Notification Actions
  addNotification: (notification: Omit<Notification, 'id' | 'read'> & { id?: string; read?: boolean }) => void;
  setNotifications: (notifications: Notification[]) => void;
  removeNotification: (id: string) => void;
  markNotificationAsRead: (id: string) => void;
  markAllRead: () => void;
  clearNotifications: () => void;

  // UI Actions
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;

  // Utility
  reset: () => void;
}

const initialState = {
  activeMonth: 'All',
  activeTeam: null,
  activeRegion: 'All' as const,
  notifications: [],
  unreadCount: 0,
  sidebarOpen: true,
};

const isUuid = (value: string) =>
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);

export const useAppStore = create<AppStore>((set) => ({
  ...initialState,

  // Navigation Actions
  setMonth: (month: string) => set({ activeMonth: month }),
  setTeam: (team: string | null) => set({ activeTeam: team }),
  setRegion: (region: 'All' | 'EGY' | 'UAE') => set({ activeRegion: region }),

  // Notification Actions
  addNotification: (notification) =>
    set((state) => {
      const newNotification: Notification = {
        ...notification,
        id: notification.id || `${Date.now()}-${Math.random()}`,
        read: notification.read !== undefined ? notification.read : false,
      };
      // Avoid duplicate notifications in local store
      const isAlreadyAdded = state.notifications.some((n) => n.id === newNotification.id);
      if (isAlreadyAdded) return state;

      return {
        notifications: [newNotification, ...state.notifications].slice(0, 50), // Keep last 50
        unreadCount: newNotification.read ? state.unreadCount : state.unreadCount + 1,
      };
    }),

  setNotifications: (notifications: Notification[]) => {
    const unreadCount = notifications.filter((n) => !n.read).length;
    set({ notifications, unreadCount });
  },

  removeNotification: (id: string) => {
    if (isUuid(id)) {
      // Invoke API request asynchronously in the background
      apiFetch(`/api/users/notifications/${id}`, { method: 'DELETE' }).catch((err) => {
        console.error('Failed to delete notification in DB:', err);
      });
    }

    set((state) => {
      const notification = state.notifications.find((n) => n.id === id);
      return {
        notifications: state.notifications.filter((n) => n.id !== id),
        unreadCount: notification && !notification.read ? state.unreadCount - 1 : state.unreadCount,
      };
    });
  },

  markNotificationAsRead: (id: string) => {
    if (isUuid(id)) {
      // Invoke API request asynchronously in the background
      apiFetch(`/api/users/notifications/${id}/read`, { method: 'PUT' }).catch((err) => {
        console.error('Failed to mark notification as read in DB:', err);
      });
    }

    set((state) => {
      const notification = state.notifications.find((n) => n.id === id);
      if (!notification || notification.read) return state;

      return {
        notifications: state.notifications.map((n) =>
          n.id === id ? { ...n, read: true } : n
        ),
        unreadCount: state.unreadCount - 1,
      };
    });
  },

  markAllRead: () => {
    // Invoke API request asynchronously in the background
    apiFetch('/api/users/notifications/read-all', { method: 'POST' }).catch((err) => {
      console.error('Failed to mark all notifications as read in DB:', err);
    });

    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    }));
  },

  clearNotifications: () => {
    // Invoke API request asynchronously in the background
    apiFetch('/api/users/notifications/clear', { method: 'DELETE' }).catch((err) => {
      console.error('Failed to clear notifications in DB:', err);
    });

    set({ notifications: [], unreadCount: 0 });
  },

  // UI Actions
  setSidebarOpen: (open: boolean) => set({ sidebarOpen: open }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),

  // Utility
  reset: () => set(initialState),
}));

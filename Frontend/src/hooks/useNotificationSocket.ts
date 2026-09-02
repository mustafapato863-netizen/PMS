import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSocketListener } from './useSocketListener';
import { useAppStore, type Notification } from '../store/appStore';
import { useAuth } from '../context/auth';
import { apiFetch } from '../lib/apiClient';

interface NotificationPayload {
  id?: string;
  type?: 'info' | 'success' | 'warning' | 'error' | 'upload' | 'action' | 'job';
  message?: string;
  timestamp?: string;
  meta?: string;
  data?: {
    created_by_name?: string;
    created_by_role?: string;
    job_id?: string;
    kind?: string;
    status?: string;
  };
}

interface PerformancePayload {
  team_name?: string;
  metric_name?: string;
  new_value?: string | number;
  timestamp?: string;
}

interface DataUploadedPayload {
  team?: string;
  month?: string;
  timestamp?: string;
}

interface ActionRecordedPayload {
  employee_name?: string;
  action_type?: string;
  employee_id?: string;
  created_by_name?: string;
  created_by_role?: string;
  data?: {
    employee_name?: string;
    action_type?: string;
    employee_id?: string;
    created_by_name?: string;
    created_by_role?: string;
  };
  timestamp?: string;
}

/**
 * Hook to set up real-time notifications via Socket.io
 * Call this once in your main app component
 */
export function useNotificationSocket(enabled = true) {
  const queryClient = useQueryClient();
  const { on, off, socket } = useSocketListener({ autoConnect: enabled });
  const addNotification = useAppStore((state) => state.addNotification);
  const setNotifications = useAppStore((state) => state.setNotifications);
  const activeTeam = useAppStore((state) => state.activeTeam);
  const { currentUser, refreshUsers } = useAuth();
  const isGlobalViewer = currentUser?.role === 'Admin' || currentUser?.is_general_manager;
  const scopedTeams = useMemo(() => (
    isGlobalViewer ? [] : (currentUser?.accessible_teams || [])
  ), [isGlobalViewer, currentUser?.accessible_teams]);
  const roomKey = useMemo(() => JSON.stringify({
    role: currentUser?.role || null,
    teams: [...scopedTeams].sort(),
    activeTeam: activeTeam || null,
    global: isGlobalViewer,
  }), [activeTeam, currentUser?.role, isGlobalViewer, scopedTeams]);
  const joinedRoomKeyRef = useRef<string | null>(null);

  const getSubscribedTeams = useCallback(() => {
    if (isGlobalViewer) return [];
    if (scopedTeams.length > 0) return scopedTeams;
    if (activeTeam) return [activeTeam];
    return [];
  }, [activeTeam, isGlobalViewer, scopedTeams]);

  // Load historical notifications on user login/mount
  useEffect(() => {
    if (!enabled) return;
    if (!currentUser) {
      setNotifications([]);
      return;
    }

    const fetchNotifications = async () => {
      try {
        const response = await apiFetch<{ success: boolean; data: Notification[] }>('/api/users/notifications');
        if (response.success && response.data) {
          setNotifications(response.data);
        }
      } catch (err) {
        console.error('Failed to load notifications from DB:', err);
      }
    };

    fetchNotifications();
  }, [enabled, currentUser, setNotifications]);

  // Dynamic Room Joining based on activeTeam selection and admin role
  useEffect(() => {
    if (!socket) return;
    if (!enabled) return;
    if (!currentUser) return;

    const teams = getSubscribedTeams();
    const subscribePayload = teams.length > 0
      ? { team_names: teams, role: currentUser?.role }
      : { team_name: null, role: currentUser?.role };

    const handleConnect = () => {
      if (joinedRoomKeyRef.current === roomKey) {
        return;
      }
      console.log('Socket connected: joining rooms');
      socket.emit('join_room', { room: 'global' });
      if (currentUser?.role === 'Admin') {
        socket.emit('join_room', { room: 'admin' });
      }
      teams.forEach((team) => socket.emit('join_room', { room: `team_${team}` }));
      socket.emit('subscribe_team', isGlobalViewer ? { global: true, role: currentUser?.role } : subscribePayload);
      joinedRoomKeyRef.current = roomKey;
    };

    socket.on('connect', handleConnect);

    if (socket.connected) {
      handleConnect();
    }

    return () => {
      socket.off('connect', handleConnect);
      if (joinedRoomKeyRef.current === roomKey) {
        joinedRoomKeyRef.current = null;
      }
      if (socket.connected) {
        if (currentUser?.role === 'Admin') {
          socket.emit('leave_room', { room: 'admin' });
        }
        teams.forEach((team) => socket.emit('leave_room', { room: `team_${team}` }));
        socket.emit('subscribe_team', { team_name: null });
      }
    };
  }, [enabled, socket, currentUser, getSubscribedTeams, isGlobalViewer, roomKey]);

  useEffect(() => {
    if (!socket || !on || !off) return;
    if (!enabled) return;

    const handleNotification = (data: NotificationPayload) => {
      console.log('Received notification:', data);

      let meta = data.meta;
      if (!meta && data.data?.created_by_name) {
        meta = `${data.data.created_by_name} - ${data.data.created_by_role || ''}`;
      }

      const notificationType: Notification['type'] = data.type === 'warning' || data.type === 'job'
        ? 'info'
        : data.type ?? 'info';
      const notification = {
        id: data.id || Math.random().toString(36),
        type: notificationType,
        message: data.message || 'New notification',
        timestamp: data.timestamp || new Date().toISOString(),
        meta,
      };

      addNotification(notification);

      // Invalidate queries to force refresh if data was uploaded
      if (data.type === 'upload') {
        queryClient.invalidateQueries({ queryKey: ['performance'] });
        queryClient.invalidateQueries({ queryKey: ['team-configs'] });
        queryClient.invalidateQueries({ queryKey: ['teams'] });
      }
      if (data.type === 'job' && data.data?.job_id) {
        queryClient.invalidateQueries({ queryKey: ['processing-jobs', data.data.job_id] });
        if (data.data.kind?.includes('report')) {
          queryClient.invalidateQueries({ queryKey: ['reports', 'list'] });
        }
        if (data.data.kind === 'pms_upload') {
          queryClient.invalidateQueries({ queryKey: ['performance'] });
          queryClient.invalidateQueries({ queryKey: ['teams'] });
        }
      }
    };

    const handlePerformanceUpdated = (data: PerformancePayload) => {
      console.log('Performance data updated:', data);

      addNotification({
        type: 'success',
        message: `${data.team_name || 'Team'} performance updated: ${data.metric_name || ''} = ${data.new_value || ''}`,
        timestamp: data.timestamp || new Date().toISOString(),
      });
      // Invalidate queries to force refresh
      queryClient.invalidateQueries({ queryKey: ['performance'] });
    };

    const handleDataUploaded = (data: DataUploadedPayload) => {
      console.log('Data uploaded:', data);

      addNotification({
        type: 'success',
        message: `New data uploaded for ${data.team || 'team'} — ${data.month || ''}`,
        timestamp: data.timestamp || new Date().toISOString(),
      });
      // Invalidate queries to force refresh
      queryClient.invalidateQueries({ queryKey: ['performance'] });
      queryClient.invalidateQueries({ queryKey: ['team-configs'] });
      queryClient.invalidateQueries({ queryKey: ['teams'] });
    };

    const handleActionRecorded = (data: ActionRecordedPayload) => {
      console.log('Action recorded:', data);
      const payload = data.data || data;

      addNotification({
        type: 'info',
        message: `Action recorded for ${payload.employee_name || 'employee'}: ${payload.action_type || ''}`,
        meta: payload.created_by_name && payload.created_by_role ? `By ${payload.created_by_name} - ${payload.created_by_role}` : undefined,
        timestamp: data.timestamp || new Date().toISOString(),
        link: payload.employee_id ? `/employees/${payload.employee_id}` : undefined,
      });
      // Invalidate employee query to reload actions list
      if (payload.employee_id) {
        queryClient.invalidateQueries({ queryKey: ['employee', payload.employee_id] });
      }
    };

    const handleConnect = () => {
      console.log('Connected to notifications');
    };

    const handleDisconnect = () => {
      console.log('Disconnected from notifications');
    };

    const handleConnectError = (error: unknown) => {
      console.warn('Connection error:', error);
    };

    const handlePresenceUpdated = () => {
      void refreshUsers();
    };

    // Register event listeners
    on('notification', handleNotification);
    on('performance_updated', handlePerformanceUpdated);
    on('data_uploaded', handleDataUploaded);
    on('action_recorded', handleActionRecorded);
    on('connect', handleConnect);
    on('disconnect', handleDisconnect);
    on('connect_error', handleConnectError);
    on('presence_updated', handlePresenceUpdated);

    // Clean up event listeners on unmount or dependency change
    return () => {
      off('notification', handleNotification);
      off('performance_updated', handlePerformanceUpdated);
      off('data_uploaded', handleDataUploaded);
      off('action_recorded', handleActionRecorded);
      off('connect', handleConnect);
      off('disconnect', handleDisconnect);
      off('connect_error', handleConnectError);
      off('presence_updated', handlePresenceUpdated);
    };
  }, [enabled, socket, on, off, addNotification, queryClient, refreshUsers]);
}

export default useNotificationSocket;

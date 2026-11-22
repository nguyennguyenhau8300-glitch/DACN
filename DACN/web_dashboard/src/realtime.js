import { useEffect, useRef, useState } from 'react';

const HEARTBEAT_TIMEOUT_MS = 45000;

export function useRealtime(user, onChange) {
  const callback = useRef(onChange);
  callback.current = onChange;
  const [status, setStatus] = useState('disconnected');

  useEffect(() => {
    if (!user) return;
    let socket, reconnect, refreshTimer, heartbeat;
    let closed = false;
    let rejected = false;

    const offline = () => socket?.close();

    function connect() {
      if (closed || rejected || !navigator.onLine) return;
      if (socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;

      clearTimeout(reconnect);
      setStatus('connecting');
      const base = import.meta.env.VITE_API_BASE_URL || location.origin;
      const url = new URL('/ws/events', base.startsWith('http') ? base : location.origin);
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';

      const connection = new WebSocket(url);
      socket = connection;
      let revision;
      const watch = () => {
        clearTimeout(heartbeat);
        heartbeat = setTimeout(() => {
          if (socket === connection) connection.close();
        }, HEARTBEAT_TIMEOUT_MS);
      };
      watch();
      connection.onopen = () => connection.send(JSON.stringify({ token: sessionStorage.getItem('parking-token') }));
      connection.onmessage = event => {
        if (closed || socket !== connection || connection.readyState !== WebSocket.OPEN) return;
        let message;
        try {
          message = JSON.parse(event.data);
        } catch {
          return;
        }
        if (!message || !['ping', 'invalidate', 'ready'].includes(message.type)) return;
        watch();
        if (message.type === 'ping') connection.send('pong');
        const versioned = typeof message.revision === 'string';
        const changed = versioned && revision !== message.revision;
        if (versioned) revision = message.revision;
        if (message.type === 'ready' || changed || (message.type === 'invalidate' && !versioned)) {
          setStatus('connected');
          if (refreshTimer == null) {
            refreshTimer = setTimeout(() => {
              refreshTimer = undefined;
              callback.current();
            }, 250);
          }
        }
      };
      connection.onclose = event => {
        if (closed || socket !== connection) return;
        clearTimeout(heartbeat);
        setStatus('disconnected');
        rejected = event.code === 1008;
        if (!rejected) reconnect = setTimeout(connect, 3000);
      };
      connection.onerror = () => connection.close();
    }

    window.addEventListener('online', connect);
    window.addEventListener('offline', offline);
    connect();
    return () => {
      closed = true;
      window.removeEventListener('online', connect);
      window.removeEventListener('offline', offline);
      clearTimeout(reconnect);
      clearTimeout(refreshTimer);
      clearTimeout(heartbeat);
      offline();
    };
  }, [user?.id]);

  return status;
}

import { useEffect, useRef, useState } from "react";
import { TOKEN_KEY, WS_URL } from "../services/api";
import type { OnlineUser, SessionEvent } from "../types";

export type ConnectionStatus = "connecting" | "connected" | "disconnected";

/**
 * Connects to /ws/sessions/{id}, authenticates with a first message, tracks
 * presence, auto-reconnects with backoff, and forwards events to `onEvent`.
 */
export function useSessionSocket(
  sessionId: string | undefined,
  onEvent: (event: SessionEvent) => void
) {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [online, setOnline] = useState<OnlineUser[]>([]);

  const onEventRef = useRef(onEvent);
  useEffect(() => {
    onEventRef.current = onEvent;
  });

  useEffect(() => {
    if (!sessionId) return;

    let ws: WebSocket | null = null;
    let closedByUs = false;
    let retries = 0;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let pingTimer: ReturnType<typeof setInterval> | undefined;

    const connect = () => {
      setStatus("connecting");
      const socket = new WebSocket(`${WS_URL}/ws/sessions/${sessionId}`);
      ws = socket;

      socket.onopen = () => {
        socket.send(JSON.stringify({ type: "AUTH", token: localStorage.getItem(TOKEN_KEY) }));
      };

      socket.onmessage = (msg) => {
        let event: SessionEvent;
        try {
          event = JSON.parse(msg.data);
        } catch {
          return;
        }

        switch (event.type) {
          case "CONNECTED":
            retries = 0;
            setStatus("connected");
            setOnline(event.payload.online_users ?? []);
            clearInterval(pingTimer);
            pingTimer = setInterval(() => {
              if (socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ type: "PING" }));
              }
            }, 25000);
            break;
          case "PONG":
            return;
          case "USER_JOINED":
            setOnline((prev) =>
              prev.some((u) => u.user_id === event.payload.user.user_id)
                ? prev
                : [...prev, event.payload.user]
            );
            break;
          case "USER_LEFT":
            setOnline((prev) => prev.filter((u) => u.user_id !== event.payload.user.user_id));
            break;
        }
        onEventRef.current(event);
      };

      socket.onclose = (e) => {
        if (closedByUs) return; // stale socket from a previous effect run
        clearInterval(pingTimer);
        setStatus("disconnected");
        setOnline([]);
        // 4401 = bad token, 4403 = not a member: retrying won't help
        if (e.code === 4401 || e.code === 4403) return;
        retries += 1;
        retryTimer = setTimeout(connect, Math.min(1000 * 2 ** retries, 15000));
      };
    };

    connect();

    return () => {
      closedByUs = true;
      clearTimeout(retryTimer);
      clearInterval(pingTimer);
      ws?.close();
    };
  }, [sessionId]);

  return { status, online };
}

import { useEffect, useRef, useState } from "react";
import { TOKEN_KEY, WS_URL } from "../services/api";
import type { OnlineUser, SessionEvent } from "../types";

export type ConnectionStatus =
  | "connecting"
  | "connected"
  | "disconnected";

/**
 * Connects to /ws/sessions/{id}, authenticates using
 * the first message, tracks presence, reconnects with
 * backoff, and forwards events to onEvent.
 *
 * Phase 15:
 * - Redirect handling when authentication expires.
 * - Stop reconnection when a session is deleted.
 */
export function useSessionSocket(
  sessionId: string | undefined,
  onEvent: (event: SessionEvent) => void
) {
  const [status, setStatus] =
    useState<ConnectionStatus>("connecting");

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

    let retryTimer:
      | ReturnType<typeof setTimeout>
      | undefined;

    let pingTimer:
      | ReturnType<typeof setInterval>
      | undefined;

    const connect = () => {
      setStatus("connecting");

      const socket = new WebSocket(
        `${WS_URL}/ws/sessions/${sessionId}`
      );

      ws = socket;

      // --------------------------------------------------
      // Authenticate after the WebSocket opens
      // --------------------------------------------------

      socket.onopen = () => {
        socket.send(
          JSON.stringify({
            type: "AUTH",
            token: localStorage.getItem(TOKEN_KEY),
          })
        );
      };

      // --------------------------------------------------
      // Handle incoming events
      // --------------------------------------------------

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
                socket.send(
                  JSON.stringify({ type: "PING" })
                );
              }
            }, 25000);

            break;

          case "PONG":
            return;

          case "USER_JOINED":
            setOnline((prev) =>
              prev.some(
                (u) =>
                  u.user_id === event.payload.user.user_id
              )
                ? prev
                : [...prev, event.payload.user]
            );
            break;

          case "USER_LEFT":
            setOnline((prev) =>
              prev.filter(
                (u) =>
                  u.user_id !== event.payload.user.user_id
              )
            );
            break;
        }

        onEventRef.current(event);
      };

      // --------------------------------------------------
      // Phase 15: Handle WebSocket disconnection
      // --------------------------------------------------

      socket.onclose = (e) => {
        // Ignore stale sockets from earlier effect runs.
        if (closedByUs) return;

        clearInterval(pingTimer);

        setStatus("disconnected");
        setOnline([]);

        // 4401: Invalid or expired JWT.
        // Tell the application's authentication handler
        // to return the user to the login page.
        if (e.code === 4401) {
          window.dispatchEvent(
            new Event("auth:expired")
          );
        }

        // 4401: Invalid/expired authentication token.
        // 4403: User does not have session permission.
        // 4404: Session was deleted.
        // Reconnecting cannot resolve these conditions.
        if (
          e.code === 4401 ||
          e.code === 4403 ||
          e.code === 4404
        ) {
          return;
        }

        // Retry temporary connection failures.
        retries += 1;

        retryTimer = setTimeout(
          connect,
          Math.min(
            1000 * 2 ** retries,
            15000
          )
        );
      };
    };

    // --------------------------------------------------
    // Initial connection
    // --------------------------------------------------

    connect();

    // --------------------------------------------------
    // Cleanup when session changes or component unmounts
    // --------------------------------------------------

    return () => {
      closedByUs = true;

      clearTimeout(retryTimer);
      clearInterval(pingTimer);

      ws?.close();
    };
  }, [sessionId]);

  return {
    status,
    online,
  };
}
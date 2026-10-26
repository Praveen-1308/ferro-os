// payloads/drivers/k6/websocket_churn.js
// Measures RFC 6455 full-duplex WebSocket connection churn and message ping/pong.

import ws from 'k6/ws';
import { check } from 'k6';

export const options = {
    vus: 100,
    duration: '300s',
};

const WS_URL = __ENV.WS_URL || 'ws://172.30.0.10:8083/realtime';

export default function () {
    const res = ws.connect(WS_URL, {}, function (socket) {
        socket.on('open', () => {
            socket.send(JSON.stringify({ action: 'subscribe', channel: 'orders' }));
            socket.ping();
        });

        socket.on('message', (data) => {
            socket.close();
        });

        socket.on('close', () => {});
    });

    check(res, { 'connected successfully': (r) => r && r.status === 101 });
}

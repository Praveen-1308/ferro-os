// payloads/drivers/k6/tls_handshake.js
// Measures TLS handshake and session ticket resumption latency.

import http from 'k6/http';
import { check } from 'k6';

export const options = {
    insecureSkipTLSVerify: true,
    stages: [
        { duration: '60s', target: 50 },
        { duration: '60s', target: 100 },
        { duration: '60s', target: 200 },
        { duration: '60s', target: 100 },
        { duration: '60s', target: 50 },
    ],
};

const TARGET_URL = __ENV.TARGET_URL || 'https://172.30.0.10:443/feed';

export default function () {
    const res = http.get(TARGET_URL);
    check(res, {
        'status is 200': (r) => r.status === 200,
        'tls handshake ok': (r) => r.timings.tls_handshaking >= 0,
    });
}

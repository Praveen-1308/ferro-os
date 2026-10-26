// payloads/drivers/k6/fd_leak_trigger.js
// Triggers file descriptor leak code paths on target server.

import http from 'k6/http';
import { check } from 'k6';

export const options = {
    vus: 200,
    duration: '300s',
};

const TARGET_URL = __ENV.TARGET_URL || 'http://172.30.0.10:8883/leak_fd';

export default function () {
    const res = http.get(TARGET_URL);
    check(res, {
        'response received': (r) => r.status > 0,
    });
}

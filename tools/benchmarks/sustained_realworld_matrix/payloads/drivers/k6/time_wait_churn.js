// payloads/drivers/k6/time_wait_churn.js
// Rapid short-lived TCP connection churn testing TIME_WAIT saturation.

import http from 'k6/http';
import { check } from 'k6';

export const options = {
    vus: 500,
    duration: '300s',
};

const TARGET_URL = __ENV.TARGET_URL || 'http://172.30.0.10:8881/churn';

export default function () {
    const params = {
        headers: {
            'Connection': 'close',
        },
    };
    const res = http.get(TARGET_URL, params);
    check(res, {
        'status ok or expected churn': (r) => r.status === 200 || r.status === 0,
    });
}

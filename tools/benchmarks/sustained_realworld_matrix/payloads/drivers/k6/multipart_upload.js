// payloads/drivers/k6/multipart_upload.js
// Streams chunked multipart uploads with real binary images to target server.

import http from 'k6/http';
import { check } from 'k6';

export const options = {
    vus: 50,
    duration: '300s',
};

const TARGET_URL = __ENV.TARGET_URL || 'http://172.30.0.10:9000/upload';

// 1MB JPEG binary buffer
const binFile = open('../../assets/sample_1mb.jpg', 'b');

export default function () {
    const data = {
        file: http.file(binFile, 'sample_1mb.jpg', 'image/jpeg'),
        category: 'benchmark_assets',
    };

    const res = http.post(TARGET_URL, data);
    check(res, {
        'upload status 200 or 201': (r) => r.status === 200 || r.status === 201,
    });
}

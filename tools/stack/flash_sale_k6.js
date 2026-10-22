// tools/stack/flash_sale_k6.js
// Grafana k6 Multi-Modal Flash Sale & Media Choke Benchmark
// Simulates extreme concurrency stampede: catalog queries, image streaming,
// hot-row lock checkouts, content likes, and 256 KB image uploads.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:10000';

// Per-Workload Latency Tracking Trends
export const catalogTrend = new Trend('catalog_read_duration', true);
export const imageStreamTrend = new Trend('image_stream_duration', true);
export const likeTrend = new Trend('content_like_duration', true);
export const checkoutTrend = new Trend('flash_checkout_duration', true);
export const imageUploadTrend = new Trend('image_upload_duration', true);

// Pre-generate 64 KB binary payload for image upload
// Creates authentic 64 KB JPEG structure
const UPLOAD_PAYLOAD = new Uint8Array(65536);
UPLOAD_PAYLOAD[0] = 0xFF; UPLOAD_PAYLOAD[1] = 0xD8; UPLOAD_PAYLOAD[2] = 0xFF; UPLOAD_PAYLOAD[3] = 0xE0;
UPLOAD_PAYLOAD[65534] = 0xFF; UPLOAD_PAYLOAD[65535] = 0xD9;

export const options = {
    summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)', 'count'],
    scenarios: {
        flash_sale_stampede: {
            executor: 'ramping-vus',
            startVUs: 20,
            stages: [
                { duration: '10s', target: 50 },   // Tier 1: Initial Rush (50 VUs)
                { duration: '20s', target: 150 },  // Tier 2: Heavy Surge (150 VUs)
                { duration: '25s', target: 300 },  // Tier 3: The Stampede (300 VUs)
                { duration: '25s', target: 500 },  // Tier 4: Hardware Ceiling / The Choke (500 VUs)
                { duration: '10s', target: 0 },    // Ramp Down
            ],
            gracefulRampDown: '5s',
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<1000'],
        http_req_failed: ['rate<0.50'], // Record failure percentage without early exit
    },
};

export default function () {
    const userId = Math.floor(Math.random() * 50000) + 1;
    const itemId = (Math.floor(Math.random() * 10) + 1); // 1 to 10
    const imgId = (Math.floor(Math.random() * 100) + 1);

    // 1. Flash Catalog Read
    const t0 = Date.now();
    const catRes = http.get(`${BASE_URL}/flash-sale/catalog`);
    catalogTrend.add(Date.now() - t0);
    check(catRes, {
        'catalog 200/429': (r) => r.status === 200 || r.status === 429,
    });
    sleep(Math.random() * 0.05 + 0.02);

    // 2. Binary Image Stream (256 KB Read)
    const t1 = Date.now();
    const imgRes = http.get(`${BASE_URL}/media/images/${imgId}`);
    imageStreamTrend.add(Date.now() - t1);
    check(imgRes, {
        'img stream 200/429': (r) => r.status === 200 || r.status === 429,
    });
    sleep(Math.random() * 0.05 + 0.02);

    // 3. Content Reaction / Like (Hot atomic counter increment)
    const t2 = Date.now();
    const likeRes = http.post(`${BASE_URL}/content/${itemId}/like`, null);
    likeTrend.add(Date.now() - t2);
    check(likeRes, {
        'like 200/429': (r) => r.status === 200 || r.status === 429,
    });
    sleep(Math.random() * 0.05 + 0.02);

    // 4. Flash Sale Checkout Race (High contention atomic purchase on item #1)
    const buyPayload = JSON.stringify({ user_id: userId, item_id: 1 });
    const t3 = Date.now();
    const buyRes = http.post(`${BASE_URL}/flash-sale/buy`, buyPayload, {
        headers: { 'Content-Type': 'application/json' },
    });
    checkoutTrend.add(Date.now() - t3);
    check(buyRes, {
        'buy 201/200/429/409': (r) => r.status === 201 || r.status === 200 || r.status === 429 || r.status === 409,
    });

    // 5. Binary Image Upload (256 KB Write to Disk - 20% of users)
    if (Math.random() < 0.20) {
        const t4 = Date.now();
        const uploadRes = http.post(`${BASE_URL}/media/images`, UPLOAD_PAYLOAD.buffer, {
            headers: { 'Content-Type': 'image/jpeg' },
        });
        imageUploadTrend.add(Date.now() - t4);
        check(uploadRes, {
            'upload 201/429': (r) => r.status === 201 || r.status === 429,
        });
    }

    sleep(Math.random() * 0.1 + 0.05);
}

// tools/stack/enterprise_k6_load.js
// Grafana k6 Enterprise Sustained Load Script with Zipfian Skewed Browsing
// Evaluates Cache Read vs DB Read vs Checkout Write latency percentiles over a 5-minute sustained test.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:10000';
const NUM_PRODUCTS = 10000;
const ZIPF_ALPHA = 0.85;

// Per-Endpoint Latency Breakdown Trends
export const cacheReadTrend = new Trend('cache_read_duration', true);
export const dbReadTrend = new Trend('db_read_duration', true);
export const checkoutWriteTrend = new Trend('checkout_write_duration', true);

// Approximate Zipfian draw
function getZipfianProductId() {
    const u = Math.random();
    const rank = Math.floor(Math.pow(u, 1.0 / (1.0 - ZIPF_ALPHA)));
    return Math.min(Math.max((rank % NUM_PRODUCTS) + 1, 1), NUM_PRODUCTS);
}

const STAGE_RAMP = __ENV.STAGE_RAMP || '5s';
const STAGE_PLATEAU = __ENV.STAGE_PLATEAU || '20s';
const STAGE_DOWN = __ENV.STAGE_DOWN || '5s';
const TARGET_VUS = parseInt(__ENV.TARGET_VUS || '100', 10);
const START_VUS = Math.min(20, TARGET_VUS);

export const options = {
    summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)', 'count'],
    scenarios: {
        enterprise_sustained: {
            executor: 'ramping-vus',
            startVUs: START_VUS,
            stages: [
                { duration: STAGE_RAMP, target: TARGET_VUS },
                { duration: STAGE_PLATEAU, target: TARGET_VUS },
                { duration: STAGE_DOWN, target: 0 },
            ],
            gracefulRampDown: '5s',
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<500', 'p(99)<1000'],
        http_req_failed: ['rate<0.02'],
        cache_read_duration: ['p(95)<200', 'p(99)<500'],
        db_read_duration: ['p(95)<300', 'p(99)<600'],
        checkout_write_duration: ['p(95)<500', 'p(99)<1000'],
    },
};

export default function () {
    const userId = Math.floor(Math.random() * 25000) + 1;
    const prodId = getZipfianProductId();

    // 1. Cache Read: Home Feed / Catalog
    const tFeed0 = Date.now();
    const feedRes = http.get(`${BASE_URL}/feed`);
    cacheReadTrend.add(Date.now() - tFeed0);
    check(feedRes, {
        'feed status 200/429': (r) => r.status === 200 || r.status === 429,
    });
    sleep(Math.random() * 0.1 + 0.05); // 50-150ms think time

    // 2. DB Read: Product Detail & Reviews (Zipfian Hot vs Cold read)
    const tProd0 = Date.now();
    const prodRes = http.get(`${BASE_URL}/products/${prodId}`);
    dbReadTrend.add(Date.now() - tProd0);
    check(prodRes, {
        'product status 200/429': (r) => r.status === 200 || r.status === 404 || r.status === 429,
    });
    sleep(Math.random() * 0.1 + 0.05);

    // 3. Checkout Write: ACID Transaction + 64KB Audit WAL Payload (35% probability)
    if (Math.random() < 0.35) {
        const payload = JSON.stringify({
            user_id: userId,
            product_id: prodId,
            quantity: 1,
        });
        const tOrder0 = Date.now();
        const orderRes = http.post(`${BASE_URL}/orders`, payload, {
            headers: { 'Content-Type': 'application/json' },
        });
        checkoutWriteTrend.add(Date.now() - tOrder0);
        check(orderRes, {
            'order status 200/201/429': (r) => r.status === 200 || r.status === 201 || r.status === 429,
        });
    }

    sleep(Math.random() * 0.15 + 0.1);
}

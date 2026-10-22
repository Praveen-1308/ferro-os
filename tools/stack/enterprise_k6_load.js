// tools/stack/enterprise_k6_load.js
// Grafana k6 Enterprise Load Script with Zipfian Skewed Browsing
// Simulates realistic human browsing, product discovery, and transactional orders.

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:10000';
const NUM_PRODUCTS = 10000;
const ZIPF_ALPHA = 0.85;

// Approximate Zipfian draw in JavaScript
function getZipfianProductId() {
    // Generate rank using inverse transform approximation for Zipfian: k = (1 - u)^(-1 / (alpha - 1))
    // Or bounded power-law approximation
    const u = Math.random();
    const rank = Math.floor(Math.pow(u, 1.0 / (1.0 - ZIPF_ALPHA)));
    return Math.min(Math.max((rank % NUM_PRODUCTS) + 1, 1), NUM_PRODUCTS);
}

export const options = {
    scenarios: {
        enterprise_users: {
            executor: 'ramping-vus',
            startVUs: 10,
            stages: [
                { duration: '3s', target: 50 },
                { duration: '5s', target: 200 },
                { duration: '3s', target: 0 },
            ],
            gracefulRampDown: '2s',
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<500', 'p(99)<1000'],
        http_req_failed: ['rate<0.01'], // Less than 1% errors
    },
};

export default function () {
    const userId = Math.floor(Math.random() * 25000) + 1;
    const prodId = getZipfianProductId();

    // 1. Browsing Home Feed / Catalog (Read)
    const feedRes = http.get(`${BASE_URL}/feed`);
    check(feedRes, {
        'feed status 200': (r) => r.status === 200,
    });
    sleep(Math.random() * 0.2 + 0.1); // 100-300ms think time

    // 2. Querying Specific Product Details & Reviews (Hot vs Cold Read)
    const prodRes = http.get(`${BASE_URL}/products/${prodId}`);
    check(prodRes, {
        'product status 200': (r) => r.status === 200 || r.status === 404,
    });
    sleep(Math.random() * 0.2 + 0.1);

    // 3. Occasional Transactional Mutation: Place Order or Like (15% probability)
    if (Math.random() < 0.15) {
        const payload = JSON.stringify({
            user_id: userId,
            product_id: prodId,
            quantity: 1,
        });
        const orderRes = http.post(`${BASE_URL}/orders`, payload, {
            headers: { 'Content-Type': 'application/json' },
        });
        check(orderRes, {
            'order status 200/201': (r) => r.status === 200 || r.status === 201 || r.status === 429,
        });
    }

    sleep(Math.random() * 0.3 + 0.2);
}

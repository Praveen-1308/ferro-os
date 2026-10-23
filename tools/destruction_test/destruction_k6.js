// tools/destruction_test/destruction_k6.js
// Continuous Ramp-to-Destruction Benchmark Script
// Concurrency progression: 100 -> 300 -> 600 -> 1200 -> 2500 -> 3500 VUs

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:10000';

export const errorRate = new Rate('custom_error_rate');
export const readLatency = new Trend('read_duration', true);
export const writeLatency = new Trend('write_duration', true);
export const totalOrders = new Counter('total_orders_placed');

export const options = {
    summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)', 'count'],
    scenarios: {
        ramp_to_destruction: {
            executor: 'ramping-vus',
            startVUs: 50,
            stages: [
                { duration: '10s', target: 100 },   // Stage 1: 100 VUs baseline
                { duration: '15s', target: 300 },   // Stage 2: 300 VUs
                { duration: '15s', target: 600 },   // Stage 3: 600 VUs
                { duration: '20s', target: 1200 },  // Stage 4: 1,200 VUs (Severe Choke)
                { duration: '20s', target: 2500 },  // Stage 5: 2,500 VUs (Devastation threshold)
                { duration: '20s', target: 3500 },  // Stage 6: 3,500 VUs (Lethal Overdrive)
                { duration: '10s', target: 0 },     // Ramp-down to test resurrection
            ],
            gracefulRampDown: '5s',
        },
    },
    thresholds: {
        // No hard-abort thresholds so test runs through the full destruction ramp
    },
};

export default function () {
    const prodId = Math.floor(Math.random() * 1000) + 1;
    const isWrite = Math.random() < 0.35; // 35% writes (heavy WAL and heap churn), 65% reads

    if (isWrite) {
        const payload = JSON.stringify({ prod_id: prodId, qty: 1 });
        const params = {
            headers: { 'Content-Type': 'application/json' },
            timeout: '4s',
        };
        const res = http.post(`${BASE_URL}/api/write?id=${prodId}`, payload, params);
        const success = res.status === 200;
        errorRate.add(!success);
        writeLatency.add(res.timings.duration);
        if (success) {
            totalOrders.add(1);
        }
    } else {
        const params = { timeout: '3s' };
        const res = http.get(`${BASE_URL}/api/read?id=${prodId}`, params);
        const success = res.status === 200;
        errorRate.add(!success);
        readLatency.add(res.timings.duration);
    }
}

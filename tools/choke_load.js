/**
 * tools/choke_load.js - Grafana k6 Choke Load Scenario
 * Progressively drives concurrency until target server chokes or fails.
 */
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:9200';
const VUS = Number(__ENV.VUS || 100);
const DURATION = __ENV.DURATION || '10s';

export const options = {
  scenarios: {
    stress: {
      executor: 'constant-vus',
      vus: VUS,
      duration: DURATION,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.01'],
  },
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
};

export default function () {
  // Realistic traffic mix: 40% feed, 30% posts, 15% like, 10% users, 5% metrics
  const rand = Math.random();
  const id = Math.floor(Math.random() * 5000) + 1;

  if (rand < 0.40) {
    const res = http.get(`${BASE_URL}/feed`);
    check(res, { 'feed status 200': (r) => r.status === 200 });
  } else if (rand < 0.70) {
    const res = http.get(`${BASE_URL}/posts/${id}`);
    check(res, { 'post status 200': (r) => r.status === 200 });
  } else if (rand < 0.85) {
    const res = http.post(`${BASE_URL}/posts/${id}/like`, '{}', { headers: { 'Content-Type': 'application/json' } });
    check(res, { 'like status 200': (r) => r.status === 200 });
  } else if (rand < 0.95) {
    const res = http.get(`${BASE_URL}/users/${id}`);
    check(res, { 'user status 200': (r) => r.status === 200 });
  } else {
    const res = http.get(`${BASE_URL}/metrics`);
    check(res, { 'metrics status 200': (r) => r.status === 200 });
  }

  // Realistic micro-think time (5ms to 25ms under choke stress)
  sleep(0.005 + Math.random() * 0.020);
}

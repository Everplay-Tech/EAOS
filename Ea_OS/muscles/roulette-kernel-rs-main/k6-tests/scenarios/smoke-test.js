/**
 * Smoke Test
 *
 * Verifies that the system works under minimal load.
 * This test should run quickly and catch basic issues.
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, smokeTestOptions } from '../utils/config.js';

export const options = smokeTestOptions;

export default function () {
  // Test health endpoint
  const healthResponse = http.get(`${BASE_URL}/health`);
  check(healthResponse, {
    'health check status is 200': (r) => r.status === 200,
    'health check response time < 200ms': (r) => r.timings.duration < 200,
  });

  sleep(1);

  // Test API endpoint (example)
  const apiResponse = http.get(`${BASE_URL}/api/v1/status`);
  check(apiResponse, {
    'api status is 200': (r) => r.status === 200,
    'api response has correct content-type': (r) =>
      r.headers['Content-Type'] && r.headers['Content-Type'].includes('application/json'),
  });

  sleep(1);
}

export function handleSummary(data) {
  return {
    'stdout': JSON.stringify(data, null, 2),
    'k6-tests/results/smoke-test-summary.json': JSON.stringify(data),
  };
}

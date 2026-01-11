/**
 * Spike Test
 *
 * Tests system behavior under sudden, dramatic increases in load.
 * Validates that the system can handle traffic spikes and recover gracefully.
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, spikeTestOptions } from '../utils/config.js';

export const options = spikeTestOptions;

export default function () {
  const response = http.get(`${BASE_URL}/api/v1/status`);

  check(response, {
    'spike test - status is 200': (r) => r.status === 200,
    'spike test - response time acceptable': (r) => r.timings.duration < 2000,
  });

  // Minimal sleep to maximize concurrent requests during spike
  sleep(0.1);
}

export function handleSummary(data) {
  return {
    'stdout': JSON.stringify(data, null, 2),
    'k6-tests/results/spike-test-summary.json': JSON.stringify(data),
  };
}

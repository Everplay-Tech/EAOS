/**
 * Stress Test
 *
 * Pushes the system beyond normal operating conditions
 * to identify breaking points and recovery behavior.
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Gauge } from 'k6/metrics';
import { BASE_URL, stressTestOptions } from '../utils/config.js';

export const options = stressTestOptions;

// Custom metrics
const failureCounter = new Counter('failure_count');
const activeUsers = new Gauge('active_users');

export default function () {
  activeUsers.add(1);

  const payload = JSON.stringify({
    operation: 'stress_test',
    timestamp: Date.now(),
    data: generateTestData(),
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  // Simulate various API calls
  const operations = [
    () => http.get(`${BASE_URL}/api/v1/heavy-computation`, params),
    () => http.post(`${BASE_URL}/api/v1/data`, payload, params),
    () => http.get(`${BASE_URL}/api/v1/large-dataset`, params),
  ];

  const operation = operations[Math.floor(Math.random() * operations.length)];
  const response = operation();

  const result = check(response, {
    'status is 200 or 201': (r) => r.status === 200 || r.status === 201,
    'response time < 1000ms': (r) => r.timings.duration < 1000,
  });

  if (!result) {
    failureCounter.add(1);
    console.error(`Stress test failure: ${response.status} - ${response.body}`);
  }

  activeUsers.add(-1);
  sleep(Math.random() * 2); // Sleep 0-2 seconds
}

function generateTestData() {
  const dataSize = Math.floor(Math.random() * 1000);
  const data = [];
  for (let i = 0; i < dataSize; i++) {
    data.push({
      id: i,
      value: Math.random(),
      text: `test_data_${i}`,
    });
  }
  return data;
}

export function handleSummary(data) {
  const thresholdsOk = data.root_group.checks.reduce((acc, check) => {
    return acc && check.passes > 0;
  }, true);

  console.log(`Stress test ${thresholdsOk ? 'PASSED' : 'FAILED'}`);

  return {
    'stdout': JSON.stringify(data, null, 2),
    'k6-tests/results/stress-test-summary.json': JSON.stringify(data),
  };
}

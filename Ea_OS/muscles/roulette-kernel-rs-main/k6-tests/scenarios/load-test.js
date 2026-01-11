/**
 * Load Test
 *
 * Tests the system under expected production load.
 * Gradually increases load to identify performance degradation points.
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import { BASE_URL, loadTestOptions } from '../utils/config.js';

export const options = loadTestOptions;

// Custom metrics
const errorRate = new Rate('errors');
const customTrend = new Trend('custom_waiting_time');

export default function () {
  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
  };

  // Test various endpoints
  const endpoints = [
    '/health',
    '/api/v1/status',
    '/api/v1/metrics',
  ];

  const endpoint = endpoints[Math.floor(Math.random() * endpoints.length)];
  const response = http.get(`${BASE_URL}${endpoint}`, params);

  // Record custom metrics
  errorRate.add(response.status !== 200);
  customTrend.add(response.timings.waiting);

  // Validate response
  const result = check(response, {
    'status is 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500,
    'response size > 0': (r) => r.body.length > 0,
  });

  if (!result) {
    console.error(`Request to ${endpoint} failed: ${response.status}`);
  }

  sleep(Math.random() * 3 + 1); // Sleep 1-4 seconds
}

export function handleSummary(data) {
  return {
    'stdout': JSON.stringify(data, null, 2),
    'k6-tests/results/load-test-summary.json': JSON.stringify(data),
    'k6-tests/results/load-test-summary.html': htmlReport(data),
  };
}

function htmlReport(data) {
  const passed = data.metrics.checks.values.passes;
  const failed = data.metrics.checks.values.fails;
  const total = passed + failed;
  const passRate = ((passed / total) * 100).toFixed(2);

  return `
<!DOCTYPE html>
<html>
<head>
  <title>K6 Load Test Report</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; }
    .header { background-color: #333; color: white; padding: 20px; }
    .metric { margin: 10px 0; padding: 10px; border-left: 4px solid #007acc; }
    .success { border-left-color: #28a745; }
    .warning { border-left-color: #ffc107; }
    .error { border-left-color: #dc3545; }
  </style>
</head>
<body>
  <div class="header">
    <h1>K6 Load Test Report</h1>
    <p>Generated: ${new Date().toISOString()}</p>
  </div>
  <div class="metric ${passRate >= 95 ? 'success' : passRate >= 80 ? 'warning' : 'error'}">
    <h2>Check Pass Rate: ${passRate}%</h2>
    <p>Passed: ${passed} | Failed: ${failed} | Total: ${total}</p>
  </div>
  <div class="metric">
    <h2>Requests: ${data.metrics.http_reqs.values.count}</h2>
    <p>Rate: ${data.metrics.http_reqs.values.rate.toFixed(2)} req/s</p>
  </div>
  <div class="metric">
    <h2>Response Time</h2>
    <p>Average: ${data.metrics.http_req_duration.values.avg.toFixed(2)}ms</p>
    <p>p95: ${data.metrics.http_req_duration.values['p(95)'].toFixed(2)}ms</p>
    <p>p99: ${data.metrics.http_req_duration.values['p(99)'].toFixed(2)}ms</p>
  </div>
</body>
</html>
  `;
}

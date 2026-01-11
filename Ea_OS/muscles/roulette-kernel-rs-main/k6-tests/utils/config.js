/**
 * K6 Load Testing Configuration
 *
 * Common configuration and utilities for k6 load tests
 */

export const BASE_URL = __ENV.BASE_URL || 'http://localhost:3000';
export const TEST_DURATION = __ENV.TEST_DURATION || '30s';
export const VUS = parseInt(__ENV.VUS) || 10;

/**
 * Standard thresholds for performance testing
 */
export const defaultThresholds = {
  // 95% of requests should be below 500ms
  http_req_duration: ['p(95)<500'],
  // 99% of requests should be below 1s
  'http_req_duration{expected_response:true}': ['p(99)<1000'],
  // Error rate should be below 1%
  http_req_failed: ['rate<0.01'],
  // Request rate should be above 50 rps
  http_reqs: ['rate>50'],
};

/**
 * Options for smoke testing
 * Quick test with minimal load to verify functionality
 */
export const smokeTestOptions = {
  vus: 1,
  duration: '1m',
  thresholds: {
    http_req_duration: ['p(99)<1000'],
    http_req_failed: ['rate<0.01'],
  },
};

/**
 * Options for load testing
 * Simulates expected production load
 */
export const loadTestOptions = {
  stages: [
    { duration: '2m', target: 10 },  // Ramp up to 10 users
    { duration: '5m', target: 10 },  // Stay at 10 users
    { duration: '2m', target: 20 },  // Ramp up to 20 users
    { duration: '5m', target: 20 },  // Stay at 20 users
    { duration: '2m', target: 0 },   // Ramp down to 0 users
  ],
  thresholds: defaultThresholds,
};

/**
 * Options for stress testing
 * Pushes the system beyond normal load
 */
export const stressTestOptions = {
  stages: [
    { duration: '2m', target: 10 },   // Ramp up to 10 users
    { duration: '5m', target: 10 },   // Stay at 10 users
    { duration: '2m', target: 50 },   // Spike to 50 users
    { duration: '5m', target: 50 },   // Stay at 50 users
    { duration: '2m', target: 100 },  // Spike to 100 users
    { duration: '5m', target: 100 },  // Stay at 100 users
    { duration: '5m', target: 0 },    // Ramp down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<1000'],
    http_req_failed: ['rate<0.05'],
  },
};

/**
 * Options for spike testing
 * Tests system behavior under sudden load increases
 */
export const spikeTestOptions = {
  stages: [
    { duration: '1m', target: 10 },   // Ramp up to 10 users
    { duration: '30s', target: 200 }, // Sudden spike to 200 users
    { duration: '3m', target: 200 },  // Stay at 200 users
    { duration: '1m', target: 10 },   // Scale down to 10 users
    { duration: '1m', target: 0 },    // Ramp down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],
    http_req_failed: ['rate<0.1'],
  },
};

/**
 * Helper function to check response status
 */
export function checkStatus(response, expectedStatus = 200) {
  return response.status === expectedStatus;
}

/**
 * Helper function to generate random data
 */
export function randomString(length = 10) {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

/**
 * Helper function to generate random number
 */
export function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

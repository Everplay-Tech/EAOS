# K6 Load Testing for Roulette Kernel

This directory contains k6 load testing scripts for the Roulette Kernel project.

## Overview

K6 is a modern load testing tool that makes performance testing easy and productive for engineering teams. It's designed for testing the performance of APIs, microservices, and websites.

## Directory Structure

```
k6-tests/
├── README.md                 # This file
├── k6.config.js             # Global k6 configuration
├── api-test.js              # API integration tests
├── scenarios/               # Different load testing scenarios
│   ├── smoke-test.js        # Quick validation with minimal load
│   ├── load-test.js         # Normal expected load
│   ├── stress-test.js       # Beyond normal load
│   └── spike-test.js        # Sudden traffic spikes
├── utils/                   # Shared utilities
│   └── config.js            # Common configuration and helpers
└── results/                 # Test results (auto-generated)
    ├── .gitkeep
    └── *.json               # Result files
```

## Installation

K6 is already installed as a dev dependency. If you need to install it separately:

```bash
npm install --save-dev k6
```

For system-wide installation:

```bash
# macOS (Homebrew)
brew install k6

# Linux (Debian/Ubuntu)
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6

# Windows (Chocolatey)
choco install k6
```

## Running Tests

### Quick Start

```bash
# Run smoke test (quick validation)
npm run k6:smoke

# Run load test (normal load)
npm run k6:load

# Run stress test (heavy load)
npm run k6:stress

# Run spike test (sudden traffic spike)
npm run k6:spike

# Run API integration test
npm run k6:api

# Run all main tests
npm run k6:all
```

### Using k6 Directly

```bash
# Run a specific test
k6 run k6-tests/scenarios/smoke-test.js

# Run with custom VUs and duration
k6 run --vus 10 --duration 30s k6-tests/api-test.js

# Run with environment variables
BASE_URL=http://localhost:8080 k6 run k6-tests/api-test.js

# Run with custom configuration
k6 run --config k6-tests/k6.config.js k6-tests/scenarios/load-test.js
```

### Environment Variables

You can customize tests using environment variables:

- `BASE_URL`: Target URL (default: `http://localhost:3000`)
- `TEST_DURATION`: Test duration (default: `30s`)
- `VUS`: Number of virtual users (default: `10`)

Example:
```bash
BASE_URL=http://api.example.com VUS=50 npm run k6:load
```

## Test Scenarios

### 1. Smoke Test (`smoke-test.js`)
- **Purpose**: Quick validation that the system works under minimal load
- **Duration**: 1 minute
- **VUs**: 1
- **Use Case**: Pre-deployment check, CI/CD integration

### 2. Load Test (`load-test.js`)
- **Purpose**: Test system under expected production load
- **Duration**: 16 minutes (with ramp-up/down)
- **VUs**: 10-20 (ramping)
- **Use Case**: Performance baseline, capacity planning

### 3. Stress Test (`stress-test.js`)
- **Purpose**: Push system beyond normal load to find breaking points
- **Duration**: 21 minutes
- **VUs**: 10-100 (ramping)
- **Use Case**: Reliability testing, finding limits

### 4. Spike Test (`spike-test.js`)
- **Purpose**: Test system behavior under sudden traffic spikes
- **Duration**: 7 minutes
- **VUs**: 10-200 (with spike)
- **Use Case**: Flash sale scenarios, DDoS resilience

### 5. API Test (`api-test.js`)
- **Purpose**: Comprehensive API endpoint testing
- **Duration**: 30 seconds
- **VUs**: 5
- **Use Case**: API integration validation

## Understanding Results

K6 outputs metrics including:

- **http_req_duration**: Request duration (avg, min, max, percentiles)
- **http_req_failed**: Rate of failed requests
- **http_reqs**: Total requests and request rate
- **iterations**: Number of test iterations completed
- **vus**: Number of active virtual users
- **vus_max**: Maximum virtual users

### Thresholds

Tests define thresholds for pass/fail criteria:

```javascript
thresholds: {
  http_req_duration: ['p(95)<500'],     // 95% of requests < 500ms
  http_req_failed: ['rate<0.01'],       // Error rate < 1%
  http_reqs: ['rate>50'],               // Request rate > 50/s
}
```

### Result Files

Test results are saved to `k6-tests/results/`:
- JSON files: Machine-readable metrics
- HTML files: Human-readable reports (where implemented)

## Customizing Tests

### Creating a New Test

1. Create a new file in `k6-tests/scenarios/`
2. Import the config utilities:
   ```javascript
   import { BASE_URL, defaultThresholds } from '../utils/config.js';
   ```
3. Define your test options and logic
4. Add an npm script in `package.json`

### Example Custom Test

```javascript
import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL } from '../utils/config.js';

export const options = {
  vus: 5,
  duration: '1m',
  thresholds: {
    http_req_duration: ['p(95)<300'],
  },
};

export default function () {
  const res = http.get(`${BASE_URL}/api/custom-endpoint`);
  check(res, {
    'status is 200': (r) => r.status === 200,
  });
}
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Load Tests
on: [push, pull_request]

jobs:
  k6-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup Node
        uses: actions/setup-node@v2
        with:
          node-version: '18'
      - name: Install dependencies
        run: npm ci
      - name: Run smoke tests
        run: npm run k6:smoke
```

## Best Practices

1. **Start Small**: Begin with smoke tests, then gradually increase load
2. **Set Realistic Thresholds**: Base them on actual requirements
3. **Monitor System Resources**: Watch CPU, memory, disk I/O during tests
4. **Use Stages**: Ramp up/down gradually to avoid thundering herd
5. **Test Regularly**: Include in CI/CD for continuous performance monitoring
6. **Analyze Trends**: Compare results over time, not just pass/fail
7. **Test Production-Like**: Use similar data, network conditions, infrastructure

## Troubleshooting

### Test Fails Immediately
- Check that the target service is running
- Verify `BASE_URL` is correct
- Ensure network connectivity

### High Error Rates
- Server may be overloaded
- Check server logs for errors
- Reduce VUs or request rate

### Inconsistent Results
- Ensure consistent test environment
- Check for background processes affecting performance
- Use longer test durations for more reliable metrics

## Resources

- [K6 Documentation](https://k6.io/docs/)
- [K6 Examples](https://k6.io/docs/examples/)
- [K6 Community](https://community.k6.io/)
- [Load Testing Best Practices](https://k6.io/docs/testing-guides/automated-performance-testing/)

## Notes for Roulette Kernel

This k6 setup is designed to be extended as the Roulette Kernel API develops:

- **Braid Operations**: Add tests for braid multiplication, reduction, etc.
- **T9 Syscalls**: Test T9-encoded system call performance
- **VM Operations**: Benchmark memory allocation and management
- **Network Stack**: Test TCP/IP operations when implemented
- **Gödel Programs**: Test program execution performance

Update the test scripts in `scenarios/` and `api-test.js` as new endpoints become available.

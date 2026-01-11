import { config } from '../src/env';

describe('Environment Config', () => {
  it('should load required env vars', () => {
    expect(config.GITHUB_TOKEN).toBeDefined();
    expect(config.XAI_API_KEY).toBeDefined();
  });
});
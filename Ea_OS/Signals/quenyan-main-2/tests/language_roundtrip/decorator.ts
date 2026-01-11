@sealed
export class ExampleService {
  constructor(private readonly gateway: Gateway) {}

  @trace('lookup')
  public async fetch(id: string): Promise<Result<Record<string, unknown>>> {
    const value = await this.gateway.lookup(id);
    return value ?? { state: 'missing' };
  }
}

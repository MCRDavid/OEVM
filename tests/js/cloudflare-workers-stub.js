// Stands in for the Workers runtime's "cloudflare:workers" module in tests/js/ocpi.test.js.
// The real DurableObject base class keeps ctx and env the same way.
export class DurableObject {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
  }
}

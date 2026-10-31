import { DurableObject } from "cloudflare:workers";
import { appEnvironment, type Env } from "./application";

export class VisaoBackend extends DurableObject<Env> {
  private starting?: Promise<void>;
  private inflight = 0;

  private async ready(): Promise<void> {
    const container = this.ctx.container!;
    if (!container.running) {
      container.start({ image: container.images.base, instance: "lite", enableInternet: true,
        env: appEnvironment(this.env) });
    }
    await container.setInactivityTimeout(10 * 60 * 1000);
    const port = container.getTcpPort(8000);
    for (let attempt = 0; attempt < 120; attempt++) {
      try {
        const response = await port.fetch("http://container/ready", { signal: AbortSignal.timeout(1500) });
        await response.body?.cancel();
        if (response.ok) return;
      } catch { /* The image may still be starting and applying migrations. */ }
      await scheduler.wait(500);
    }
    throw new Error("VISÃO did not become ready");
  }

  async fetch(request: Request): Promise<Response> {
    this.inflight++;
    try {
      this.starting ??= this.ready().finally(() => { this.starting = undefined; });
      await this.starting;
      const url = new URL(request.url);
      url.protocol = "http:";
      url.host = "container";
      const forwarded = new Request(url, request);
      forwarded.headers.delete("host");
      return await this.ctx.container!.getTcpPort(8000).fetch(forwarded);
    } finally {
      this.inflight--;
      if (!this.inflight && this.ctx.container?.running) {
        await this.ctx.container.setInactivityTimeout(2 * 60 * 1000);
      }
    }
  }
}

export { default } from "./application";

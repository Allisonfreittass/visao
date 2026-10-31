import { describe, expect, it, vi } from "vitest";
import { ensureRunning } from "../src/lifecycle";
import type { Env } from "../src/application";

const env = {
  VISION_DATABASE_URL: "postgresql+psycopg://test@example.com/postgres",
  VISION_DATABASE_SCHEMA: "visao", VISION_SECRET_KEY: "test-key",
  VISION_CLOUD_TICK_KEY: "cron", VISION_BUILD_SHA: "new-release",
} as unknown as Env;

function container(image: string, release: string) {
  const state = {
    running: true, images: {base:"image-new"},
    inspect: vi.fn(async () => ({image, labels:{release}})),
    destroy: vi.fn(async () => { state.running = false; }),
    start: vi.fn(() => { state.running = true; }),
  };
  return state;
}

describe("running image updates", () => {
  it("replaces an old image even while the application stays active", async () => {
    const state = container("image-old", "old-release");
    await ensureRunning(state, env);
    expect(state.destroy).toHaveBeenCalledOnce();
    expect(state.start).toHaveBeenCalledWith(expect.objectContaining({image:"image-new", labels:{release:"new-release"}}));
  });
  it("restarts an unchanged image when the release environment changes", async () => {
    const state = container("image-new", "old-release");
    await ensureRunning(state, env);
    expect(state.destroy).toHaveBeenCalledOnce();
  });
  it("keeps the exact running release", async () => {
    const state = container("image-new", "new-release");
    await ensureRunning(state, env);
    expect(state.destroy).not.toHaveBeenCalled();
    expect(state.start).not.toHaveBeenCalled();
  });
});

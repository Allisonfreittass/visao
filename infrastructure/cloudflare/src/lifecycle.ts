import { appEnvironment, type Env } from "./application";

export async function ensureRunning(container: Pick<Container, "inspect" | "destroy" | "start" | "running" | "images">, env: Env) {
  const release = typeof env.VISION_BUILD_SHA === "string" ? env.VISION_BUILD_SHA : "manual";
  const actual = await container.inspect();
  if (actual && (actual.image !== container.images.base || actual.labels.release !== release)) {
    await container.destroy();
  }
  if (!container.running) {
    container.start({ image: container.images.base, instance: "lite", enableInternet: true,
      env: appEnvironment(env), labels: { release } });
  }
}

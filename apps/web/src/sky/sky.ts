// The background of the "Neblina" appearance: rows of pines with fog drifting between them, drawn
// by a slow WebGL shader whose colors follow the local hour.

export type Rgb = [number, number, number];

export interface SkyLook {
  top: Rgb;
  mid: Rgb;
  low: Rgb;
  /** The light behind the fog (sun by day, moon at night). */
  sunColor: Rgb;
  /** The fog itself. */
  cloudColor: Rgb;
  /** The nearest pines; farther ones fade into the fog. */
  tree: Rgb;
  /** How thick the fog is, 0..1. */
  cloud: number;
  /** 0 day, 1 night (dark glass). */
  night: number;
  /** Where the light sits, 0..1 of the screen. */
  sun: [number, number];
}

const hex = (value: string): Rgb => {
  const n = parseInt(value.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
};

/** Key hours of a foggy pine forest; the hours between are blended. */
const KEYS: { hour: number; look: Omit<SkyLook, "sun"> }[] = [
  { hour: 0, look: { top: hex("#141c26"), mid: hex("#1d2833"), low: hex("#24303b"), sunColor: hex("#7f93ad"), cloudColor: hex("#334250"), tree: hex("#070b0f"), cloud: 0.8, night: 1 } },
  { hour: 5, look: { top: hex("#1f2a36"), mid: hex("#2e3a47"), low: hex("#3a4653"), sunColor: hex("#9aa3c0"), cloudColor: hex("#4a5664"), tree: hex("#0b1116"), cloud: 0.9, night: 0.8 } },
  { hour: 6.5, look: { top: hex("#c9cdd6"), mid: hex("#b9bfca"), low: hex("#a8b0bb"), sunColor: hex("#f0d9c8"), cloudColor: hex("#c3c8d0"), tree: hex("#1d262e"), cloud: 1, night: 0.1 } },
  { hour: 9, look: { top: hex("#e4e9eb"), mid: hex("#d3dbdf"), low: hex("#bcc7cd"), sunColor: hex("#ffffff"), cloudColor: hex("#d4dce0"), tree: hex("#1e2b33"), cloud: 0.95, night: 0 } },
  { hour: 15, look: { top: hex("#e1e7ea"), mid: hex("#cfd8dd"), low: hex("#b6c2c9"), sunColor: hex("#fbf6ee"), cloudColor: hex("#d0d9de"), tree: hex("#1c2a32"), cloud: 0.85, night: 0 } },
  { hour: 18, look: { top: hex("#d8cfcf"), mid: hex("#c2b8bc"), low: hex("#a9a1a9"), sunColor: hex("#f3c9a8"), cloudColor: hex("#cdc2c3"), tree: hex("#22232b"), cloud: 0.9, night: 0.15 } },
  { hour: 19.5, look: { top: hex("#4a4d5d"), mid: hex("#3d4352"), low: hex("#343b48"), sunColor: hex("#b49aa8"), cloudColor: hex("#545a6a"), tree: hex("#0d1116"), cloud: 0.85, night: 0.7 } },
  { hour: 21, look: { top: hex("#161e28"), mid: hex("#1e2934"), low: hex("#25313c"), sunColor: hex("#7f93ad"), cloudColor: hex("#36444f"), tree: hex("#070b0f"), cloud: 0.8, night: 1 } },
  { hour: 24, look: { top: hex("#141c26"), mid: hex("#1d2833"), low: hex("#24303b"), sunColor: hex("#7f93ad"), cloudColor: hex("#334250"), tree: hex("#070b0f"), cloud: 0.8, night: 1 } },
];

const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const mixRgb = (a: Rgb, b: Rgb, t: number): Rgb => [mix(a[0], b[0], t), mix(a[1], b[1], t), mix(a[2], b[2], t)];
const smooth = (t: number) => t * t * (3 - 2 * t);

/** How the forest looks at a given local hour (0..24, fractional). */
export function lookAt(hour: number): SkyLook {
  const h = ((hour % 24) + 24) % 24;
  let i = 0;
  while (i < KEYS.length - 2 && KEYS[i + 1].hour <= h) i++;
  const a = KEYS[i];
  const b = KEYS[i + 1];
  const t = smooth((h - a.hour) / (b.hour - a.hour));
  // The light crosses from 6h to 18h behind the fog; at night the moon sits high and dim.
  const day = (h - 6) / 12;
  const sun: [number, number] =
    day >= 0 && day <= 1
      ? [0.12 + 0.76 * day, 0.55 + 0.35 * Math.sin(Math.PI * day)]
      : [0.72, 0.85];
  return {
    top: mixRgb(a.look.top, b.look.top, t),
    mid: mixRgb(a.look.mid, b.look.mid, t),
    low: mixRgb(a.look.low, b.look.low, t),
    sunColor: mixRgb(a.look.sunColor, b.look.sunColor, t),
    cloudColor: mixRgb(a.look.cloudColor, b.look.cloudColor, t),
    tree: mixRgb(a.look.tree, b.look.tree, t),
    cloud: mix(a.look.cloud, b.look.cloud, t),
    night: mix(a.look.night, b.look.night, t),
    sun,
  };
}

export function localHour(date = new Date()): number {
  return date.getHours() + date.getMinutes() / 60;
}

/** A CSS gradient with the same colors, for when WebGL is not there and behind the first frame. */
export function cssGradient(look: SkyLook): string {
  const c = (rgb: Rgb) => `rgb(${rgb.map((v) => Math.round(v * 255)).join(" ")})`;
  return `linear-gradient(180deg, ${c(look.top)} 0%, ${c(look.mid)} 45%, ${c(look.tree)} 100%)`;
}

const VERTEX = `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

const FRAGMENT = `
precision mediump float;
uniform vec2 uRes;
uniform float uTime;
uniform vec3 uTop;
uniform vec3 uMid;
uniform vec3 uLow;
uniform vec3 uGlow;
uniform vec3 uFog;
uniform vec3 uTree;
uniform vec2 uSun;
uniform float uFogAmount;

float hash1(float n) { return fract(sin(n * 127.1) * 43758.5453); }

float hash(vec2 p) {
  p = fract(p * vec2(127.1, 311.7));
  p += dot(p, p + 34.5);
  return fract(p.x * p.y);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
             mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

float layered(vec2 p) {
  float value = 0.0;
  float amplitude = 0.5;
  for (int i = 0; i < 4; i++) {
    value += amplitude * noise(p);
    p = p * 2.03 + vec2(3.1, 7.7);
    amplitude *= 0.5;
  }
  return value;
}

// How much of a pixel one row of pines covers. y is the height above the row's ground line; below
// it the forest is solid. Each cell holds one spruce: tall and narrow, its outline stepping in at
// each tier of branches.
float forest(float x, float y, float seed, float density, float height, float pix) {
  float cx = x * density;
  // The row's base melts into the fog with a ragged edge instead of a straight ground line.
  float edge = 0.035 * noise(vec2(cx * 0.6, seed));
  float cover = smoothstep(0.02, -0.05, y - edge);
  float base = floor(cx);
  for (int k = -1; k <= 1; k++) {
    float cell = base + float(k);
    float r = hash1(cell * 3.17 + seed);
    float center = cell + 0.5 + (r - 0.5) * 0.8;
    float h = height * (0.55 + 0.6 * hash1(cell * 1.93 + seed));
    if (y < h) {
      float t = max(y, 0.0) / h;
      float tier = 1.0 - 0.22 * fract(t * (5.0 + 4.0 * r) + r * 3.0);
      float spread = (0.3 + 0.2 * hash1(cell * 7.31 + seed)) * pow(1.0 - t, 0.9) * tier;
      float sd = abs(cx - center) - spread;
      cover = max(cover, smoothstep(pix, -pix, sd));
    }
  }
  return cover;
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  float aspect = uRes.x / uRes.y;
  float x = uv.x * aspect;
  float px = 1.2 / uRes.y;

  vec3 color = mix(uLow, uMid, smoothstep(0.2, 0.6, uv.y));
  color = mix(color, uTop, smoothstep(0.55, 1.0, uv.y));
  float d = distance(vec2(x, uv.y), vec2(uSun.x * aspect, uSun.y));
  color += uGlow * exp(-d * 2.2) * 0.18;

  // Five rows of pines, far to near; fog drifts after each one, thicker around the treetops.
  for (int i = 0; i < 5; i++) {
    float depth = float(i) / 4.0;
    float density = mix(34.0, 8.0, depth);
    float ground = mix(0.5, -0.02, depth) + 0.04 * sin(x * mix(1.7, 0.9, depth) + float(i) * 2.1);
    // Far rows are softer: fog blurs what is far away.
    float cover = forest(x + float(i) * 3.7, uv.y - ground, float(i) * 11.0, density, mix(0.1, 0.42, depth), density * px * mix(4.0, 1.0, depth));
    vec3 tree = mix(uFog, uTree, mix(0.12, 0.92, depth * depth));
    color = mix(color, tree, cover);
    float speed = mix(0.005, 0.018, depth);
    float drift = layered(vec2(x * mix(1.5, 0.8, depth) + uTime * speed + float(i) * 5.3, uv.y * 3.5 - uTime * 0.003));
    float band = smoothstep(ground + mix(0.4, 0.6, depth), ground - 0.05, uv.y);
    float amount = smoothstep(0.25, 0.8, drift) * band * uFogAmount * mix(0.95, 0.5, depth);
    color = mix(color, uFog, amount);
  }

  // Ground fog rolling slowly at the bottom.
  float ground = layered(vec2(x * 0.7 - uTime * 0.01, uv.y * 2.5 + 7.0));
  color = mix(color, uFog, smoothstep(0.3, 0.85, ground) * smoothstep(0.38, 0.0, uv.y) * 0.55 * uFogAmount);

  // Fine grain so the gradients never band.
  color += (hash(gl_FragCoord.xy + fract(uTime)) - 0.5) * 0.016;
  gl_FragColor = vec4(color, 1.0);
}
`;

/** For tests: the shader sources, checked for words GLSL ES reserves (a "half" broke one build). */
export const SHADER_SOURCES = { vertex: VERTEX, fragment: FRAGMENT };

export interface SkyRenderer {
  draw(look: SkyLook, seconds: number): void;
  resize(width: number, height: number): void;
  dispose(): void;
}

function compile(gl: WebGLRenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) throw new Error("no shader");
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`shader: ${log}`);
  }
  return shader;
}

/** Null when this browser has no WebGL: the CSS gradient stays as the sky. */
export function createSkyRenderer(canvas: HTMLCanvasElement): SkyRenderer | null {
  // alpha: an untouched canvas stays transparent, so the CSS gradient shows if the shader fails.
  const gl = canvas.getContext("webgl", { antialias: false, depth: false, alpha: true, powerPreference: "low-power" });
  if (!gl) return null;
  let program: WebGLProgram;
  try {
    program = gl.createProgram() as WebGLProgram;
    gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX));
    gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return null;
  } catch {
    return null;
  }
  gl.useProgram(program);
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const position = gl.getAttribLocation(program, "aPos");
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
  const at = (name: string) => gl.getUniformLocation(program, name);
  const u = {
    res: at("uRes"), time: at("uTime"), top: at("uTop"), mid: at("uMid"), low: at("uLow"),
    glow: at("uGlow"), fog: at("uFog"), tree: at("uTree"), sun: at("uSun"), fogAmount: at("uFogAmount"),
  };
  return {
    draw(look, seconds) {
      gl.uniform2f(u.res, canvas.width, canvas.height);
      gl.uniform1f(u.time, seconds);
      gl.uniform3fv(u.top, look.top);
      gl.uniform3fv(u.mid, look.mid);
      gl.uniform3fv(u.low, look.low);
      gl.uniform3fv(u.glow, look.sunColor);
      gl.uniform3fv(u.fog, look.cloudColor);
      gl.uniform3fv(u.tree, look.tree);
      gl.uniform2fv(u.sun, look.sun);
      gl.uniform1f(u.fogAmount, look.cloud);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    },
    resize(width, height) {
      canvas.width = width;
      canvas.height = height;
      gl.viewport(0, 0, width, height);
    },
    dispose() {
      gl.deleteBuffer(buffer);
      gl.deleteProgram(program);
    },
  };
}

// The sky behind the "Céu" appearance: a slow WebGL shader whose colors follow the local hour.
// Written for Visão; only the idea (a live sky as wallpaper) comes from elsewhere.

export type Rgb = [number, number, number];

export interface SkyLook {
  top: Rgb;
  mid: Rgb;
  low: Rgb;
  sunColor: Rgb;
  cloudColor: Rgb;
  /** 0 clear, 1 overcast. */
  cloud: number;
  /** 0 day, 1 night (stars, dark glass). */
  night: number;
  /** Sun (or moon) position, 0..1 of the screen. */
  sun: [number, number];
}

const hex = (value: string): Rgb => {
  const n = parseInt(value.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
};

/** Key hours of a day and how the sky looks at each; the hours between are blended. */
const KEYS: { hour: number; look: Omit<SkyLook, "sun"> }[] = [
  { hour: 0, look: { top: hex("#070d22"), mid: hex("#142048"), low: hex("#2b3766"), sunColor: hex("#8fa3d9"), cloudColor: hex("#36426e"), cloud: 0.45, night: 1 } },
  { hour: 5, look: { top: hex("#0d1838"), mid: hex("#2d3a6e"), low: hex("#6a5f8c"), sunColor: hex("#c9a4c4"), cloudColor: hex("#4c5482"), cloud: 0.45, night: 0.85 } },
  { hour: 6.5, look: { top: hex("#5e7fc0"), mid: hex("#d9a9b5"), low: hex("#f6cfa6"), sunColor: hex("#ffd9a8"), cloudColor: hex("#f4d6d4"), cloud: 0.5, night: 0.1 } },
  { hour: 9, look: { top: hex("#6d98dc"), mid: hex("#a8c5ee"), low: hex("#e4ecf8"), sunColor: hex("#fff4dc"), cloudColor: hex("#ffffff"), cloud: 0.55, night: 0 } },
  { hour: 15, look: { top: hex("#6893da"), mid: hex("#a3c1ec"), low: hex("#e8eef8"), sunColor: hex("#fff1d6"), cloudColor: hex("#ffffff"), cloud: 0.6, night: 0 } },
  { hour: 18, look: { top: hex("#4c62a8"), mid: hex("#d897a0"), low: hex("#f4c191"), sunColor: hex("#ffc58a"), cloudColor: hex("#f1c3be"), cloud: 0.5, night: 0.15 } },
  { hour: 19.5, look: { top: hex("#1b2654"), mid: hex("#4a467c"), low: hex("#8c6a86"), sunColor: hex("#d79aa6"), cloudColor: hex("#544c7a"), cloud: 0.45, night: 0.7 } },
  { hour: 21, look: { top: hex("#08102a"), mid: hex("#172350"), low: hex("#2e3a6a"), sunColor: hex("#8fa3d9"), cloudColor: hex("#36426e"), cloud: 0.45, night: 1 } },
  { hour: 24, look: { top: hex("#070d22"), mid: hex("#142048"), low: hex("#2b3766"), sunColor: hex("#8fa3d9"), cloudColor: hex("#36426e"), cloud: 0.45, night: 1 } },
];

const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const mixRgb = (a: Rgb, b: Rgb, t: number): Rgb => [mix(a[0], b[0], t), mix(a[1], b[1], t), mix(a[2], b[2], t)];
const smooth = (t: number) => t * t * (3 - 2 * t);

/** How the sky looks at a given local hour (0..24, fractional). */
export function lookAt(hour: number): SkyLook {
  const h = ((hour % 24) + 24) % 24;
  let i = 0;
  while (i < KEYS.length - 2 && KEYS[i + 1].hour <= h) i++;
  const a = KEYS[i];
  const b = KEYS[i + 1];
  const t = smooth((h - a.hour) / (b.hour - a.hour));
  // The sun crosses from 6h to 18h; the moon takes the night shift, higher and dimmer.
  const day = (h - 6) / 12;
  const sun: [number, number] =
    day >= 0 && day <= 1
      ? [0.12 + 0.76 * day, 0.18 + 0.62 * Math.sin(Math.PI * day)]
      : [0.75, 0.78];
  return {
    top: mixRgb(a.look.top, b.look.top, t),
    mid: mixRgb(a.look.mid, b.look.mid, t),
    low: mixRgb(a.look.low, b.look.low, t),
    sunColor: mixRgb(a.look.sunColor, b.look.sunColor, t),
    cloudColor: mixRgb(a.look.cloudColor, b.look.cloudColor, t),
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
  return `linear-gradient(180deg, ${c(look.top)} 0%, ${c(look.mid)} 55%, ${c(look.low)} 100%)`;
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
uniform vec3 uSunColor;
uniform vec3 uCloudColor;
uniform vec2 uSun;
uniform float uCloud;
uniform float uNight;

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
  for (int i = 0; i < 5; i++) {
    value += amplitude * noise(p);
    p = p * 2.02 + vec2(3.1, 7.7);
    amplitude *= 0.5;
  }
  return value;
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  float aspect = uRes.x / uRes.y;
  vec3 color = mix(uLow, uMid, smoothstep(0.0, 0.6, uv.y));
  color = mix(color, uTop, smoothstep(0.5, 1.0, uv.y));

  vec2 p = vec2(uv.x * aspect, uv.y);
  float d = distance(p, vec2(uSun.x * aspect, uSun.y));
  color += uSunColor * (exp(-d * 3.2) * 0.45 + exp(-d * 16.0) * 0.35) * (1.0 - 0.6 * uNight);

  // Clouds: warped layered noise drifting sideways, thinner towards the top of the screen.
  vec2 q = vec2(p.x * 1.4 + uTime * 0.010, p.y * 2.2);
  float warp = layered(q + 0.8 * layered(q * 0.6 + vec2(uTime * 0.003, 0.0)));
  float shape = smoothstep(0.5 - uCloud * 0.3, 0.88, warp) * (0.6 + 0.4 * smoothstep(1.0, 0.2, uv.y));
  float body = layered(q * 2.6 - vec2(uTime * 0.006, 0.0));
  vec3 cloud = mix(uCloudColor * 0.9, uCloudColor, body);
  color = mix(color, cloud, shape * (0.75 + 0.25 * body));

  // A few stars at night, hidden behind clouds.
  float star = step(0.9982, hash(floor(gl_FragCoord.xy * 0.5)));
  float twinkle = 0.6 + 0.4 * sin(uTime * 2.0 + hash(floor(gl_FragCoord.xy)) * 6.28);
  color += star * twinkle * uNight * (1.0 - shape) * smoothstep(0.25, 0.7, uv.y) * 0.9;

  // Fine grain so the gradient never bands.
  color += (hash(gl_FragCoord.xy + fract(uTime)) - 0.5) * 0.018;
  gl_FragColor = vec4(color, 1.0);
}
`;

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
  const gl = canvas.getContext("webgl", { antialias: false, depth: false, alpha: false, powerPreference: "low-power" });
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
    sunColor: at("uSunColor"), cloudColor: at("uCloudColor"), sun: at("uSun"), cloud: at("uCloud"), night: at("uNight"),
  };
  return {
    draw(look, seconds) {
      gl.uniform2f(u.res, canvas.width, canvas.height);
      gl.uniform1f(u.time, seconds);
      gl.uniform3fv(u.top, look.top);
      gl.uniform3fv(u.mid, look.mid);
      gl.uniform3fv(u.low, look.low);
      gl.uniform3fv(u.sunColor, look.sunColor);
      gl.uniform3fv(u.cloudColor, look.cloudColor);
      gl.uniform2fv(u.sun, look.sun);
      gl.uniform1f(u.cloud, look.cloud);
      gl.uniform1f(u.night, look.night);
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

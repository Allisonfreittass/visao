// The background of the "Neblina" look: rows of pines with fog drifting between them. A port of
// the fragment shader in apps/web/src/sky/sky.ts to a SwiftUI color effect; same rows, same fog,
// same colors (which come from VisaoKit.SkyLook, by the local hour).

#include <metal_stdlib>
#include <SwiftUI/SwiftUI_Metal.h>
using namespace metal;

static float hash1(float n) { return fract(sin(n * 127.1) * 43758.5453); }

static float hash2(float2 p) {
    p = fract(p * float2(127.1, 311.7));
    p += dot(p, p + 34.5);
    return fract(p.x * p.y);
}

static float vnoise(float2 p) {
    float2 i = floor(p);
    float2 f = fract(p);
    float2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash2(i), hash2(i + float2(1.0, 0.0)), u.x),
               mix(hash2(i + float2(0.0, 1.0)), hash2(i + float2(1.0, 1.0)), u.x), u.y);
}

static float layered(float2 p) {
    float value = 0.0;
    float amplitude = 0.5;
    for (int i = 0; i < 4; i++) {
        value += amplitude * vnoise(p);
        p = p * 2.03 + float2(3.1, 7.7);
        amplitude *= 0.5;
    }
    return value;
}

// How much of a pixel one row of pines covers; y is the height above the row's ground line.
static float forest(float x, float y, float seed, float density, float height, float pix) {
    float cx = x * density;
    float edge = 0.035 * vnoise(float2(cx * 0.6, seed));
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

[[ stitchable ]] half4 visaoSky(
    float2 position, half4 incoming, float2 size, float time,
    float3 topColor, float3 midColor, float3 lowColor, float3 glow, float3 fog, float3 treeColor,
    float2 sun, float fogAmount
) {
    // SwiftUI's y runs down; the web shader's runs up.
    float2 uv = float2(position.x / size.x, 1.0 - position.y / size.y);
    float aspect = size.x / size.y;
    float x = uv.x * aspect;
    float px = 1.2 / size.y;

    float3 color = mix(lowColor, midColor, smoothstep(0.2, 0.6, uv.y));
    color = mix(color, topColor, smoothstep(0.55, 1.0, uv.y));
    float d = distance(float2(x, uv.y), float2(sun.x * aspect, sun.y));
    color += glow * exp(-d * 2.2) * 0.18;

    for (int i = 0; i < 5; i++) {
        float depth = float(i) / 4.0;
        float density = mix(34.0, 8.0, depth);
        float ground = mix(0.5, -0.02, depth) + 0.04 * sin(x * mix(1.7, 0.9, depth) + float(i) * 2.1);
        float cover = forest(x + float(i) * 3.7, uv.y - ground, float(i) * 11.0, density, mix(0.1, 0.42, depth), density * px * mix(4.0, 1.0, depth));
        float3 tree = mix(fog, treeColor, mix(0.12, 0.92, depth * depth));
        color = mix(color, tree, cover);
        float speed = mix(0.005, 0.018, depth);
        float drift = layered(float2(x * mix(1.5, 0.8, depth) + time * speed + float(i) * 5.3, uv.y * 3.5 - time * 0.003));
        float band = smoothstep(ground + mix(0.4, 0.6, depth), ground - 0.05, uv.y);
        float amount = smoothstep(0.25, 0.8, drift) * band * fogAmount * mix(0.95, 0.5, depth);
        color = mix(color, fog, amount);
    }

    float groundFog = layered(float2(x * 0.7 - time * 0.01, uv.y * 2.5 + 7.0));
    color = mix(color, fog, smoothstep(0.3, 0.85, groundFog) * smoothstep(0.38, 0.0, uv.y) * 0.55 * fogAmount);

    // Fine grain so the gradients never band.
    color += (hash2(position + fract(time)) - 0.5) * 0.016;
    return half4(half3(color), 1.0h);
}

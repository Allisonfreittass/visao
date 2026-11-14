import SwiftUI
import VisaoKit

/// The pine forest in fog behind every screen ("Neblina"), or the flat dark of "Noite".
/// Drawn at half resolution and 20 frames a second, like the web: the fog has no sharp edges to
/// lose. It stands still with Reduce Motion, in Low Power Mode, when the app is in the
/// background, or when "Neblina em movimento" is off; it still follows the hour.
struct SkyBackground: View {
    @Environment(Appearance.self) private var appearance
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @State private var lowPower = ProcessInfo.processInfo.isLowPowerModeEnabled

    var body: some View {
        Group {
            if appearance.mode == .noite {
                Palette.noite.fundo
            } else {
                GeometryReader { proxy in
                    TimelineView(.animation(minimumInterval: 1.0 / 20, paused: !moving)) { context in
                        forest(size: proxy.size, seconds: seconds(context.date))
                    }
                }
            }
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
        .onReceive(NotificationCenter.default.publisher(for: .NSProcessInfoPowerStateDidChange)) { _ in
            lowPower = ProcessInfo.processInfo.isLowPowerModeEnabled
        }
    }

    private var moving: Bool {
        appearance.moving && !reduceMotion && !lowPower && scenePhase == .active
    }

    /// Kept small so the GPU's float time stays precise; the fog loops too slowly to notice.
    private func seconds(_ date: Date) -> Double {
        date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 20_000)
    }

    private func forest(size: CGSize, seconds: Double) -> some View {
        let look = appearance.look
        let half = CGSize(width: max(size.width / 2, 1), height: max(size.height / 2, 1))
        return Rectangle()
            .frame(width: half.width, height: half.height)
            .colorEffect(
                ShaderLibrary.visaoSky(
                    .float2(half),
                    .float(seconds),
                    .float3(look.top.x, look.top.y, look.top.z),
                    .float3(look.mid.x, look.mid.y, look.mid.z),
                    .float3(look.low.x, look.low.y, look.low.z),
                    .float3(look.sunColor.x, look.sunColor.y, look.sunColor.z),
                    .float3(look.cloudColor.x, look.cloudColor.y, look.cloudColor.z),
                    .float3(look.tree.x, look.tree.y, look.tree.z),
                    .float2(look.sun.x, look.sun.y),
                    .float(look.cloud)
                )
            )
            .drawingGroup()
            .scaleEffect(2, anchor: .topLeading)
            .frame(width: size.width, height: size.height, alignment: .topLeading)
            .background(gradient(look))
    }

    /// The same colors as a gradient, under the first frame.
    private func gradient(_ look: SkyLook) -> LinearGradient {
        func color(_ c: SkyLook.RGB) -> Color { Color(red: c.x, green: c.y, blue: c.z) }
        return LinearGradient(colors: [color(look.top), color(look.mid), color(look.tree)], startPoint: .top, endPoint: .bottom)
    }
}

extension View {
    /// The forest behind this screen, with the palette of the hour for everything on it.
    func visaoBackground() -> some View {
        modifier(VisaoBackground())
    }
}

private struct VisaoBackground: ViewModifier {
    @Environment(Appearance.self) private var appearance
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    func body(content: Content) -> some View {
        content
            .background { SkyBackground() }
            .environment(\.palette, palette)
            .foregroundStyle(palette.tinta)
            .tint(palette.tinta)
    }

    private var palette: Palette {
        appearance.palette.adapted(reduceTransparency: reduceTransparency, increaseContrast: contrast == .increased)
    }
}

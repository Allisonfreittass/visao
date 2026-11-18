import SwiftUI

/// The floor of every screen (apps/web/src/brand/AmbientBackground.tsx): the brand's `bg`, a HUD
/// grid of faint dots every 24 pt, and the sensor's red glow near the top (10% down), behind the
/// mascot of Início. The glow breathes (opacity .10 → .16); still with Reduce Motion.
struct AmbientBackground: View {
    @Environment(\.palette) private var palette
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var breathe = false

    var body: some View {
        GeometryReader { proxy in
            ZStack {
                palette.bg
                Canvas { context, size in
                    let dot = Path(ellipseIn: CGRect(x: -0.5, y: -0.5, width: 1, height: 1))
                    var y: CGFloat = 12
                    while y < size.height {
                        var x: CGFloat = 12
                        while x < size.width {
                            context.fill(dot.offsetBy(dx: x, dy: y), with: .color(.white.opacity(0.045)))
                            x += 24
                        }
                        y += 24
                    }
                }
                RadialGradient(
                    colors: [Palette.red.opacity(0.16), .clear],
                    center: UnitPoint(x: 0.5, y: 0.1), startRadius: 0,
                    endRadius: max(proxy.size.width, proxy.size.height) * 0.42
                )
                .opacity(breathe ? 1 : 0.625)
            }
            .frame(width: proxy.size.width, height: proxy.size.height)
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
        .allowsHitTesting(false)
        .onAppear {
            guard !reduceMotion else { breathe = false; return }
            withAnimation(.easeInOut(duration: 4.8).repeatForever(autoreverses: true)) { breathe = true }
        }
    }
}

extension View {
    /// The ambient floor behind this screen, with the theme's palette for everything on it.
    func visaoBackground() -> some View {
        modifier(VisaoBackground())
    }
}

private struct VisaoBackground: ViewModifier {
    @Environment(Appearance.self) private var appearance
    @Environment(\.colorSchemeContrast) private var contrast

    func body(content: Content) -> some View {
        content
            .background { AmbientBackground().environment(\.palette, palette) }
            .environment(\.palette, palette)
            .foregroundStyle(palette.text)
            .tint(palette.text2)
    }

    private var palette: Palette {
        appearance.palette.adapted(reduceTransparency: false, increaseContrast: contrast == .increased)
    }
}

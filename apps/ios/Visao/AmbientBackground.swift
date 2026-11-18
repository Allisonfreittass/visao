import SwiftUI

/// The floor of every screen (apps/web/src/brand/AmbientBackground.tsx): the brand's warm `bg`
/// and three big soft blobs in the corners (coral, lavender, peach) drifting slowly. Still with
/// Reduce Motion. The only gradient in the app.
struct AmbientBackground: View {
    @Environment(\.palette) private var palette
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var drift = false

    var body: some View {
        GeometryReader { proxy in
            let side = max(proxy.size.width, proxy.size.height) * 0.45
            let dx = proxy.size.width * 0.03, dy = proxy.size.height * 0.03
            ZStack {
                palette.bg
                blob(palette.blob1, side: side)
                    .position(x: proxy.size.width * 0.05, y: proxy.size.height * 0.04)
                    .offset(x: drift ? dx : -dx, y: drift ? dy : -dy)
                blob(palette.blob2, side: side)
                    .position(x: proxy.size.width * 1.02, y: proxy.size.height * 0.42)
                    .offset(x: drift ? -dx : dx, y: drift ? dy : -dy)
                blob(palette.blob3, side: side)
                    .position(x: proxy.size.width * 0.45, y: proxy.size.height * 1.02)
                    .offset(x: drift ? dx : -dx, y: drift ? -dy : dy)
            }
            .frame(width: proxy.size.width, height: proxy.size.height)
            .clipped()
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
        .allowsHitTesting(false)
        .onAppear {
            guard !reduceMotion else { return }
            withAnimation(.easeInOut(duration: 24).repeatForever(autoreverses: true)) { drift = true }
        }
    }

    private func blob(_ color: Color, side: CGFloat) -> some View {
        Circle()
            .fill(color)
            .frame(width: side, height: side)
            .blur(radius: 60)
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
            .tint(palette.accentText)
    }

    private var palette: Palette {
        appearance.palette.adapted(reduceTransparency: false, increaseContrast: contrast == .increased)
    }
}

import Observation
import SwiftUI
import UIKit
import VisaoKit

/// The look (apps/web/src/brand/theme.ts). The brand ("Ciclope Sentinela") shows only the dark
/// theme: `forced` wins over the saved choice, and Ajustes hides the picker. The light theme and
/// the choice stay in the code in case they come back.
@MainActor
@Observable
final class Appearance {
    enum Mode: String, CaseIterable, Identifiable {
        case claro, escuro, sistema
        var id: String { rawValue }
        var label: String {
            switch self {
            case .claro: "Claro"
            case .escuro: "Escuro"
            case .sistema: "Sistema"
            }
        }
    }

    var mode: Mode {
        didSet { UserDefaults.standard.set(mode.rawValue, forKey: "theme") }
    }
    /// What the iPhone itself is set to, read at the root while "Sistema" lets it through.
    var systemDark = false

    init() {
        mode = Mode(rawValue: UserDefaults.standard.string(forKey: "theme") ?? "") ?? .sistema
    }

    /// The theme the brand shows, whatever is saved. nil would bring the choice back.
    static let forced: Mode? = .escuro

    var isDark: Bool {
        let shown = Appearance.forced ?? mode
        return shown == .escuro || (shown == .sistema && systemDark)
    }

    /// nil lets the system decide (and lets `systemDark` follow it).
    var preferredScheme: ColorScheme? {
        switch Appearance.forced ?? mode {
        case .claro: .light
        case .escuro: .dark
        case .sistema: nil
        }
    }

    var palette: Palette { isDark ? .escuro : .claro }
}

/// The brand's color tokens (apps/web/src/brand/tokens.css). Red is rare: only the mascot's eye,
/// the primary button, focus, the active tab mark, one highlighted word and real errors. Amber
/// is attention, green is success, the rest is graphite. Text on red uses `onRed`, never white.
/// The older names (tinta, fundo...) point to the new ones.
struct Palette: Equatable {
    var bg: Color
    var surface: Color
    var surface2: Color
    var border: Color
    var borderStrong: Color
    var text: Color
    var textMuted: Color
    var accentText: Color
    var accentStrong: Color
    var blob1: Color
    var blob2: Color
    var blob3: Color
    var success: Color
    var danger: Color
    var shadow: Color
    /// Pages and yes/no cards stay dark, like a screen, in both themes.
    var cardInk: Color
    var cardInk2: Color
    var isDark: Bool

    var accent: Color { Palette.red }
    var onAccent: Color { Palette.onRed }
    var iris: Color { surface2 }
    var red: Color { Palette.red }
    var redText: Color { Color(rgb: 0xff5a4e) }
    var onRed: Color { Palette.onRed }
    var amber: Color { Color(rgb: 0xf5b544) }
    var amberBg: Color { Color(rgb: 0x2a2212) }
    var green: Color { Color(rgb: 0x4ade80) }
    var greenDot: Color { Color(rgb: 0x16a34a) }
    var text2: Color { Color(rgb: 0xc2c3c8) }
    var bubbleUser: Color { Color(rgb: 0x1f2126) }
    var bubbleUserBorder: Color { Color(rgb: 0x2c2e34) }
    static let red = Color(rgb: 0xff3b30)
    static let onRed = Color(rgb: 0x0b0b0d)
    static let graphite = Color(rgb: 0x2b2e34)
    static let graphiteEdge = Color(rgb: 0x454952)
    static let graphiteLine = Color(rgb: 0x5a5f69)
    static let socket = Color(rgb: 0x050506)
    /// Kept for older call sites: the mascot's red.
    static let accentColor = red

    // Older names, kept so the screens keep compiling; new code uses the names above.
    var tinta: Color { text }
    var tintaSuave: Color { textMuted }
    var tintaFraca: Color { textMuted }
    var linha: Color { border }
    var linhaForte: Color { borderStrong }
    var estanho: Color { accentText }
    var erro: Color { danger }
    var sucesso: Color { success }
    var fundo: Color { bg }
    var fundoElevado: Color { surface }
    var fundoHover: Color { surface2 }
    var vidro: Color { surface }
    var vidroForte: Color { surface }
    var vidroBorda: Color { border }
    var bolhaDele: Color { .clear }
    var bolhaDeleTinta: Color { text }
    var bolhaSua: Color { surface2 }
    var pilulaAtiva: Color { text }
    var pilulaAtivaTinta: Color { bg }
    var sombra: Color { shadow }
    var cartaoPagina: Color { cardInk }
    var lanterna: Color { accent }
    /// No frosted glass in this brand: solid cards on the ambient floor.
    var usesGlass: Bool { false }

    /// Increase Contrast: firmer lines (the muted text already passes 4.5:1).
    func adapted(reduceTransparency: Bool, increaseContrast: Bool) -> Palette {
        var p = self
        if increaseContrast {
            p.border = p.borderStrong
            p.textMuted = isDark ? Color(rgb: 0xc4c4cc) : Color(rgb: 0x55545a)
        }
        return p
    }

    static let claro = Palette(
        bg: Color(rgb: 0xf6f4f1), surface: Color(rgb: 0xffffff), surface2: Color(rgb: 0xefece7),
        border: Color(rgb: 0xe6e1da), borderStrong: Color(rgb: 0xd3ccc2),
        text: Color(rgb: 0x16161a), textMuted: Color(rgb: 0x6b6a70),
        accentText: Color(rgb: 0xc2410c), accentStrong: Color(rgb: 0xd9480f),
        blob1: Color(rgb: 0xff8a6b, opacity: 0.35), blob2: Color(rgb: 0xb9a6ff, opacity: 0.40), blob3: Color(rgb: 0xffc9a8, opacity: 0.30),
        success: Color(rgb: 0x15803d), danger: Color(rgb: 0xb91c1c),
        shadow: Color(rgb: 0x16161a, opacity: 0.06),
        cardInk: Color(rgb: 0x17181d), cardInk2: Color(rgb: 0x23252c),
        isDark: false
    )

    static let escuro = Palette(
        bg: Color(rgb: 0x09090b), surface: Color(rgb: 0x141518), surface2: Color(rgb: 0x1d1f24),
        border: Color(rgb: 0x24262b), borderStrong: Color(rgb: 0x34363c),
        text: Color(rgb: 0xededef), textMuted: Color(rgb: 0x9a9ba2),
        accentText: Color(rgb: 0xc2c3c8), accentStrong: Color(rgb: 0xff5a4e),
        blob1: .clear, blob2: .clear, blob3: .clear,
        success: Color(rgb: 0x4ade80), danger: Color(rgb: 0xff3b30),
        shadow: .clear,
        cardInk: Color(rgb: 0x141518), cardInk2: Color(rgb: 0x1d1f24),
        isDark: true
    )
}

/// The brand's spacing (base 4) and radii (tokens.css).
enum Space {
    static let s1: CGFloat = 4, s2: CGFloat = 8, s3: CGFloat = 12, s4: CGFloat = 16, s5: CGFloat = 24, s6: CGFloat = 32, s7: CGFloat = 48
}

enum Radius {
    static let chip: CGFloat = 10, card: CGFloat = 16, panel: CGFloat = 24
}

private struct PaletteKey: EnvironmentKey {
    static let defaultValue = Palette.claro
}

extension EnvironmentValues {
    var palette: Palette {
        get { self[PaletteKey.self] }
        set { self[PaletteKey.self] = newValue }
    }
}

extension Color {
    init(rgb: UInt32, opacity: Double = 1) {
        self.init(
            red: Double((rgb >> 16) & 255) / 255, green: Double((rgb >> 8) & 255) / 255,
            blue: Double(rgb & 255) / 255, opacity: opacity
        )
    }
}

/// The brand's three faces: Space Grotesk (600/700) for titles, the greeting and the name; Inter
/// Tight for text; JetBrains Mono only for small metadata ("conferido hoje, 09:00"). The files ship
/// with the app; without them, SF in the same weights. Every size follows Dynamic Type.
enum Typo {
    static let displayFace = "SpaceGrotesk-Light"

    /// `italic` is kept for older call sites and ignored: the highlighted word is colored, not
    /// slanted. Space Grotesk is a variable font: the weight is set on its axis.
    static func display(_ size: CGFloat, relativeTo style: Font.TextStyle = .largeTitle, italic: Bool = false, weight: Font.Weight = .bold) -> Font {
        let scaled = UIFontMetrics(forTextStyle: style.uiStyle).scaledValue(for: size)
        if let base = UIFont(name: displayFace, size: scaled) {
            let wght: CGFloat = weight == .semibold ? 600 : 700
            let axis = 0x7767_6874 // 'wght'
            let descriptor = base.fontDescriptor.addingAttributes([
                UIFontDescriptor.AttributeName(rawValue: kCTFontVariationAttribute as String): [axis: wght],
            ])
            return Font(UIFont(descriptor: descriptor, size: scaled))
        }
        return .system(size: scaled, weight: weight)
    }

    static func text(_ style: Font.TextStyle = .body, weight: Font.Weight = .regular) -> Font {
        let name = weight == .regular ? "InterTight-Regular" : "InterTight-Medium"
        if UIFont(name: name, size: 17) != nil {
            return .custom(name, size: UIFont.preferredFont(forTextStyle: style.uiStyle).pointSize, relativeTo: style)
        }
        return .system(style).weight(weight)
    }

    static func mono(_ style: Font.TextStyle = .footnote) -> Font {
        if UIFont(name: "JetBrainsMono-Regular", size: 13) != nil {
            return .custom("JetBrainsMono-Regular", size: UIFont.preferredFont(forTextStyle: style.uiStyle).pointSize, relativeTo: style)
        }
        return .system(style, design: .monospaced)
    }
}

private extension Font.TextStyle {
    var uiStyle: UIFont.TextStyle {
        switch self {
        case .largeTitle: .largeTitle
        case .title: .title1
        case .title2: .title2
        case .title3: .title3
        case .headline: .headline
        case .subheadline: .subheadline
        case .callout: .callout
        case .footnote: .footnote
        case .caption: .caption1
        case .caption2: .caption2
        default: .body
        }
    }
}

/// A small section label: Inter Tight medium, muted, in normal case (no spaced capitals).
struct Rotulo: View {
    let text: String
    @Environment(\.palette) private var palette

    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .font(Typo.text(.footnote, weight: .medium))
            .foregroundStyle(palette.textMuted)
    }
}

extension View {
    /// A card of the brand (named `glass` from before): solid surface, 1 pt border, and the soft
    /// card shadow in the light theme (only the border in the dark one).
    func glass(_ palette: Palette, cornerRadius: CGFloat, strong: Bool = true, shadow: Bool = true) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        return background(shape.fill(palette.surface))
            .overlay(shape.strokeBorder(palette.border, lineWidth: 1))
            .shadow(color: shadow ? palette.shadow : .clear, radius: 12, y: 4)
    }

    /// A round button on a solid surface, like the avatar of the web.
    func glassCircle(_ palette: Palette, size: CGFloat = 44) -> some View {
        frame(width: size, height: size)
            .contentShape(Circle())
            .liquidGlass(palette, in: Circle())
    }
}

extension View {
    /// Controls that float over the content (buttons, the message box, the tab bar): a solid
    /// surface with a border and the floating shadow. Named from the glass it replaced.
    @ViewBuilder
    func liquidGlass<S: Shape>(_ palette: Palette, in shape: S, tint: Color? = nil, interactive: Bool = true) -> some View {
        background(shape.fill(tint ?? palette.surface))
            .overlay(shape.stroke(palette.border, lineWidth: 1))
            .shadow(color: palette.shadow.opacity(palette.isDark ? 0 : 1.4), radius: 14, y: 6)
    }

    /// Kept for older call sites: nothing to group without glass.
    func glassGroup(spacing: CGFloat = 12) -> some View { self }
}

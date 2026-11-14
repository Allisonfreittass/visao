import Observation
import SwiftUI
import UIKit
import VisaoKit

/// The two looks the web has (apps/web/src/ceu.css and styles.css): "Neblina", glass over the
/// pine forest whose light follows the hour, and "Noite", the brand's flat dark theme.
@MainActor
@Observable
final class Appearance {
    enum Mode: String, CaseIterable, Identifiable {
        case neblina, noite
        var id: String { rawValue }
        var label: String { self == .neblina ? "Neblina" : "Noite" }
    }

    var mode: Mode {
        didSet { UserDefaults.standard.set(mode.rawValue, forKey: "appearance") }
    }
    /// The fog drifting. Off, the forest only follows the hour (and costs nothing).
    var moving: Bool {
        didSet { UserDefaults.standard.set(moving, forKey: "skyMoving") }
    }
    private(set) var look = SkyLook.at(hour: SkyLook.localHour())

    init() {
        mode = Mode(rawValue: UserDefaults.standard.string(forKey: "appearance") ?? "") ?? .neblina
        moving = UserDefaults.standard.object(forKey: "skyMoving") as? Bool ?? true
    }

    /// Called every minute: the sky (and day or night glass) follows the local hour.
    func tick(_ date: Date = Date()) {
        let next = SkyLook.at(hour: SkyLook.localHour(date))
        if next != look { look = next }
    }

    var isDark: Bool { mode == .noite || look.isNight }

    var palette: Palette {
        switch mode {
        case .noite: .noite
        case .neblina: look.isNight ? .neblinaNoite : .neblinaDia
        }
    }
}

/// The color tokens of the web, by name (ceu.css / rastros/tokens.css).
struct Palette: Equatable {
    var tinta: Color
    var tintaSuave: Color
    var tintaFraca: Color
    var linha: Color
    var linhaForte: Color
    var estanho: Color
    var erro: Color
    var fundo: Color
    var fundoElevado: Color
    var fundoHover: Color
    var vidro: Color
    var vidroForte: Color
    var vidroBorda: Color
    var bolhaDele: Color
    var bolhaDeleTinta: Color
    var bolhaSua: Color
    var pilulaAtiva: Color
    var pilulaAtivaTinta: Color
    var sombra: Color
    /// Pages are dark like a screen in every look.
    var cartaoPagina = Color(rgb: 0x1b262d)
    var lanterna = Color(rgb: 0xe0483f)
    /// Glass over the forest; flat panels in "Noite".
    var usesGlass: Bool

    /// "Conectado", on: teal, darker on light glass.
    var sucesso: Color { self == .neblinaDia ? Color(rgb: 0x1b6a70) : Color(rgb: 0x5cc2c9) }

    static let neblinaDia = Palette(
        tinta: Color(rgb: 0x17222a), tintaSuave: Color(rgb: 0x36454e), tintaFraca: Color(rgb: 0x56656e),
        linha: Color(rgb: 0x1d1d1f, opacity: 0.08), linhaForte: Color(rgb: 0x1d1d1f, opacity: 0.14),
        estanho: Color(rgb: 0x4f6366), erro: Color(rgb: 0xb3342b),
        fundo: Color(red: 240 / 255, green: 244 / 255, blue: 245 / 255, opacity: 0.6),
        fundoElevado: Color(red: 244 / 255, green: 247 / 255, blue: 248 / 255, opacity: 0.82),
        fundoHover: Color(rgb: 0x17222a, opacity: 0.06),
        vidro: Color(red: 236 / 255, green: 242 / 255, blue: 244 / 255, opacity: 0.5),
        vidroForte: Color(red: 242 / 255, green: 246 / 255, blue: 247 / 255, opacity: 0.86),
        vidroBorda: Color.white.opacity(0.45),
        bolhaDele: Color(red: 248 / 255, green: 250 / 255, blue: 250 / 255, opacity: 0.95), bolhaDeleTinta: Color(rgb: 0x17222a),
        bolhaSua: Color(red: 214 / 255, green: 225 / 255, blue: 230 / 255, opacity: 0.86),
        pilulaAtiva: Color(rgb: 0x2e3d45), pilulaAtivaTinta: Color(rgb: 0xeef2f3),
        sombra: Color(red: 15 / 255, green: 25 / 255, blue: 30 / 255, opacity: 0.1),
        usesGlass: true
    )

    static let neblinaNoite = Palette(
        tinta: Color(rgb: 0xf5f5f7), tintaSuave: Color(rgb: 0xc7cbd8), tintaFraca: Color(rgb: 0x9aa0b4),
        linha: Color(rgb: 0xf5f5f7, opacity: 0.1), linhaForte: Color(rgb: 0xf5f5f7, opacity: 0.18),
        estanho: Color(rgb: 0xa9bcbd), erro: Color(rgb: 0xff7a6e),
        fundo: Color(red: 20 / 255, green: 24 / 255, blue: 40 / 255, opacity: 0.5),
        fundoElevado: Color(red: 28 / 255, green: 32 / 255, blue: 52 / 255, opacity: 0.78),
        fundoHover: Color(rgb: 0xf5f5f7, opacity: 0.08),
        vidro: Color(red: 24 / 255, green: 28 / 255, blue: 48 / 255, opacity: 0.45),
        vidroForte: Color(red: 30 / 255, green: 34 / 255, blue: 56 / 255, opacity: 0.82),
        vidroBorda: Color.white.opacity(0.12),
        bolhaDele: Color(red: 30 / 255, green: 40 / 255, blue: 48 / 255, opacity: 0.94), bolhaDeleTinta: Color(rgb: 0xf5f5f7),
        bolhaSua: Color(red: 58 / 255, green: 74 / 255, blue: 84 / 255, opacity: 0.82),
        pilulaAtiva: Color(rgb: 0xf5f5f7), pilulaAtivaTinta: Color(rgb: 0x1d1d1f),
        sombra: Color.black.opacity(0.3),
        usesGlass: true
    )

    static let noite = Palette(
        tinta: Color(rgb: 0xe6e9e6), tintaSuave: Color(rgb: 0xa9b4b2), tintaFraca: Color(rgb: 0x7e8b8a),
        linha: Color(red: 214 / 255, green: 228 / 255, blue: 226 / 255, opacity: 0.09),
        linhaForte: Color(red: 214 / 255, green: 228 / 255, blue: 226 / 255, opacity: 0.22),
        estanho: Color(rgb: 0xa9bcbd), erro: Color(rgb: 0xff7a6e),
        fundo: Color(rgb: 0x090e10), fundoElevado: Color(rgb: 0x0e1619), fundoHover: Color(rgb: 0x142024),
        vidro: Color(rgb: 0x0e1619), vidroForte: Color(rgb: 0x0e1619),
        vidroBorda: Color(red: 214 / 255, green: 228 / 255, blue: 226 / 255, opacity: 0.09),
        bolhaDele: Color(rgb: 0x0e1619), bolhaDeleTinta: Color(rgb: 0xe6e9e6),
        bolhaSua: Color(rgb: 0x142024),
        pilulaAtiva: Color(rgb: 0xe6e9e6), pilulaAtivaTinta: Color(rgb: 0x090e10),
        sombra: Color.clear,
        usesGlass: false
    )
}

private struct PaletteKey: EnvironmentKey {
    static let defaultValue = Palette.neblinaDia
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

/// The web's three faces: Instrument Serif for titles, Inter Tight for text, JetBrains Mono for
/// code and labels. When those files are in the app they are used; until then, the iPhone's own
/// serif (New York), SF and SF Mono. Every size follows Dynamic Type.
enum Typo {
    static func display(_ size: CGFloat, relativeTo style: Font.TextStyle = .largeTitle, italic: Bool = false) -> Font {
        let name = italic ? "InstrumentSerif-Italic" : "InstrumentSerif-Regular"
        if UIFont(name: name, size: size) != nil { return .custom(name, size: size, relativeTo: style) }
        let base = Font.system(style, design: .serif)
        return italic ? base.italic() : base
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

/// A label in the brand's "rótulo" style: small mono capitals.
struct Rotulo: View {
    let text: String
    @Environment(\.palette) private var palette

    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text.uppercased())
            .font(Typo.mono(.caption))
            .tracking(0.6)
            .foregroundStyle(palette.tintaFraca)
    }
}

extension View {
    /// The frosted glass of the web (backdrop blur + a tint + a light border); a flat panel in "Noite".
    func glass(_ palette: Palette, cornerRadius: CGFloat, strong: Bool = true, shadow: Bool = true) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        return background {
            if palette.usesGlass {
                shape.fill(.ultraThinMaterial)
                    .overlay(shape.fill(strong ? palette.vidroForte : palette.vidro))
            } else {
                shape.fill(palette.fundoElevado)
            }
        }
        .overlay(shape.strokeBorder(palette.vidroBorda, lineWidth: 1))
        .shadow(color: shadow ? palette.sombra : .clear, radius: 16, y: 6)
    }

    /// A round glass button, like the drawer and avatar buttons of the web.
    func glassCircle(_ palette: Palette, size: CGFloat = 44) -> some View {
        frame(width: size, height: size)
            .background {
                if palette.usesGlass {
                    Circle().fill(.ultraThinMaterial).overlay(Circle().fill(palette.vidro))
                } else {
                    Circle().fill(palette.fundoElevado)
                }
            }
            .overlay(Circle().strokeBorder(palette.vidroBorda, lineWidth: 1))
            .shadow(color: palette.sombra.opacity(0.5), radius: 8, y: 2)
    }
}

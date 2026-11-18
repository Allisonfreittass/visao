// Gera os ícones e imagens da marca "Ciclope Sentinela" a partir do desenho do mascote
// (o mesmo de apps/web/src/ciclope/Ciclope.tsx). Rode na raiz do repositório:
//
//     swift brand/generate-assets.swift
//
// Precisa de macOS (CoreGraphics, CoreText, ImageIO) e da fonte em
// apps/ios/Visao/Fonts/SpaceGrotesk.ttf. Escreve em brand/, apps/web/public/ e no AppIcon do iOS.
import CoreGraphics
import CoreText
import Foundation
import ImageIO
import UniformTypeIdentifiers

let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let brand = root.appendingPathComponent("brand")
let pub = root.appendingPathComponent("apps/web/public")
let appIcon = root.appendingPathComponent("apps/ios/Visao/Assets.xcassets/AppIcon.appiconset")

func rgb(_ hex: UInt32, _ a: CGFloat = 1) -> CGColor {
    CGColor(srgbRed: CGFloat((hex >> 16) & 255) / 255, green: CGFloat((hex >> 8) & 255) / 255, blue: CGFloat(hex & 255) / 255, alpha: a)
}

let red = rgb(0xFF3B30)
let graphite = rgb(0x2B2E34)

enum Look { case normal, dark, tinted }

struct Style {
    var body: CGColor = graphite
    var eye: CGColor = red
    var highlight: CGColor = rgb(0xFFE2E0)
    var edge: CGColor = rgb(0x454952)
    var line: CGColor = rgb(0x5A5F69)
    var socketStroke: CGColor = rgb(0x3E424A)
    var grille: CGColor = rgb(0x15171A)

    static func of(_ look: Look) -> Style {
        switch look {
        case .normal: Style()
        case .dark: Style(body: rgb(0x141518), edge: rgb(0x2C2E34), line: rgb(0x3A3D45))
        case .tinted: Style(body: rgb(0x2E2E2E), eye: rgb(0xFFFFFF), highlight: rgb(0xFFFFFF), edge: rgb(0x4A4A4A), line: rgb(0x5E5E5E), socketStroke: rgb(0x444444), grille: rgb(0x1A1A1A))
        }
    }
}

func context(_ w: Int, _ h: Int) -> CGContext {
    let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    // Top-left origin, like SVG.
    ctx.translateBy(x: 0, y: CGFloat(h))
    ctx.scaleBy(x: 1, y: -1)
    return ctx
}

func save(_ ctx: CGContext, _ url: URL) {
    let image = ctx.makeImage()!
    let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(dest, image, nil)
    CGImageDestinationFinalize(dest)
    print("ok", url.path.replacingOccurrences(of: root.path + "/", with: ""))
}

func pngData(_ ctx: CGContext) -> Data {
    let data = NSMutableData()
    let dest = CGImageDestinationCreateWithData(data as CFMutableData, UTType.png.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(dest, ctx.makeImage()!, nil)
    CGImageDestinationFinalize(dest)
    return data as Data
}

func circle(_ ctx: CGContext, _ cx: CGFloat, _ cy: CGFloat, _ r: CGFloat) -> CGRect {
    CGRect(x: cx - r, y: cy - r, width: 2 * r, height: 2 * r)
}

/// The mascot in its 100 × 100 box, drawn into `rect`. `bleed`: the body fills the square with
/// no rounding and no edge (app icons). `simple`: only body, eye and core (16–48 px).
func drawSentinela(_ ctx: CGContext, in rect: CGRect, look: Look = .normal, bleed: Bool = false, simple: Bool = false) {
    let s = Style.of(look)
    ctx.saveGState()
    ctx.translateBy(x: rect.minX, y: rect.minY)
    ctx.scaleBy(x: rect.width / 100, y: rect.height / 100)
    let box = CGRect(x: 0, y: 0, width: 100, height: 100)
    let body = bleed ? CGPath(rect: box, transform: nil) : CGPath(roundedRect: box, cornerWidth: 30, cornerHeight: 30, transform: nil)
    ctx.addPath(body); ctx.setFillColor(s.body); ctx.fillPath()
    // top highlight
    ctx.saveGState()
    ctx.addPath(body); ctx.clip()
    let hl = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB), colors: [rgb(0xFFFFFF, 0.12), rgb(0xFFFFFF, 0)] as CFArray, locations: [0, 0.5])!
    ctx.drawLinearGradient(hl, start: CGPoint(x: 0, y: 0), end: CGPoint(x: 0, y: 100), options: [])
    ctx.restoreGState()
    if !bleed && !simple {
        ctx.addPath(CGPath(roundedRect: box.insetBy(dx: 1, dy: 1), cornerWidth: 29, cornerHeight: 29, transform: nil))
        ctx.setStrokeColor(s.edge); ctx.setLineWidth(1.5); ctx.strokePath()
    }
    // socket
    ctx.setFillColor(rgb(0x050506)); ctx.fillEllipse(in: circle(ctx, 50, 46, 23))
    if !simple { ctx.setStrokeColor(s.socketStroke); ctx.setLineWidth(2); ctx.strokeEllipse(in: circle(ctx, 50, 46, 23)) }
    if simple {
        // At 16–48 px: a bigger core and its ring, nothing else.
        ctx.setStrokeColor(s.eye); ctx.setLineWidth(5); ctx.strokeEllipse(in: circle(ctx, 50, 47, 12))
        ctx.setFillColor(s.eye); ctx.fillEllipse(in: circle(ctx, 50, 47, 6))
        ctx.restoreGState()
        return
    }
    // glow: a soft red disc behind the iris
    ctx.saveGState()
    ctx.addEllipse(in: circle(ctx, 50, 46, 23)); ctx.clip()
    let glow = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB), colors: [s.eye.copy(alpha: 0.75)!, s.eye.copy(alpha: 0.35)!, s.eye.copy(alpha: 0)!] as CFArray, locations: [0, 0.55, 1])!
    ctx.drawRadialGradient(glow, startCenter: CGPoint(x: 50, y: 47), startRadius: 0, endCenter: CGPoint(x: 50, y: 47), endRadius: 18, options: [])
    ctx.restoreGState()
    ctx.setStrokeColor(s.eye); ctx.setLineWidth(3); ctx.strokeEllipse(in: circle(ctx, 50, 47, 10.5))
    ctx.setFillColor(s.eye); ctx.fillEllipse(in: circle(ctx, 50, 47, 4.5))
    ctx.setFillColor(s.highlight); ctx.fillEllipse(in: circle(ctx, 50, 47, 1.7))
    // lid (metal), clipped by the eye
    ctx.saveGState()
    ctx.addEllipse(in: circle(ctx, 50, 46, 23)); ctx.clip()
    ctx.setFillColor(s.body); ctx.fill(CGRect(x: 22, y: 18, width: 56, height: 17))
    ctx.setStrokeColor(s.line); ctx.setLineWidth(1.6)
    ctx.move(to: CGPoint(x: 28, y: 35)); ctx.addLine(to: CGPoint(x: 72, y: 35)); ctx.strokePath()
    ctx.restoreGState()
    // LED
    ctx.setFillColor(s.eye); ctx.fillEllipse(in: circle(ctx, 83, 17, 2.6))
    // grille
    ctx.setStrokeColor(s.grille); ctx.setLineWidth(2.6); ctx.setLineCap(.round)
    ctx.move(to: CGPoint(x: 41, y: 79)); ctx.addLine(to: CGPoint(x: 59, y: 79))
    ctx.move(to: CGPoint(x: 44, y: 84)); ctx.addLine(to: CGPoint(x: 56, y: 84))
    ctx.strokePath()
    ctx.restoreGState()
}

func square(_ size: Int, _ draw: (CGContext) -> Void) -> CGContext {
    let ctx = context(size, size)
    draw(ctx)
    return ctx
}

// ---------- iOS AppIcon (1024, full bleed: iOS rounds it) ----------
for (look, name) in [(Look.normal, "AppIcon.png"), (.dark, "AppIcon-dark.png"), (.tinted, "AppIcon-tinted.png")] {
    let ctx = square(1024) { ctx in
        if look == .tinted { ctx.setFillColor(rgb(0x000000)); ctx.fill(CGRect(x: 0, y: 0, width: 1024, height: 1024)) }
        drawSentinela(ctx, in: CGRect(x: 0, y: 0, width: 1024, height: 1024), look: look, bleed: true)
    }
    save(ctx, appIcon.appendingPathComponent(name))
    save(ctx, brand.appendingPathComponent(name.replacingOccurrences(of: "AppIcon", with: "app-icon").lowercased()))
}
let contents = """
{
  "images" : [
    { "filename" : "AppIcon.png", "idiom" : "universal", "platform" : "ios", "size" : "1024x1024" },
    { "appearances" : [ { "appearance" : "luminosity", "value" : "dark" } ], "filename" : "AppIcon-dark.png", "idiom" : "universal", "platform" : "ios", "size" : "1024x1024" },
    { "appearances" : [ { "appearance" : "luminosity", "value" : "tinted" } ], "filename" : "AppIcon-tinted.png", "idiom" : "universal", "platform" : "ios", "size" : "1024x1024" }
  ],
  "info" : { "author" : "xcode", "version" : 1 }
}

"""
try! contents.write(to: appIcon.appendingPathComponent("Contents.json"), atomically: true, encoding: .utf8)

// ---------- Web ----------
save(square(180) { drawSentinela($0, in: CGRect(x: 0, y: 0, width: 180, height: 180), bleed: true) }, pub.appendingPathComponent("apple-touch-icon.png"))
for size in [192, 512] {
    save(square(size) { drawSentinela($0, in: CGRect(x: 0, y: 0, width: size, height: size)) }, pub.appendingPathComponent("icon-\(size).png"))
}
// Maskable: full-bleed graphite, the mascot inside the 80% safe zone (20% margin).
save(square(512) { ctx in
    ctx.setFillColor(graphite); ctx.fill(CGRect(x: 0, y: 0, width: 512, height: 512))
    let inner = 512 * 0.6
    drawSentinela(ctx, in: CGRect(x: (512 - inner) / 2, y: (512 - inner) / 2, width: inner, height: inner))
}, pub.appendingPathComponent("maskable-512.png"))

// favicon.ico (16/32/48, PNG inside), the simple drawing.
var icons: [(Int, Data)] = []
for size in [16, 32, 48] {
    icons.append((size, pngData(square(size) { drawSentinela($0, in: CGRect(x: 0, y: 0, width: size, height: size), simple: true) })))
}
var ico = Data([0, 0, 1, 0, UInt8(icons.count), 0])
var offset = 6 + 16 * icons.count
for (size, data) in icons {
    var entry = Data([UInt8(size % 256), UInt8(size % 256), 0, 0, 1, 0, 32, 0])
    withUnsafeBytes(of: UInt32(data.count).littleEndian) { entry.append(contentsOf: $0) }
    withUnsafeBytes(of: UInt32(offset).littleEndian) { entry.append(contentsOf: $0) }
    ico.append(entry)
    offset += data.count
}
for (_, data) in icons { ico.append(data) }
try! ico.write(to: pub.appendingPathComponent("favicon.ico"))
print("ok apps/web/public/favicon.ico")

// ---------- Wordmark in outlines (Space Grotesk 700, tracking .04em) ----------
let fontURL = root.appendingPathComponent("apps/ios/Visao/Fonts/SpaceGrotesk.ttf") as CFURL
let descriptor = (CTFontManagerCreateFontDescriptorsFromURL(fontURL) as! [CTFontDescriptor])[0]
func spaceGrotesk(_ size: CGFloat) -> CTFont {
    let base = CTFontCreateWithFontDescriptor(descriptor, size, nil)
    let wght = 0x7767_6874 as NSNumber
    let varied = CTFontDescriptorCreateCopyWithAttributes(CTFontCopyFontDescriptor(base), [kCTFontVariationAttribute: [wght: 700]] as CFDictionary)
    return CTFontCreateWithFontDescriptor(varied, size, nil)
}

let word = Array("V.I.S.A.O.")
func wordGlyphs(_ font: CTFont, tracking: CGFloat) -> [(Character, CGPath, CGFloat)] {
    var x: CGFloat = 0
    var out: [(Character, CGPath, CGFloat)] = []
    for c in word {
        var unichar = Array(String(c).utf16)
        var glyph = CGGlyph()
        CTFontGetGlyphsForCharacters(font, &unichar, &glyph, 1)
        var advance = CGSize.zero
        CTFontGetAdvancesForGlyphs(font, .horizontal, &glyph, &advance, 1)
        if let path = CTFontCreatePathForGlyph(font, glyph, nil) { out.append((c, path, x)) }
        x += advance.width + tracking
    }
    return out
}

func svgPath(_ path: CGPath, dx: CGFloat, baseline: CGFloat) -> String {
    var d = ""
    func p(_ pt: CGPoint) -> String { String(format: "%.2f %.2f", pt.x + dx, baseline - pt.y) }
    path.applyWithBlock { el in
        let e = el.pointee
        switch e.type {
        case .moveToPoint: d += "M" + p(e.points[0])
        case .addLineToPoint: d += "L" + p(e.points[0])
        case .addQuadCurveToPoint: d += "Q" + p(e.points[0]) + " " + p(e.points[1])
        case .addCurveToPoint: d += "C" + p(e.points[0]) + " " + p(e.points[1]) + " " + p(e.points[2])
        case .closeSubpath: d += "Z"
        @unknown default: break
        }
    }
    return d
}

let size: CGFloat = 100
let font = spaceGrotesk(size)
let glyphs = wordGlyphs(font, tracking: size * 0.04)
let ascent = CTFontGetAscent(font), descent = CTFontGetDescent(font)
let width = (glyphs.last.map { $0.2 + $0.1.boundingBox.maxX } ?? 0)
var paths = ""
for (i, (c, path, x)) in glyphs.enumerated() {
    let color = c == "." ? (i == glyphs.count - 1 ? "#FF3B30" : "#9A9BA2") : "#EDEDEF"
    paths += "  <path fill=\"\(color)\" d=\"\(svgPath(path, dx: x, baseline: ascent))\"/>\n"
}
let svg = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 \(Int(width.rounded(.up))) \(Int((ascent + descent).rounded(.up)))" role="img" aria-label="V.I.S.A.O.">
\(paths)</svg>

"""
try! svg.write(to: brand.appendingPathComponent("visao-wordmark.svg"), atomically: true, encoding: .utf8)
print("ok brand/visao-wordmark.svg")

// ---------- Lockup and OG image (1200 × 630) ----------
func drawBackground(_ ctx: CGContext, _ w: CGFloat, _ h: CGFloat, glowAt: CGPoint) {
    ctx.setFillColor(rgb(0x09090B)); ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.setFillColor(rgb(0xFFFFFF, 0.045))
    var y: CGFloat = 12
    while y < h { var x: CGFloat = 12; while x < w { ctx.fillEllipse(in: CGRect(x: x - 1, y: y - 1, width: 2, height: 2)); x += 24 }; y += 24 }
    let glow = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB), colors: [rgb(0xFF3B30, 0.16), rgb(0xFF3B30, 0)] as CFArray, locations: [0, 1])!
    ctx.drawRadialGradient(glow, startCenter: glowAt, startRadius: 0, endCenter: glowAt, endRadius: max(w, h) * 0.42, options: [])
}

func drawWord(_ ctx: CGContext, at origin: CGPoint, size: CGFloat) -> CGFloat {
    let f = spaceGrotesk(size)
    let gs = wordGlyphs(f, tracking: size * 0.04)
    let asc = CTFontGetAscent(f)
    for (i, (c, path, x)) in gs.enumerated() {
        let color = c == "." ? (i == gs.count - 1 ? rgb(0xFF3B30) : rgb(0x9A9BA2)) : rgb(0xEDEDEF)
        ctx.saveGState()
        ctx.translateBy(x: origin.x + x, y: origin.y + asc)
        ctx.scaleBy(x: 1, y: -1)
        ctx.addPath(path); ctx.setFillColor(color); ctx.fillPath()
        ctx.restoreGState()
    }
    return gs.last.map { $0.2 + $0.1.boundingBox.maxX } ?? 0
}

let og = context(1200, 630)
drawBackground(og, 1200, 630, glowAt: CGPoint(x: 600, y: 315))
let mascot: CGFloat = 160, wordSize: CGFloat = 72, gap: CGFloat = 36
let wordWidth = drawWord(context(10, 10), at: .zero, size: wordSize)
let totalWidth = mascot + gap + wordWidth
let left = (1200 - totalWidth) / 2
drawSentinela(og, in: CGRect(x: left, y: 315 - mascot / 2, width: mascot, height: mascot))
let capHeight = CTFontGetCapHeight(spaceGrotesk(wordSize)), asc = CTFontGetAscent(spaceGrotesk(wordSize))
_ = drawWord(og, at: CGPoint(x: left + mascot + gap, y: 315 - asc + capHeight / 2), size: wordSize)
save(og, brand.appendingPathComponent("og-image.png"))
save(og, pub.appendingPathComponent("og-image.png"))

// The mascot alone, for documents.
save(square(512) { drawSentinela($0, in: CGRect(x: 0, y: 0, width: 512, height: 512)) }, brand.appendingPathComponent("sentinela-512.png"))

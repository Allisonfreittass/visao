import SwiftUI
import UIKit
import VisaoKit

/// A reply's text: the blocks from VisaoKit.Markdown, with system text styles so Dynamic Type
/// scales everything, and code that keeps its lines (scrolls sideways) and has a copy button.
struct MarkdownView: View {
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(MarkdownCache.blocks(text).enumerated()), id: \.offset) { _, block in
                switch block {
                case .paragraph(let body):
                    Text(Markdown.inline(body))
                case .heading(let body):
                    Text(Markdown.inline(body)).font(Typo.text(.headline, weight: .medium))
                        .accessibilityAddTraits(.isHeader)
                case .bullets(let items):
                    ListBlock(items: items) { _ in "•" }
                case .numbered(let items):
                    ListBlock(items: items) { "\($0 + 1)." }
                case .code(let language, let code):
                    CodeBlock(language: language, code: code)
                }
            }
        }
        .textSelection(.enabled)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct ListBlock: View {
    let items: [String]
    let marker: (Int) -> String
    @Environment(\.palette) private var palette

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(marker(index)).foregroundStyle(palette.tintaFraca).monospacedDigit()
                    Text(Markdown.inline(item))
                }
            }
        }
    }
}

/// The part of a reply meant to be used: its language and a copy button (.code-block on the web).
private struct CodeBlock: View {
    let language: String
    let code: String
    @Environment(\.palette) private var palette
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text((language.isEmpty ? "código" : language).uppercased())
                    .font(Typo.mono(.caption))
                    .tracking(0.6)
                    .foregroundStyle(palette.tintaFraca)
                Spacer()
                Button {
                    UIPasteboard.general.string = code
                    copied = true
                    Task {
                        try? await Task.sleep(for: .seconds(1.8))
                        copied = false
                    }
                } label: {
                    Text(copied ? "✓ Copiado" : "Copiar")
                        .font(Typo.text(.footnote, weight: .medium))
                        .underline(!copied, color: palette.linhaForte)
                        .foregroundStyle(palette.tinta)
                }
                .buttonStyle(.plain)
                .sensoryFeedback(.success, trigger: copied) { _, now in now }
                .accessibilityLabel(copied ? "Copiado" : "Copiar código")
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            Rectangle().fill(palette.linha).frame(height: 1)
            ScrollView(.horizontal) {
                Text(code)
                    .font(Typo.mono(.footnote))
                    .foregroundStyle(palette.tinta)
                    .fixedSize(horizontal: true, vertical: false)
                    .padding(14)
            }
        }
        .background(palette.fundoElevado, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(palette.linhaForte))
    }
}

/// A reply is parsed once, not again every time the list is drawn.
@MainActor
enum MarkdownCache {
    private static var cache: [String: [MarkdownBlock]] = [:]

    static func blocks(_ text: String) -> [MarkdownBlock] {
        if let hit = cache[text] { return hit }
        let parsed = Markdown.blocks(text)
        if cache.count > 400 { cache.removeAll(keepingCapacity: true) }
        cache[text] = parsed
        return parsed
    }
}

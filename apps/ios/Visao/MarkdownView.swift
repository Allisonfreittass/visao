import SwiftUI
import UIKit
import VisaoKit

/// A reply's text: the blocks from VisaoKit.Markdown, with system text styles so Dynamic Type
/// scales everything, and code that keeps its lines (scrolls sideways) and has a copy button.
struct MarkdownView: View {
    let text: String
    /// Still being written: parsed each time (not cached), and stable as it grows: an open code
    /// block is already code, an unfinished list is already a list.
    var live = false
    /// While it is written, the newest characters of the last paragraph come in faded.
    var freshTail = 0
    @Environment(\.palette) private var palette

    var body: some View {
        let blocks = live ? Markdown.blocks(text) : MarkdownCache.blocks(text)
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { index, block in
                switch block {
                case .paragraph(let body) where freshTail > 0 && index == blocks.count - 1:
                    fresh(body)
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

    /// The last paragraph with its newest characters lighter, in two steps, so the words that
    /// just arrived fade in as the text moves on. Only plain text: a half-written ** or link is
    /// shown as it is.
    private func fresh(_ body: String) -> Text {
        guard body.count > freshTail, body.rangeOfCharacter(from: CharacterSet(charactersIn: "*`[")) == nil else {
            return Text(Markdown.inline(body))
        }
        let newest = body.suffix(freshTail / 2)
        let newer = body.dropLast(freshTail / 2).suffix(freshTail - freshTail / 2)
        let settled = body.dropLast(freshTail)
        return Text(String(settled))
            + Text(String(newer)).foregroundStyle(palette.bolhaDeleTinta.opacity(0.6))
            + Text(String(newest)).foregroundStyle(palette.bolhaDeleTinta.opacity(0.3))
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

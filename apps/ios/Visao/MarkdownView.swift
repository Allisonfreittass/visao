import SwiftUI
import UIKit
import VisaoKit

/// A reply's text: the blocks from VisaoKit.Markdown, with system text styles so Dynamic Type
/// scales everything, and code that keeps its lines (scrolls sideways) and has a copy button.
struct MarkdownView: View {
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(Markdown.blocks(text).enumerated()), id: \.offset) { _, block in
                switch block {
                case .paragraph(let body):
                    Text(Markdown.inline(body))
                case .heading(let body):
                    Text(Markdown.inline(body)).font(.headline)
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

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(marker(index)).foregroundStyle(.secondary).monospacedDigit()
                    Text(Markdown.inline(item))
                }
            }
        }
    }
}

/// The part of a reply meant to be used: its language and a copy button.
private struct CodeBlock: View {
    let language: String
    let code: String
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(language.isEmpty ? "código" : language)
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                Spacer()
                Button {
                    UIPasteboard.general.string = code
                    copied = true
                    Task {
                        try? await Task.sleep(for: .seconds(1.8))
                        copied = false
                    }
                } label: {
                    Label(copied ? "Copiado" : "Copiar", systemImage: copied ? "checkmark" : "doc.on.doc")
                        .font(.caption)
                }
                .buttonStyle(.borderless)
                .sensoryFeedback(.success, trigger: copied) { _, now in now }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            Divider()
            ScrollView(.horizontal) {
                Text(code)
                    .font(.callout.monospaced())
                    .fixedSize(horizontal: true, vertical: false)
                    .padding(10)
            }
        }
        .background(Color(uiColor: .tertiarySystemBackground), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(.quaternary))
    }
}

import SwiftUI
import UIKit
import VisaoKit
import WebKit

/// The card under the reply that said it would write a page (docs/ARTEFATOS.md): "Criando…", then
/// Abrir. Dark like a screen in every look, as on the web.
struct ArtifactCard: View {
    let artifact: Artifact
    let onOpen: () -> Void
    @Environment(\.palette) private var palette
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var ready: Bool { artifact.status == "ready" && artifact.path != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 2) {
                Text(artifact.title)
                    .font(Typo.text(.body, weight: .medium))
                    .foregroundStyle(Color(rgb: 0xf5f5f7))
                Text(subtitle)
                    .font(Typo.text(.subheadline))
                    .foregroundStyle(artifact.status == "failed" ? Color(rgb: 0xff8b80) : Color(rgb: 0x9aa0b4))
            }
            if artifact.status == "pending" {
                HStack(spacing: 10) {
                    ThinkingDots(color: Color(rgb: 0xc7cbd8))
                    Text("Escrevendo \(artifact.title)")
                        .lineLimit(1)
                }
                .font(Typo.text(.subheadline))
                .foregroundStyle(Color(rgb: 0xc7cbd8))
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(Color(rgb: 0x27343c), in: Capsule())
            }
            if ready {
                HStack {
                    Spacer()
                    Button(action: onOpen) {
                        Text("Abrir")
                            .font(Typo.text(.callout, weight: .medium))
                            .padding(.horizontal, 22)
                            .frame(minHeight: 40)
                            .foregroundStyle(palette.cartaoPagina)
                            .background(Color(rgb: 0xeef2f3), in: Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(18)
        .frame(maxWidth: 420, alignment: .leading)
        .background(palette.cartaoPagina, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .shadow(color: .black.opacity(0.25), radius: 20, y: 8)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Página: \(artifact.title). \(subtitle)")
        .accessibilityAddTraits(ready ? .isButton : [])
    }

    private var subtitle: String {
        switch artifact.status {
        case "pending": "Criando a página…"
        case "failed": artifact.error ?? "Não deu para criar a página."
        default: "index.html"
        }
    }
}

/// The page over the chat. No JavaScript and no cookies: the page cannot reach the app or your
/// session (the server already serves it with an opaque origin). Links open in Safari.
struct PageSheet: View {
    let artifact: Artifact
    let url: URL
    let onDelete: () -> Void
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL
    @State private var confirmDelete = false
    @State private var loading = true

    var body: some View {
        NavigationStack {
            PageWebView(url: url, loading: $loading)
                .ignoresSafeArea(edges: .bottom)
                .overlay { if loading { ProgressView() } }
                .navigationTitle(artifact.title)
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Fechar") { dismiss() }
                    }
                    ToolbarItemGroup(placement: .primaryAction) {
                        ShareLink(item: url, subject: Text(artifact.title)) {
                            Image(systemName: "square.and.arrow.up")
                        }
                        .accessibilityLabel("Compartilhar: quem tiver o link consegue abrir")
                        Menu {
                            Button("Abrir no Safari", systemImage: "safari") { openURL(url) }
                            Button("Copiar link", systemImage: "link") { UIPasteboard.general.url = url }
                            Button("Apagar", systemImage: "trash", role: .destructive) { confirmDelete = true }
                        } label: {
                            Image(systemName: "ellipsis.circle")
                        }
                        .accessibilityLabel("Mais")
                    }
                }
                .confirmationDialog("Apagar “\(artifact.title)”?", isPresented: $confirmDelete, titleVisibility: .visible) {
                    Button("Apagar", role: .destructive) {
                        onDelete()
                        dismiss()
                    }
                } message: {
                    Text("O link para de funcionar para todo mundo que tiver ele.")
                }
        }
        .presentationDragIndicator(.visible)
    }
}

struct PageWebView: UIViewRepresentable {
    let url: URL
    @Binding var loading: Bool

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = false
        configuration.websiteDataStore = .nonPersistent()
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.allowsLinkPreview = false
        view.isOpaque = false
        view.backgroundColor = .clear
        var request = URLRequest(url: url)
        request.setValue(nil, forHTTPHeaderField: "Referer")
        view.load(request)
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, WKNavigationDelegate {
        let parent: PageWebView

        init(_ parent: PageWebView) { self.parent = parent }

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping @MainActor (WKNavigationActionPolicy) -> Void) {
            // Only the page itself loads here; a tapped link goes to Safari.
            if action.navigationType == .linkActivated, let target = action.request.url {
                if ["http", "https"].contains(target.scheme?.lowercased() ?? "") { UIApplication.shared.open(target) }
                decisionHandler(.cancel)
                return
            }
            decisionHandler(.allow)
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            parent.loading = false
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            parent.loading = false
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            parent.loading = false
        }
    }
}

/// The three dots of "Pensando", one after the other.
struct ThinkingDots: View {
    var color: Color
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 0.2, paused: reduceMotion)) { context in
            let step = Int(context.date.timeIntervalSinceReferenceDate * 3) % 3
            HStack(spacing: 4) {
                ForEach(0..<3, id: \.self) { i in
                    Circle()
                        .fill(color)
                        .frame(width: 6, height: 6)
                        .opacity(reduceMotion || i == step ? 1 : 0.35)
                }
            }
        }
        .accessibilityHidden(true)
    }
}

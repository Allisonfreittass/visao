import SwiftUI
import UIKit
import VisaoKit

/// "Visão" in the share sheet of any app (docs/COMPARTILHAR.md, ADR-0018). It reads what was
/// picked, shows a preview with an optional comment, sends, and closes: the reply arrives later as
/// a notice and in the continuous conversation.
final class ShareViewController: UIViewController {
    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .clear
        let config = SharedConfig.main
        let api = APIClient(baseURL: config.server, tokens: config.tokens())
        let model = ShareModel(api: api, close: { [weak self] in self?.finish() })
        let host = UIHostingController(rootView: ShareView(model: model))
        host.view.backgroundColor = .clear
        addChild(host)
        host.view.frame = view.bounds
        host.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(host.view)
        host.didMove(toParent: self)
        let items = extensionContext?.inputItems.compactMap { $0 as? NSExtensionItem } ?? []
        Task { await model.load(items) }
    }

    private func finish() {
        extensionContext?.completeRequest(returningItems: nil)
    }
}

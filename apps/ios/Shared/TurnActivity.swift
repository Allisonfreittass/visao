#if os(iOS)
import ActivityKit
import Foundation

/// What the lock-screen card and the Dynamic Island show while he answers (docs/STATUS.md): the
/// steps of the turn, as /conversations/{id}/progress says them. Shared by the app and the
/// VisaoLive extension.
struct VisaoTurnAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        /// Every step so far, in order ("Pensando", "Pesquisando “voos”"…).
        var steps: [String]
        /// The detail of the current step, when there is one (the term, the site).
        var detail: String?
        /// The reply arrived: the card says so and shows its beginning.
        var done: Bool
        /// The first words of the reply, or why it stopped.
        var excerpt: String?
        /// Stopped or failed instead of answering.
        var failed: Bool

        var current: String { steps.last ?? "Pensando" }
    }

    /// The name he chose, or nil while he has none.
    var agentName: String?
    var startedAt: Date
}
#endif

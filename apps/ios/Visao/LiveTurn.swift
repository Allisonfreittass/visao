import ActivityKit
import Foundation
import UIKit
import VisaoKit

/// The Live Activity of a reply in progress (docs/APP_IOS.md, stage 7). With the free Apple ID it
/// is updated only by the app: while it is on screen, and for the short time the iPhone gives an
/// app after it leaves (a background task). The push path (APNs) is built and switched off by
/// VISAO_LIVE_ACTIVITY_PUSH until there is a paid account and a server route for it.
@MainActor
final class LiveTurn {
    static let shared = LiveTurn()

    private var activity: Activity<VisaoTurnAttributes>?
    private var background: UIBackgroundTaskIdentifier = .invalid
    private let push = LiveActivityPush()

    var allowed: Bool { ActivityAuthorizationInfo().areActivitiesEnabled }

    /// A turn started: the card appears with "Pensando".
    func start(agentName: String?, conversationId: String?) {
        guard allowed, activity == nil else { return }
        let attributes = VisaoTurnAttributes(agentName: agentName, startedAt: Date())
        let state = VisaoTurnAttributes.ContentState(steps: ["Pensando"], detail: nil, done: false, excerpt: nil, failed: false)
        do {
            activity = try Activity.request(
                attributes: attributes,
                content: ActivityContent(state: state, staleDate: Date().addingTimeInterval(10 * 60)),
                pushType: push.enabled ? .token : nil
            )
            if let activity, push.enabled { push.follow(activity, conversationId: conversationId) }
        } catch {
            activity = nil
        }
    }

    /// Each new step from /progress.
    func update(_ steps: [ProgressStep]) {
        guard let activity, !steps.isEmpty else { return }
        let state = VisaoTurnAttributes.ContentState(
            steps: steps.map(\.label), detail: steps.last?.detail, done: false, excerpt: nil, failed: false
        )
        // ActivityKit is safe to call from any thread; the type just isn't marked Sendable.
        nonisolated(unsafe) let card = activity
        Task { await card.update(ActivityContent(state: state, staleDate: Date().addingTimeInterval(10 * 60))) }
    }

    /// The turn ended. Seen in the app, the card leaves at once; away, it stays saying it answered.
    func finish(reply: String?, failed: Bool, onScreen: Bool) {
        guard let activity else { return }
        self.activity = nil
        let excerpt = reply.map { String(VoiceRules.speakable($0).prefix(140)) }
        let state = VisaoTurnAttributes.ContentState(
            steps: activity.content.state.steps, detail: nil, done: true,
            excerpt: failed ? (reply ?? "Parou antes de responder.") : excerpt, failed: failed
        )
        let policy: ActivityUIDismissalPolicy = onScreen ? .immediate : .after(Date().addingTimeInterval(30 * 60))
        nonisolated(unsafe) let card = activity
        Task {
            await card.end(ActivityContent(state: state, staleDate: nil), dismissalPolicy: policy)
            self.endBackgroundTime()
        }
    }

    /// The app left the screen mid-turn: ask the iPhone for the few seconds it allows, to keep
    /// following the turn and close the card with the reply if it arrives in time.
    func beginBackgroundTime() {
        guard background == .invalid, activity != nil else { return }
        background = UIApplication.shared.beginBackgroundTask(withName: "visao.turn") { [weak self] in
            Task { @MainActor in self?.endBackgroundTime() }
        }
    }

    func endBackgroundTime() {
        guard background != .invalid else { return }
        UIApplication.shared.endBackgroundTask(background)
        background = .invalid
    }
}

/// Updating the card by push (APNs), for when the turn outlives the app's time in the background.
/// Needs the paid Apple Developer account (the aps-environment entitlement) and a server route
/// that does not exist yet; see docs/APP_IOS.md. Off unless VISAO_LIVE_ACTIVITY_PUSH = YES.
@MainActor
final class LiveActivityPush {
    var enabled: Bool {
        (Bundle.main.object(forInfoDictionaryKey: "VisaoLiveActivityPush") as? String)?.uppercased() == "YES"
    }

    /// Hands each push token of the card to the server, which would send the steps and the end
    /// of the turn to APNs with it.
    func follow(_ activity: Activity<VisaoTurnAttributes>, conversationId: String?) {
        nonisolated(unsafe) let card = activity
        Task {
            for await token in card.pushTokenUpdates {
                let hex = token.map { String(format: "%02x", $0) }.joined()
                await register(token: hex, conversationId: conversationId)
            }
        }
    }

    /// The route the server would need (not in the API today): POST /live-activities with
    /// {"conversation_id", "token"}. Until it exists, the token is not sent anywhere.
    private func register(token: String, conversationId: String?) async {}
}

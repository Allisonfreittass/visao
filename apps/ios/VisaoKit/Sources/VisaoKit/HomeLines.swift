import Foundation

/// The words on Início, built from real data (apps/web/src/components/InboxView.tsx).
public enum HomeLines {
    /// "2 painéis", with a non-breaking space; nil when nothing is watched.
    public static func watchCount(_ panels: [LivePanel]?) -> String? {
        let watched = (panels ?? []).filter { $0.status != "paused" }.count
        guard watched > 0 else { return nil }
        return "\(watched)\u{00a0}\(watched == 1 ? "painel" : "painéis")"
    }

    /// "Sistemas prontos · Mac conectado · 1 voo aguardando preço".
    public static func status(online: Bool, macOnline: Bool?, pendingCount: Int, panels: [LivePanel]?) -> String {
        guard online else { return "Sem conexão com o servidor." }
        var parts = ["Sistemas prontos"]
        if macOnline == true { parts.append("Mac conectado") }
        if macOnline == false { parts.append("Sem conexão com o Mac") }
        let open = (panels ?? []).flatMap(\.items).filter { $0.cost == nil }
        let flights = open.filter { $0.kind == "flight" }.count
        let hotels = open.count - flights
        if flights > 0 { parts.append("\(flights) \(flights == 1 ? "voo aguardando" : "voos aguardando") preço") }
        if hotels > 0 { parts.append("\(hotels) \(hotels == 1 ? "hospedagem aguardando" : "hospedagens aguardando") preço") }
        if pendingCount > 0 { parts.append("\(pendingCount) \(pendingCount == 1 ? "pedido esperando" : "pedidos esperando") você") }
        return parts.joined(separator: " · ")
    }
}

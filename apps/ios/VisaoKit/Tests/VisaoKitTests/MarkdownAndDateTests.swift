import XCTest
@testable import VisaoKit

final class MarkdownTests: XCTestCase {
    func testBlocks() {
        let text = """
        # Plano

        Primeiro **isso**.
        Depois aquilo.

        - um
        - dois

        1. a
        2. b

        ```Swift
        let x = 1

        print(x)
        ```
        fim
        """
        XCTAssertEqual(Markdown.blocks(text), [
            .heading("Plano"),
            .paragraph("Primeiro **isso**.\nDepois aquilo."),
            .bullets(["um", "dois"]),
            .numbered(["a", "b"]),
            .code(language: "swift", code: "let x = 1\n\nprint(x)"),
            .paragraph("fim"),
        ])
    }

    func testUnclosedFenceStillRendersAsCode() {
        XCTAssertEqual(Markdown.blocks("Veja:\n```py\nprint(1)"), [
            .paragraph("Veja:"),
            .code(language: "py", code: "print(1)"),
        ])
    }

    func testOnlyWebLinksStayLinks() {
        let safe = Markdown.inline("[site](https://exemplo.com) e [x](javascript:alert(1)) e [f](file:///etc/passwd)")
        let links = safe.runs.compactMap(\.link)
        XCTAssertEqual(links.map(\.absoluteString), ["https://exemplo.com"])
        XCTAssertEqual(String(safe.characters), "site e x e f")
    }

    func testHTMLStaysText() {
        let text = Markdown.inline("<b>oi</b> `code`")
        XCTAssertEqual(String(text.characters), "<b>oi</b> code")
    }
}

final class DateTests: XCTestCase {
    func testOffsetlessAndMicrosecondDatesAreUTC() throws {
        let reference = try XCTUnwrap(APIDate.parse("2026-11-13T12:00:00Z"))
        XCTAssertEqual(APIDate.parse("2026-11-13T12:00:00"), reference)
        XCTAssertEqual(try XCTUnwrap(APIDate.parse("2026-11-13T12:00:00.123456")).timeIntervalSince(reference), 0.123, accuracy: 0.0005)
        XCTAssertEqual(APIDate.parse("2026-11-13T09:00:00-03:00"), reference)
        XCTAssertEqual(APIDate.parse("2026-11-13T12:00:00.5+00:00")?.timeIntervalSince(reference), 0.5)
        XCTAssertNil(APIDate.parse("ontem"))
    }

    func testDayLabel() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Sao_Paulo")!
        let now = try XCTUnwrap(APIDate.parse("2026-11-13T18:00:00-03:00"))
        let today = try XCTUnwrap(APIDate.parse("2026-11-13T09:05:00-03:00"))
        let yesterday = try XCTUnwrap(APIDate.parse("2026-11-12T22:30:00-03:00"))
        let earlier = try XCTUnwrap(APIDate.parse("2026-11-03T08:00:00-03:00"))

        XCTAssertTrue(DayLabel.text(for: today, now: now, calendar: calendar).hasPrefix("Hoje, "))
        XCTAssertTrue(DayLabel.text(for: yesterday, now: now, calendar: calendar).hasPrefix("Ontem, "))
        XCTAssertTrue(DayLabel.text(for: earlier, now: now, calendar: calendar).hasPrefix("03/11, "))
    }

    func testQuotedExcerptIsOneLine() {
        let m = Message(id: "m", role: .user, content: "linha um\n\n  linha   dois", createdAt: Date())
        XCTAssertEqual(m.quoted.excerpt, "linha um linha dois")
    }
}

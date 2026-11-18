import XCTest
@testable import VisaoKit

/// The opening (Intro.test.ts on the web).
final class OpeningTests: XCTestCase {
    private var calendar: Calendar = {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(identifier: "America/Sao_Paulo")!
        return c
    }()

    private func at(_ day: Int, _ hour: Int) -> Date {
        calendar.date(from: DateComponents(year: 2026, month: 11, day: day, hour: hour))!
    }

    func testTheGreetingFollowsTheHour() {
        XCTAssertEqual(Opening.greeting(hour: 6), "Bom dia")
        XCTAssertEqual(Opening.greeting(hour: 13), "Boa tarde")
        XCTAssertEqual(Opening.greeting(hour: 20), "Boa noite")
        XCTAssertEqual(Opening.greeting(hour: 2), "Boa noite")
        XCTAssertEqual(Opening.greeting(hour: 5), "Bom dia")
        XCTAssertEqual(Opening.greeting(hour: 12), "Boa tarde")
        XCTAssertEqual(Opening.greeting(hour: 18), "Boa noite")
        XCTAssertEqual(Opening.greeting(at: at(17, 13), calendar: calendar), "Boa tarde")
    }

    func testItPlaysOnceADay() throws {
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "visao-opening-\(UUID())"))
        XCTAssertTrue(Opening.takeTurn(now: at(17, 9), reduceMotion: false, defaults: defaults, calendar: calendar))
        XCTAssertFalse(Opening.takeTurn(now: at(17, 22), reduceMotion: false, defaults: defaults, calendar: calendar), "the same day: not again")
        XCTAssertTrue(Opening.takeTurn(now: at(18, 7), reduceMotion: false, defaults: defaults, calendar: calendar), "the next day")
        XCTAssertFalse(Opening.shouldPlay(now: at(17, 9), lastDay: "2026-11-17", reduceMotion: false, calendar: calendar))
        XCTAssertTrue(Opening.shouldPlay(now: at(17, 9), lastDay: "2026-11-16", reduceMotion: false, calendar: calendar))
    }

    func testItNeverPlaysWithReduceMotion() throws {
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "visao-opening-\(UUID())"))
        XCTAssertFalse(Opening.takeTurn(now: at(17, 9), reduceMotion: true, defaults: defaults, calendar: calendar))
        XCTAssertNil(defaults.string(forKey: Opening.dayKey), "not marked: it did not play")
    }
}

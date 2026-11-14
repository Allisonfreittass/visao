import XCTest
@testable import VisaoKit

/// The Brazilian sounds the Kokoro voice "pf_dora" learned from espeak-ng pt-br (via misaki).
final class BrazilianPhonemesTests: XCTestCase {
    private func ipa(_ word: String) -> String { BrazilianPhonemes.word(word) }

    func testTAndDBeforeISoundAreAffricates() {
        XCTAssertEqual(ipa("tia"), "ʧˈiɐ")
        XCTAssertEqual(ipa("leite"), "lˈAʧi")
        XCTAssertEqual(ipa("dizia"), "ʤizˈiɐ")
        XCTAssertEqual(ipa("onde"), "ˈõʤi")
        XCTAssertEqual(ipa("tarde"), "tˈaɾʤi", "not the Lisbon tˈaɾədɨ")
    }

    func testFinalVowelsAndL() {
        XCTAssertEqual(ipa("gato"), "ɡˈatʊ")
        XCTAssertEqual(ipa("bife"), "bˈifi")
        XCTAssertEqual(ipa("sol"), "sˈɔw".replacingOccurrences(of: "ɔ", with: "o"))
        XCTAssertEqual(ipa("brasil"), "bɾazˈiw")
        XCTAssertEqual(ipa("casas"), "kˈazɐs")
    }

    func testStrongR() {
        XCTAssertEqual(ipa("rato"), "xˈatʊ")
        XCTAssertEqual(ipa("carro"), "kˈaxʊ")
        XCTAssertEqual(ipa("caro"), "kˈaɾʊ")
        XCTAssertEqual(ipa("amar"), "ɐmˈax")
    }

    func testNasals() {
        XCTAssertEqual(ipa("mão"), "mˈɐ̃ʊ̃")
        XCTAssertEqual(ipa("mãe"), "mˈɐ̃ɪ̃")
        XCTAssertEqual(ipa("campo"), "kˈɐ̃pʊ")
        XCTAssertEqual(ipa("tempo"), "tˈẽpʊ")
        XCTAssertEqual(ipa("falam"), "fˈalɐ̃ʊ̃")
        XCTAssertEqual(ipa("viagem"), "viˈaʒẽɪ̃")
    }

    func testStressRulesAndAccents() {
        XCTAssertEqual(ipa("café"), "kafˈɛ")
        XCTAssertEqual(ipa("médico"), "mˈɛʤikʊ")
        XCTAssertEqual(ipa("papel"), "papˈew")
        XCTAssertEqual(ipa("janela"), "ʒɐnˈelɐ")
        XCTAssertEqual(ipa("ônibus"), "ˈonibus")
    }

    func testConsonantsAndDigraphs() {
        XCTAssertEqual(ipa("chave"), "ʃˈavi")
        XCTAssertEqual(ipa("filho"), "fˈiʎʊ")
        XCTAssertEqual(ipa("ninho"), "nˈiɲʊ")
        XCTAssertEqual(ipa("queijo"), "kˈAʒʊ")
        XCTAssertEqual(ipa("guerra"), "ɡˈexɐ")
        XCTAssertEqual(ipa("casa"), "kˈazɐ")
        XCTAssertEqual(ipa("cidadão"), "sidadˈɐ̃ʊ̃")
        XCTAssertEqual(ipa("exame"), "ezˈɐmi")
    }

    func testCommonWordsAndClitics() {
        XCTAssertEqual(ipa("Você"), "vosˈe")
        XCTAssertEqual(ipa("de"), "ʤi")
        XCTAssertEqual(ipa("muito"), "mˈũɪ̃tʊ")
    }

    func testSentenceTokensAndNumbers() {
        let tokens = BrazilianPhonemes.phonemize("Oi, tudo bem? São 25 dias.")
        XCTAssertEqual(tokens.first, .word("ˈoɪ"))
        XCTAssertEqual(tokens[1], .punctuation(","))
        XCTAssertTrue(tokens.contains(.punctuation("?")))
        XCTAssertTrue(tokens.contains(.word(BrazilianPhonemes.word("vinte"))))
        XCTAssertEqual(tokens.last, .punctuation("."))
        XCTAssertEqual(BrazilianPhonemes.spell(1234), "mil duzentos e trinta e quatro")
        XCTAssertEqual(BrazilianPhonemes.spell(2000), "dois mil")
        XCTAssertEqual(BrazilianPhonemes.spell(100), "cem")
        XCTAssertEqual(BrazilianPhonemes.spell(1_500_000), "um milhão quinhentos mil")
    }
}

final class KokoroInputTests: XCTestCase {
    func testWordsBecomeCodesWithTheirPronunciation() {
        let input = BrazilianPhonemes.kokoroInput("Oi, a tarde está boa!")
        let codes = input.text.split(separator: " ").map(String.init)
        XCTAssertEqual(codes.count, 5)
        XCTAssertTrue(codes[0].hasSuffix(","), "punctuation stays for the pause")
        XCTAssertTrue(input.text.hasSuffix("!"))
        for code in codes.map({ $0.trimmingCharacters(in: .punctuationCharacters) }) {
            XCTAssertTrue(code.hasPrefix("qx"))
            XCTAssertTrue(code.allSatisfy { $0.isLetter && $0.isASCII && $0.isLowercase }, "letters only: \(code)")
            XCTAssertNotNil(input.pronunciations[code])
        }
        // "a" never reaches the English special case: it is a code too.
        XCTAssertEqual(input.pronunciations[codes[1]], "ɐ")
        XCTAssertEqual(input.pronunciations[codes[2]], "tˈaɾʤi")
    }

    func testSameWordSameCode() {
        XCTAssertEqual(BrazilianPhonemes.code(for: "tˈaɾʤi"), BrazilianPhonemes.code(for: "tˈaɾʤi"))
        XCTAssertNotEqual(BrazilianPhonemes.code(for: "tˈaɾʤi"), BrazilianPhonemes.code(for: "kˈazɐ"))
    }
}

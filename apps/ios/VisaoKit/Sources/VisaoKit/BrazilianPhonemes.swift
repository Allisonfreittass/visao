import Foundation

/// Brazilian Portuguese text to the phonemes the Kokoro voice "pf_dora" was trained on.
///
/// Kokoro learned pt-BR from espeak-ng (`pt-br`) through misaki's EspeakG2P, which swaps a few
/// symbols: tied d^ʒ → ʤ, t^ʃ → ʧ, a^ɪ → I, e^ɪ → A, a^ʊ → W, o^ʊ → O, ɔ^ɪ → Y, and drops the ties.
/// The dictionary inside the speech-swift package is European Portuguese ("tarde" → tˈaɾədɨ),
/// which is why the voice sounded robotic and not Brazilian. This writes the Brazilian sounds by
/// rule (no espeak, no GPL): ʤi/ʧi, final e/o as i/ʊ, final l as w, strong r as x, nasal vowels,
/// stress before the stressed vowel as espeak marks it.
public enum BrazilianPhonemes {
    /// A text as speakable tokens: words as phonemes, punctuation kept for the pauses.
    public enum Token: Equatable, Sendable {
        case word(String)
        case punctuation(String)
    }

    public static func phonemize(_ text: String) -> [Token] {
        var tokens: [Token] = []
        for piece in split(expandNumbers(text)) {
            if piece.first.map({ $0.isLetter }) == true {
                tokens.append(.word(word(piece)))
            } else if let mark = piece.first, ",.!?;:".contains(mark) {
                tokens.append(.punctuation(String(mark)))
            }
        }
        return tokens
    }

    /// The phonemes of one word.
    public static func word(_ raw: String) -> String {
        let word = raw.lowercased()
        if let known = exceptions[word] { return known }
        if let light = unstressed[word] { return light }
        return convert(word)
    }

    // MARK: Splitting

    private static func split(_ text: String) -> [String] {
        var pieces: [String] = []
        var current = ""
        for ch in text {
            if ch.isLetter || (ch == "-" && !current.isEmpty) {
                current.append(ch)
            } else {
                if !current.isEmpty { pieces.append(contentsOf: current.split(separator: "-").map(String.init)); current = "" }
                if !ch.isWhitespace { pieces.append(String(ch)) }
            }
        }
        if !current.isEmpty { pieces.append(contentsOf: current.split(separator: "-").map(String.init)) }
        return pieces
    }

    // MARK: Words that do not follow the rules, or that are common enough to get exactly right

    static let exceptions: [String: String] = [
        "você": "vosˈe", "vocês": "vosˈes", "não": "nˈɐ̃ʊ̃", "sim": "sˈĩ", "também": "tɐ̃bˈẽɪ̃",
        "muito": "mˈũɪ̃tʊ", "muita": "mˈũɪ̃tɐ", "muitos": "mˈũɪ̃tʊs", "bem": "bˈẽɪ̃", "quem": "kˈẽɪ̃",
        "está": "estˈa", "estou": "estˈo", "estão": "estˈɐ̃ʊ̃", "é": "ˈɛ", "olá": "olˈa", "oi": "ˈoɪ",
        "obrigado": "obɾiɡˈadʊ", "obrigada": "obɾiɡˈadɐ", "pode": "pˈɔʤi", "hoje": "ˈoʒi",
        "agora": "aɡˈɔɾɐ", "ele": "ˈeli", "ela": "ˈɛlɐ", "eles": "ˈelis", "elas": "ˈɛlɐs",
        "isso": "ˈisʊ", "isto": "ˈistʊ", "esse": "ˈesi", "essa": "ˈɛsɐ", "este": "ˈesʧi",
        "esta": "ˈɛstɐ", "aquele": "akˈeli", "aquela": "akˈɛlɐ", "gente": "ʒˈẽʧi",
        "noite": "nˈoɪʧi", "tarde": "tˈaɾʤi", "cidade": "sidˈaʤi", "verdade": "veɾdˈaʤi",
        "porque": "poɾkˈe", "por": "poɾ", "para": "pˈaɾɐ", "pra": "pɾɐ", "tudo": "tˈudʊ",
        "coisa": "kˈoɪzɐ", "coisas": "kˈoɪzɐs", "mais": "mˈIs", "mas": "mˈas", "depois": "depˈoɪs",
        "nós": "nˈɔs", "vou": "vˈo", "vai": "vˈI", "vamos": "vˈɐ̃mʊs", "foi": "fˈoɪ", "sou": "sˈo",
        "tem": "tˈẽɪ̃", "têm": "tˈẽɪ̃ẽɪ̃", "bom": "bˈõ", "boa": "bˈoɐ", "dia": "ʤˈiɐ", "dias": "ʤˈiɐs",
        "ontem": "ˈõtẽɪ̃", "sempre": "sˈẽpɾi", "nunca": "nˈũkɐ", "nada": "nˈadɐ", "onde": "ˈõʤi",
        "quando": "kwˈɐ̃dʊ", "como": "kˈomʊ", "quanto": "kwˈɐ̃tʊ", "qual": "kwˈaw", "quais": "kwˈIs",
        "aqui": "akˈi", "ali": "alˈi", "lá": "lˈa", "já": "ʒˈa", "só": "sˈɔ", "ainda": "aˈĩdɐ",
        "então": "ẽtˈɐ̃ʊ̃", "assim": "asˈĩ", "mesmo": "mˈezmʊ", "melhor": "meʎˈɔɾ", "pior": "piˈɔɾ",
        "senhor": "seɲˈoɾ", "senhora": "seɲˈɔɾɐ", "homem": "ˈɔmẽɪ̃", "mulher": "muʎˈɛɾ",
        "tchau": "ʧˈW", "beleza": "belˈezɐ", "certo": "sˈɛɾtʊ", "certeza": "seɾtˈezɐ",
        "hora": "ˈɔɾɐ", "horas": "ˈɔɾɐs", "nova": "nˈɔvɐ", "novo": "nˈovʊ", "nossa": "nˈɔsɐ",
        "nosso": "nˈɔsʊ", "pessoa": "pesˈoɐ", "pessoas": "pesˈoɐs", "email": "imˈeɪw",
        "mac": "mˈɛk", "google": "ɡˈuɡow", "visão": "vizˈɐ̃ʊ̃", "brasil": "bɾazˈiw",
        "deus": "dˈeʊs", "seu": "sˈeʊ", "sua": "sˈuɐ", "meu": "mˈeʊ", "minha": "mˈĩɲɐ",
        "eu": "ˈeʊ", "ter": "tˈeɾ", "ser": "sˈeɾ", "fazer": "fazˈeɾ", "dizer": "ʤizˈeɾ",
        "quero": "kˈɛɾʊ", "quer": "kˈɛɾ", "precisa": "pɾesˈizɐ", "preciso": "pɾesˈizʊ",
    ]

    /// Clitics and function words: no stress of their own.
    static let unstressed: [String: String] = [
        "o": "ʊ", "a": "ɐ", "os": "ʊs", "as": "ɐs", "e": "i", "de": "ʤi", "do": "dʊ", "da": "dɐ",
        "dos": "dʊs", "das": "dɐs", "em": "ẽɪ̃", "no": "nʊ", "na": "nɐ", "nos": "nʊs", "nas": "nɐs",
        "um": "ũ", "uma": "ˈumɐ", "que": "ki", "se": "si", "me": "mi", "te": "ʧi", "lhe": "ʎi",
        "com": "kõ", "sem": "sẽɪ̃", "ao": "ˈaʊ", "aos": "ˈaʊs", "à": "a", "às": "as", "ou": "o",
        "nem": "nẽɪ̃", "num": "nũ", "numa": "nˈumɐ", "pelo": "pˈelʊ", "pela": "pˈelɐ",
    ]

    // MARK: Rules

    private static let vowels: Set<Character> = ["a", "e", "i", "o", "u", "á", "é", "í", "ó", "ú", "â", "ê", "ô", "ã", "õ", "à", "ü"]
    private static let accented: Set<Character> = ["á", "é", "í", "ó", "ú", "â", "ê", "ô"]

    /// A vowel nucleus of the word: where it starts and ends in the letters.
    private struct Nucleus { let start: Int; let end: Int }

    private static func convert(_ word: String) -> String {
        let letters = Array(word)
        let nuclei = findNuclei(letters)
        guard !nuclei.isEmpty else { return word }
        let stressed = stressIndex(letters, nuclei: nuclei)

        var out = ""
        var i = 0
        var nucleusIndex = 0
        while i < letters.count {
            if nucleusIndex < nuclei.count, nuclei[nucleusIndex].start == i {
                let n = nuclei[nucleusIndex]
                let isStressed = nucleusIndex == stressed
                let isLast = nucleusIndex == nuclei.count - 1
                let piece = String(letters[n.start...n.end])
                let next = n.end + 1 < letters.count ? letters[n.end + 1] : nil
                let afterNext = n.end + 2 < letters.count ? letters[n.end + 2] : nil
                // A vowel before m/n that closes the syllable is nasal ("campo", "tempo", "fim").
                let nasalCoda = (next == "m" || next == "n") && (afterNext == nil || !(vowels.contains(afterNext!) || afterNext == "h"))
                if isStressed { out += "ˈ" }
                out += vowel(piece, stressed: isStressed, final: isLast && isFinalSyllableOpen(letters, from: n.end),
                             nasal: nasalCoda, beforeNasalOnset: next == "m" || next == "n")
                if nasalCoda {
                    // The m/n only colours the vowel; at the end, -am/-em are diphthongs.
                    if afterNext == nil {
                        if piece == "a" || piece == "á" { out += next == "m" ? "ʊ̃" : "" }
                        if piece == "e" || piece == "é" || piece == "ê" { out += "ɪ̃" }
                    }
                    i = n.end + 2
                    if afterNext == "s" && n.end + 3 == letters.count { out += "s"; i += 1 }
                } else {
                    i = n.end + 1
                }
                nucleusIndex += 1
                continue
            }
            out += consonant(letters, at: i, skip: &i)
        }
        return out
    }

    /// True when nothing but s (or nothing) follows the last vowel: "casa", "casas", "carro".
    private static func isFinalSyllableOpen(_ letters: [Character], from end: Int) -> Bool {
        let rest = letters.count - 1 - end
        return rest == 0 || (rest == 1 && letters.last == "s")
    }

    private static func findNuclei(_ letters: [Character]) -> [Nucleus] {
        var nuclei: [Nucleus] = []
        var i = 0
        while i < letters.count {
            let ch = letters[i]
            // The u of "que/qui/gue/gui" is silent: part of the consonant.
            if ch == "u", i > 0, letters[i - 1] == "q" || letters[i - 1] == "g",
               i + 1 < letters.count, "eiéíêe".contains(letters[i + 1]) {
                i += 1
                continue
            }
            guard vowels.contains(ch) else { i += 1; continue }
            var end = i
            if i + 1 < letters.count {
                let pair = String(letters[i...i + 1])
                let diphthongs = ["ai", "ei", "oi", "ui", "au", "eu", "ou", "iu", "ão", "ãe", "õe", "éi", "ói", "éu", "ái"]
                // A falling diphthong, unless the second vowel carries the stress or starts a syllable.
                if diphthongs.contains(pair), !(i + 2 < letters.count && (letters[i + 2] == "m" || letters[i + 2] == "n") && pair.last == "i") {
                    end = i + 1
                }
            }
            nuclei.append(Nucleus(start: i, end: end))
            i = end + 1
        }
        return nuclei
    }

    private static func stressIndex(_ letters: [Character], nuclei: [Nucleus]) -> Int {
        if nuclei.count == 1 { return 0 }
        for (index, n) in nuclei.enumerated() where letters[n.start...n.end].contains(where: { accented.contains($0) }) {
            return index
        }
        for (index, n) in nuclei.enumerated() where letters[n.start...n.end].contains(where: { $0 == "ã" || $0 == "õ" }) {
            return index
        }
        let word = String(letters)
        let oxytone = ["r", "l", "z", "x", "i", "u", "im", "um", "is", "us", "ins", "uns", "om", "ons", "ps"]
        if oxytone.contains(where: { word.hasSuffix($0) }) { return nuclei.count - 1 }
        return nuclei.count - 2
    }

    private static func vowel(_ piece: String, stressed: Bool, final: Bool, nasal: Bool, beforeNasalOnset: Bool) -> String {
        switch piece {
        case "ão": return "ɐ̃ʊ̃"
        case "ãe": return "ɐ̃ɪ̃"
        case "õe": return "õɪ̃"
        case "ai", "ái": return "I"
        case "ei", "éi": return piece == "éi" ? "ɛɪ" : "A"
        case "oi": return "oɪ"
        case "ói": return "ɔɪ"
        case "ui": return "uɪ"
        case "au": return "W"
        case "eu": return "eʊ"
        case "éu": return "ɛʊ"
        case "ou": return "o"
        case "iu": return "iʊ"
        default: break
        }
        let base: String
        switch piece.first! {
        case "á", "à": base = "a"
        case "â": base = "ɐ"
        case "ã": base = "ɐ̃"
        case "é": base = "ɛ"
        case "ê": base = "e"
        case "í": base = "i"
        case "ó": base = "ɔ"
        case "ô": base = "o"
        case "õ": base = "õ"
        case "ú": base = "u"
        // Open a, except at the end of the word and before m/n ("casa", "cama", "janela").
        case "a": base = (final && !stressed) || beforeNasalOnset ? "ɐ" : "a"
        case "e": base = !stressed && final ? "i" : "e"
        case "o": base = !stressed && final ? "ʊ" : "o"
        case "i": base = "i"
        case "u", "ü": base = "u"
        default: base = String(piece.first!)
        }
        guard nasal else { return base }
        switch base {
        case "a", "ɐ": return "ɐ̃"
        case "e", "ɛ": return "ẽ"
        case "i": return "ĩ"
        case "o", "ɔ": return "õ"
        case "u": return "ũ"
        default: return base
        }
    }

    private static func consonant(_ letters: [Character], at i: Int, skip index: inout Int) -> String {
        let ch = letters[i]
        let next = i + 1 < letters.count ? letters[i + 1] : nil
        let previous = i > 0 ? letters[i - 1] : nil
        let isVowel: (Character?) -> Bool = { $0.map { vowels.contains($0) } ?? false }
        // A t or d before the sound "i" (written i, or a final unstressed e) is ʧ / ʤ.
        let soundsI: Bool = {
            guard let next else { return false }
            if next == "i" || next == "í" { return true }
            if next == "e" {
                let rest = letters.count - (i + 2)
                return rest == 0 || (rest == 1 && letters.last == "s")
            }
            return false
        }()
        index = i + 1
        switch ch {
        case "c":
            if next == "h" { index = i + 2; return "ʃ" }
            if let next, "eiéíê".contains(next) { return "s" }
            return "k"
        case "ç": return "s"
        case "q": return "k"
        case "g":
            if let next, "eiéíê".contains(next) { return "ʒ" }
            return "ɡ"
        case "j": return "ʒ"
        case "h": return ""
        case "l":
            if next == "h" { index = i + 2; return "ʎ" }
            return isVowel(next) ? "l" : "w"
        case "n":
            if next == "h" { index = i + 2; return "ɲ" }
            return "n"
        case "r":
            if next == "r" { index = i + 2; return "x" }
            if previous == nil || previous == "n" || previous == "l" || previous == "s" { return "x" }
            if next == nil { return "x" }
            return "ɾ"
        case "s":
            if next == "s" { index = i + 2; return "s" }
            if next == "c", let after = i + 2 < letters.count ? letters[i + 2] : nil, "eiéí".contains(after) {
                index = i + 2
                return "s"
            }
            if isVowel(previous) && isVowel(next) { return "z" }
            return "s"
        case "x":
            if previous == "e" && i == 1 && isVowel(next) { return "z" }
            return "ʃ"
        case "z": return next == nil ? "s" : "z"
        case "t": return soundsI ? "ʧ" : "t"
        case "d": return soundsI ? "ʤ" : "d"
        case "u": return ""   // the silent u of que/qui/gue/gui
        case "w": return "w"
        case "y": return "i"
        case "k": return "k"
        default: return String(ch)
        }
    }

    // MARK: Numbers, read in Portuguese

    static func expandNumbers(_ text: String) -> String {
        var out = ""
        var digits = ""
        for ch in text {
            if ch.isNumber, ch.isASCII {
                digits.append(ch)
            } else {
                if !digits.isEmpty { out += spell(Int(digits) ?? 0); digits = "" }
                out.append(ch)
            }
        }
        if !digits.isEmpty { out += spell(Int(digits) ?? 0) }
        return out
    }

    static func spell(_ n: Int) -> String {
        let units = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
                     "onze", "doze", "treze", "catorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
        let tens = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
        let hundreds = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos", "oitocentos", "novecentos"]
        if n < 20 { return units[n] }
        if n < 100 { return tens[n / 10] + (n % 10 == 0 ? "" : " e " + units[n % 10]) }
        if n == 100 { return "cem" }
        if n < 1000 { return hundreds[n / 100] + (n % 100 == 0 ? "" : " e " + spell(n % 100)) }
        if n < 1_000_000 {
            let thousands = n / 1000
            let rest = n % 1000
            let head = thousands == 1 ? "mil" : spell(thousands) + " mil"
            if rest == 0 { return head }
            return head + (rest < 100 || rest % 100 == 0 ? " e " : " ") + spell(rest)
        }
        let millions = n / 1_000_000
        let rest = n % 1_000_000
        let head = millions == 1 ? "um milhão" : spell(millions) + " milhões"
        return rest == 0 ? head : head + " " + spell(rest)
    }
}

extension BrazilianPhonemes {
    /// What Kokoro is given: each word replaced by a neutral code ("qx…", letters only, never a
    /// real word nor one of its English special cases like "a" or "i"), and the table that tells
    /// it how each code is said. Its public pronunciation hook only works on the English path,
    /// which looks each code up and passes the Brazilian phonemes through untouched.
    public static func kokoroInput(_ text: String) -> (text: String, pronunciations: [String: String]) {
        var words: [String] = []
        var table: [String: String] = [:]
        for token in phonemize(text) {
            switch token {
            case .word(let ipa):
                let code = code(for: ipa)
                table[code] = ipa
                words.append(code)
            case .punctuation(let mark):
                if words.isEmpty { continue }
                words[words.count - 1] += mark
            }
        }
        return (words.joined(separator: " "), table)
    }

    /// A stable code for a pronunciation: "qx" and the FNV-1a hash in letters.
    static func code(for ipa: String) -> String {
        var hash: UInt64 = 0xcbf29ce484222325
        for byte in ipa.utf8 {
            hash ^= UInt64(byte)
            hash = hash &* 0x100000001b3
        }
        var letters = "qx"
        for _ in 0..<8 {
            letters.append(Character(UnicodeScalar(UInt8(97 + hash % 26))))
            hash /= 26
        }
        return letters
    }
}

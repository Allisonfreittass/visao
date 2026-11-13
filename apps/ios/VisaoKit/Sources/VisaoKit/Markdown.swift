import Foundation

/// The small Markdown subset the replies use, as apps/web/src/components/MessageContent.tsx reads
/// it: code fences (an unclosed one still renders as code), lists, headings and paragraphs.
public enum MarkdownBlock: Equatable, Sendable {
    case paragraph(String)
    case heading(String)
    case bullets([String])
    case numbered([String])
    case code(language: String, code: String)
}

public enum Markdown {
    public static func blocks(_ text: String) -> [MarkdownBlock] {
        var result: [MarkdownBlock] = []
        var prose: [String] = []
        var fence: (language: String, lines: [String])?

        func flushProse() {
            result += proseBlocks(prose.joined(separator: "\n"))
            prose = []
        }

        for line in text.components(separatedBy: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if var open = fence {
                if trimmed.hasPrefix("```") {
                    result.append(.code(language: open.language, code: open.lines.joined(separator: "\n")))
                    fence = nil
                } else {
                    open.lines.append(line)
                    fence = open
                }
            } else if trimmed.hasPrefix("```") {
                flushProse()
                let language = trimmed.dropFirst(3).trimmingCharacters(in: .whitespaces).lowercased()
                fence = (language, [])
            } else {
                prose.append(line)
            }
        }
        if let open = fence {
            result.append(.code(language: open.language, code: open.lines.joined(separator: "\n")))
        }
        flushProse()
        return result
    }

    private static func proseBlocks(_ text: String) -> [MarkdownBlock] {
        // Blocks are separated by blank lines.
        var groups: [[String]] = [[]]
        for line in text.components(separatedBy: "\n") {
            if line.trimmingCharacters(in: .whitespaces).isEmpty {
                if !(groups.last?.isEmpty ?? true) { groups.append([]) }
            } else {
                groups[groups.count - 1].append(line)
            }
        }
        return groups.filter { !$0.isEmpty }.map { lines in
            if lines.allSatisfy({ bullet($0) != nil }) { return .bullets(lines.compactMap(bullet)) }
            if lines.allSatisfy({ numbered($0) != nil }) { return .numbered(lines.compactMap(numbered)) }
            if let first = lines.first, let heading = heading(first) {
                return .heading(([heading] + lines.dropFirst()).joined(separator: "\n"))
            }
            return .paragraph(lines.joined(separator: "\n"))
        }
    }

    private static func bullet(_ line: String) -> String? {
        strip(line, pattern: #"^\s*[-*]\s+"#)
    }

    private static func numbered(_ line: String) -> String? {
        strip(line, pattern: #"^\s*\d+\.\s+"#)
    }

    private static func heading(_ line: String) -> String? {
        strip(line, pattern: #"^#{1,6}\s+"#)
    }

    private static func strip(_ line: String, pattern: String) -> String? {
        guard let range = line.range(of: pattern, options: .regularExpression) else { return nil }
        return String(line[range.upperBound...])
    }

    /// Bold, italics, `code` and links, with whitespace kept. HTML stays text, and a link only
    /// survives as a link if it is http or https (no javascript:, file:, tel: tricks).
    public static func inline(_ text: String) -> AttributedString {
        let options = AttributedString.MarkdownParsingOptions(
            allowsExtendedAttributes: false,
            interpretedSyntax: .inlineOnlyPreservingWhitespace,
            failurePolicy: .returnPartiallyParsedIfPossible
        )
        guard var attributed = try? AttributedString(markdown: text, options: options) else {
            return AttributedString(text)
        }
        for run in attributed.runs {
            guard let url = run.link else { continue }
            let scheme = url.scheme?.lowercased()
            if scheme != "http" && scheme != "https" { attributed[run.range].link = nil }
        }
        return attributed
    }
}

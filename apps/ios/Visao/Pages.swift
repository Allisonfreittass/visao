import SwiftUI
import VisaoKit

/// A place of the web other than the chat (.page in ceu.css): one glass sheet over the forest,
/// a label, a big serif title with its italic half, a lede, a line, then the body.
struct GlassPage<Body: View>: View {
    let label: String
    let title: String
    let italic: String
    var lede: String?
    @ViewBuilder let content: Body
    @Environment(\.palette) private var palette

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                VStack(alignment: .leading, spacing: 8) {
                    Rotulo(label)
                    (Text(title).font(Typo.display(40, relativeTo: .largeTitle))
                        + Text(italic).font(Typo.display(40, relativeTo: .largeTitle, italic: true)).foregroundColor(palette.tintaSuave))
                        .accessibilityAddTraits(.isHeader)
                    if let lede {
                        Text(lede)
                            .font(Typo.text(.callout))
                            .foregroundStyle(palette.tintaSuave)
                    }
                }
                .padding(.bottom, 16)
                Rectangle().fill(palette.linha).frame(height: 1)
                VStack(alignment: .leading, spacing: 28) {
                    content
                }
                .padding(.top, 20)
                .padding(.bottom, 8)
            }
            .padding(.horizontal, 18)
            .padding(.top, 22)
            .padding(.bottom, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .glass(palette, cornerRadius: 26)
            .padding(.horizontal, 10)
            .padding(.top, 6)
            .padding(.bottom, 12)
            .frame(maxWidth: 760)
            .frame(maxWidth: .infinity)
        }
        .scrollIndicators(.hidden)
    }
}

/// A group inside a page: its label, then rows separated by thin lines (.list-group).
struct PageGroup<Content: View>: View {
    let label: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Rotulo(label).padding(.bottom, 8)
            content
        }
    }
}

/// One line with a thin line above (.list-item / .setting).
struct PageRow<Content: View>: View {
    @ViewBuilder let content: Content
    @Environment(\.palette) private var palette

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Rectangle().fill(palette.linha).frame(height: 1)
            content.padding(.vertical, 16)
        }
    }
}

/// A setting: what it is, one sentence on what it does, and the web's switch.
struct SettingRow: View {
    let title: String
    let description: String
    @Binding var isOn: Bool
    var disabled = false
    @Environment(\.palette) private var palette

    var body: some View {
        PageRow {
            Toggle(isOn: $isOn) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(title).font(Typo.text(.subheadline, weight: .medium))
                    Text(description)
                        .font(Typo.text(.footnote))
                        .foregroundStyle(palette.tintaSuave)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .toggleStyle(VisaoSwitch())
            .disabled(disabled)
            .opacity(disabled ? 0.45 : 1)
        }
    }
}

/// The switch of the web (.switch): a small pill, tin when on.
struct VisaoSwitch: ToggleStyle {
    @Environment(\.palette) private var palette

    func makeBody(configuration: Configuration) -> some View {
        HStack(alignment: .center, spacing: 20) {
            configuration.label
            Spacer(minLength: 0)
            Capsule()
                .fill(configuration.isOn ? palette.estanho : palette.fundoHover)
                .overlay(Capsule().strokeBorder(configuration.isOn ? palette.estanho : palette.tintaFraca.opacity(0.6)))
                .frame(width: 46, height: 28)
                .overlay(alignment: configuration.isOn ? .trailing : .leading) {
                    Circle()
                        .fill(configuration.isOn ? palette.pilulaAtivaTinta : palette.tintaFraca)
                        .frame(width: 20, height: 20)
                        .padding(4)
                }
                .animation(.easeOut(duration: 0.18), value: configuration.isOn)
        }
        .contentShape(Rectangle())
        .onTapGesture { configuration.isOn.toggle() }
        .sensoryFeedback(.selection, trigger: configuration.isOn)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isToggle)
        .accessibilityValue(configuration.isOn ? "ligado" : "desligado")
        .accessibilityAction { configuration.isOn.toggle() }
    }
}

/// The web's buttons: the dark pill for the main action, the outlined ghost for the rest.
struct PillButton: View {
    let title: String
    var primary = false
    var busy = false
    let action: () -> Void
    @Environment(\.palette) private var palette
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Button(action: action) {
            Group {
                if busy { ProgressView().tint(primary ? palette.pilulaAtivaTinta : palette.tinta) } else { Text(title) }
            }
            .font(Typo.text(.subheadline, weight: .medium))
            .foregroundStyle(primary ? palette.pilulaAtivaTinta : palette.tinta)
            .padding(.horizontal, 16)
            .frame(minHeight: 40)
            .background(primary ? palette.pilulaAtiva : .clear, in: Capsule())
            .overlay(Capsule().strokeBorder(primary ? .clear : palette.linhaForte))
            .frame(minHeight: 44)
            .contentShape(Rectangle())
            .opacity(isEnabled ? 1 : 0.45)
        }
        .buttonStyle(.plain)
    }
}

/// A rounded text field on the page (.projects-new input).
struct PageField: View {
    let placeholder: String
    @Binding var text: String
    var onSubmit: () -> Void = {}
    @Environment(\.palette) private var palette

    var body: some View {
        TextField(placeholder, text: $text)
            .font(Typo.text(.subheadline))
            .submitLabel(.done)
            .onSubmit(onSubmit)
            .padding(.horizontal, 16)
            .frame(minHeight: 44)
            .background(palette.fundoElevado, in: Capsule())
            .overlay(Capsule().strokeBorder(palette.linhaForte))
    }
}

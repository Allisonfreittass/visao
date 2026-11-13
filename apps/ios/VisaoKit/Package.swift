// swift-tools-version: 6.0
// O que o app do iPhone usa e dá para testar sem simulador: `swift test` nesta pasta.
import PackageDescription

let package = Package(
    name: "VisaoKit",
    defaultLocalization: "pt-BR",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "VisaoKit", targets: ["VisaoKit"]),
    ],
    targets: [
        .target(name: "VisaoKit"),
        .testTarget(name: "VisaoKitTests", dependencies: ["VisaoKit"]),
    ]
)

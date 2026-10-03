// swift-tools-version:5.9
// Oracle driver for NFCPassportReader (iOS only). The test target runs in the iOS Simulator and
// talks to the harness chips through tools/chip_broker.py on the macOS host.
import PackageDescription

let package = Package(
    name: "NFCPassportReaderOracle",
    platforms: [.iOS("15.0")],
    dependencies: [
        // Pinned checkout with nfcpassportreader-test-visibility.patch applied (scripts/bootstrap-ios.sh).
        .package(path: "../../../_vendor/NFCPassportReader"),
    ],
    targets: [
        .target(name: "OracleSupport", path: "Sources/OracleSupport"),
        .testTarget(
            name: "NFCPassportReaderOracleTests",
            dependencies: [
                "OracleSupport",
                .product(name: "NFCPassportReader", package: "NFCPassportReader"),
            ],
            path: "Tests/NFCPassportReaderOracleTests"
        ),
    ]
)

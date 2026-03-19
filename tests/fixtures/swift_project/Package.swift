// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "TestSwiftApp",
    targets: [
        .executableTarget(name: "App"),
        .target(name: "Models"),
        .testTarget(name: "AppTests"),
    ]
)

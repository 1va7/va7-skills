import Foundation
import AVFoundation
import CoreImage
import ImageIO
import UniformTypeIdentifiers

func fail(_ message: String) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
    exit(1)
}

let args = CommandLine.arguments
guard args.count >= 4 else {
    fail("usage: swift extract_avfoundation_frame.swift SOURCE seconds OUTPUT [width]")
}

let src = URL(fileURLWithPath: args[1])
guard let seconds = Double(args[2]) else {
    fail("invalid seconds: \(args[2])")
}
let out = URL(fileURLWithPath: args[3])
let width = args.count >= 5 ? (Double(args[4]) ?? 0) : 0

let asset = AVURLAsset(url: src)
let generator = AVAssetImageGenerator(asset: asset)
generator.appliesPreferredTrackTransform = true
generator.requestedTimeToleranceBefore = CMTime(seconds: 0.02, preferredTimescale: 600)
generator.requestedTimeToleranceAfter = CMTime(seconds: 0.02, preferredTimescale: 600)
if width > 0 {
    generator.maximumSize = CGSize(width: width, height: width * 2.0)
}

let requested = CMTime(seconds: seconds, preferredTimescale: 600)
var actual = CMTime.zero
let sourceImage: CGImage
do {
    sourceImage = try generator.copyCGImage(at: requested, actualTime: &actual)
} catch {
    fail("AVAssetImageGenerator failed: \(error)")
}

let sRGB = CGColorSpace(name: CGColorSpace.sRGB)!
let ciImage = CIImage(cgImage: sourceImage)
let context = CIContext(options: [
    .workingColorSpace: sRGB,
    .outputColorSpace: sRGB
])
guard let outputImage = context.createCGImage(ciImage, from: ciImage.extent, format: .RGBA8, colorSpace: sRGB) else {
    fail("failed to create sRGB CGImage")
}

try? FileManager.default.createDirectory(at: out.deletingLastPathComponent(), withIntermediateDirectories: true)
guard let destination = CGImageDestinationCreateWithURL(out as CFURL, UTType.jpeg.identifier as CFString, 1, nil) else {
    fail("failed to create image destination")
}
let properties: [CFString: Any] = [
    kCGImageDestinationLossyCompressionQuality: 0.95,
    kCGImagePropertyColorModel: kCGImagePropertyColorModelRGB,
    kCGImagePropertyProfileName: "sRGB IEC61966-2.1"
]
CGImageDestinationAddImage(destination, outputImage, properties as CFDictionary)
guard CGImageDestinationFinalize(destination) else {
    fail("failed to write \(out.path)")
}

let actualSeconds = CMTimeGetSeconds(actual)
print("{\"requested\":\(seconds),\"actual\":\(actualSeconds),\"width\":\(outputImage.width),\"height\":\(outputImage.height)}")

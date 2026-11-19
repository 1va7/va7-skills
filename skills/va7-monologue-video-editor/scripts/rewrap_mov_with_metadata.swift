import Foundation
import AVFoundation

enum RewrapError: Error {
    case missingVideoTrack
    case exportSessionUnavailable
}

@main
struct Runner {
    static func main() async {
        do {
            let args = CommandLine.arguments
            guard args.count == 4 else {
                fputs("usage: rewrap_mov_with_metadata.swift <metadata_source.mov> <edited.mov> <output.mov>\n", stderr)
                exit(2)
            }

            let sourceURL = URL(fileURLWithPath: args[1])
            let editedURL = URL(fileURLWithPath: args[2])
            let outputURL = URL(fileURLWithPath: args[3])

            try? FileManager.default.removeItem(at: outputURL)

            let source = AVURLAsset(url: sourceURL)
            let edited = AVURLAsset(url: editedURL)
            let composition = AVMutableComposition()

            let editedDuration = try await edited.load(.duration)
            let fullRange = CMTimeRange(start: .zero, duration: editedDuration)

            let editedVideoTracks = try await edited.loadTracks(withMediaType: .video)
            guard let editedVideo = editedVideoTracks.first else {
                throw RewrapError.missingVideoTrack
            }
            let compositionVideo = composition.addMutableTrack(
                withMediaType: .video,
                preferredTrackID: kCMPersistentTrackID_Invalid
            )!
            try compositionVideo.insertTimeRange(fullRange, of: editedVideo, at: .zero)
            compositionVideo.preferredTransform = try await editedVideo.load(.preferredTransform)

            let editedAudioTracks = try await edited.loadTracks(withMediaType: .audio)
            for editedAudio in editedAudioTracks {
                let compositionAudio = composition.addMutableTrack(
                    withMediaType: .audio,
                    preferredTrackID: kCMPersistentTrackID_Invalid
                )!
                try compositionAudio.insertTimeRange(fullRange, of: editedAudio, at: .zero)
            }

            let metadataTracks = try await source.loadTracks(withMediaType: .metadata)
            for metadataTrack in metadataTracks {
                let compositionMetadata = composition.addMutableTrack(
                    withMediaType: .metadata,
                    preferredTrackID: kCMPersistentTrackID_Invalid
                )!
                let metadataRange = try await metadataTrack.load(.timeRange)
                let copyDuration = CMTimeMinimum(metadataRange.duration, editedDuration)
                let copyRange = CMTimeRange(start: .zero, duration: copyDuration)
                try compositionMetadata.insertTimeRange(copyRange, of: metadataTrack, at: .zero)
            }

            guard let exporter = AVAssetExportSession(
                asset: composition,
                presetName: AVAssetExportPresetPassthrough
            ) else {
                throw RewrapError.exportSessionUnavailable
            }

            exporter.metadata = try await source.load(.metadata)
            exporter.outputURL = outputURL
            exporter.outputFileType = .mov
            exporter.shouldOptimizeForNetworkUse = false

            try await exporter.export(to: outputURL, as: .mov)
        } catch {
            fputs("error: \(error)\n", stderr)
            exit(1)
        }
    }
}

import AVFoundation
import CoreImage
import SwiftUI
import UIKit
import UniformTypeIdentifiers

/// The camera in a call (as in Grok's voice mode): while it is on, what it sees goes with each
/// sentence you say, so you can point it and ask "o que é isso?". Video only, no audio, and it
/// never touches the call's audio session. On only by its button, only during the call.
final class CallCamera: NSObject, @unchecked Sendable {
    let session = AVCaptureSession()
    private let queue = DispatchQueue(label: "visao.camera")
    private let output = AVCaptureVideoDataOutput()
    private let lock = NSLock()
    private var latest: CVPixelBuffer?
    private var input: AVCaptureDeviceInput?
    private let context = CIContext()

    private(set) var position: AVCaptureDevice.Position = .back

    /// Asks for the camera once; false when refused.
    static func requestAccess() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: return true
        case .notDetermined: return await AVCaptureDevice.requestAccess(for: .video)
        default: return false
        }
    }

    func start() throws {
        // The call owns the audio session; the camera must not reconfigure it.
        session.automaticallyConfiguresApplicationAudioSession = false
        session.beginConfiguration()
        session.sessionPreset = .hd1280x720
        try attachCamera(.back)
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
        output.alwaysDiscardsLateVideoFrames = true
        output.setSampleBufferDelegate(self, queue: queue)
        if session.canAddOutput(output) { session.addOutput(output) }
        session.commitConfiguration()
        queue.async { [session] in session.startRunning() }
    }

    func stop() {
        queue.async { [session] in session.stopRunning() }
        lock.withLock { latest = nil }
    }

    /// Back ⇄ front.
    func flip() {
        let next: AVCaptureDevice.Position = position == .back ? .front : .back
        session.beginConfiguration()
        try? attachCamera(next)
        session.commitConfiguration()
    }

    private func attachCamera(_ position: AVCaptureDevice.Position) throws {
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: position) else {
            throw CameraError.unavailable
        }
        let newInput = try AVCaptureDeviceInput(device: device)
        if let input { session.removeInput(input) }
        guard session.canAddInput(newInput) else { throw CameraError.unavailable }
        session.addInput(newInput)
        input = newInput
        self.position = position
        if let connection = output.connection(with: .video) {
            if connection.isVideoRotationAngleSupported(90) { connection.videoRotationAngle = 90 }
            connection.isVideoMirrored = position == .front
        }
    }

    /// What the camera shows right now, as a JPEG (the long side up to 1568 px, as the photos
    /// the chat sends).
    func snapshot() -> Data? {
        guard let buffer = lock.withLock({ latest }) else { return nil }
        var image = CIImage(cvPixelBuffer: buffer)
        let long = max(image.extent.width, image.extent.height)
        if long > 1568 {
            let scale = 1568 / long
            image = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        }
        guard let cg = context.createCGImage(image, from: image.extent) else { return nil }
        return UIImage(cgImage: cg).jpegData(compressionQuality: 0.85)
    }
}

extension CallCamera: AVCaptureVideoDataOutputSampleBufferDelegate {
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard let buffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        lock.withLock { latest = buffer }
    }
}

enum CameraError: LocalizedError {
    case unavailable, denied
    var errorDescription: String? {
        switch self {
        case .unavailable: "A câmera não está disponível agora."
        case .denied: "Para ele ver pela câmera, permita a câmera em Ajustes do iPhone."
        }
    }
}

/// The live picture of the call's camera.
struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> PreviewView {
        let view = PreviewView()
        view.previewLayer.session = session
        view.previewLayer.videoGravity = .resizeAspectFill
        return view
    }

    func updateUIView(_ view: PreviewView, context: Context) {}

    final class PreviewView: UIView {
        override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
        var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }

        /// Upright in portrait: the preview has its own rotation, apart from the photo's.
        override func layoutSubviews() {
            super.layoutSubviews()
            if let connection = previewLayer.connection, connection.isVideoRotationAngleSupported(90) {
                connection.videoRotationAngle = 90
            }
        }
    }
}

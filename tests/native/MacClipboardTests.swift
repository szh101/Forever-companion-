import AppKit
import Foundation

@main struct MacClipboardTests {
    enum TestFailure: Error { case pasteboardUnavailable }
    static func main() throws {
        // Exercise AppKit with an isolated pasteboard. Never read or overwrite
        // the user's general clipboard, capture a window, or activate an app.
        let board = NSPasteboard.withUniqueName()
        defer { board.releaseGlobally() }
        guard board.setString("synthetic sentinel", forType: .string) else {
            throw TestFailure.pasteboardUnavailable
        }
        for invalid in [Data(), Data("not a PNG".utf8)] {
            do {
                try copyPNG(invalid, to: board)
                fatalError("Invalid data was accepted")
            } catch ClipboardError.invalidImage {}
            precondition(board.string(forType: .string) == "synthetic sentinel")
        }
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 240, pixelsHigh: 160,
            bitsPerSample: 8, samplesPerPixel: 3, hasAlpha: false, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        bitmap.bitmapData!.initialize(repeating: 100, count: bitmap.bytesPerRow * bitmap.pixelsHigh)
        let png = bitmap.representation(using: .png, properties: [:])!
        try copyPNG(png, to: board)
        precondition(board.data(forType: .png) == png)
        precondition(board.string(forType: .string) == nil)
        precondition(NSBitmapImageRep(data: board.data(forType: .png)!)?.pixelsWide == 240)
        print("PASS: native PNG clipboard round trip and invalid-input preservation on a private pasteboard")
    }
}

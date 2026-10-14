import AppKit
import CoreGraphics
import Foundation
import ImageIO
import ScreenCaptureKit
import UniformTypeIdentifiers

// Fixed allowlist shared with companion/mac_capture.py. Titles never grant access.
let wowNames: Set<String> = ["world of warcraft", "world of warcraft classic",
    "world of warcraft beta", "wow", "wowb", "wowt", "wowclassic", "wowclassicb", "wowforever"]

struct WindowInfo: Codable {
    let id: UInt32
    let pid: Int32
    let executable: String
    let title: String
}

func sendJSON<T: Encodable>(_ value: T) throws {
    FileHandle.standardOutput.write(try JSONEncoder().encode(value))
}

func fail(_ code: String) -> Never {
    let data = try! JSONEncoder().encode(["error": code])
    FileHandle.standardError.write(data)
    exit(1)
}

func executableName(_ pid: Int32) -> String? {
    NSRunningApplication(processIdentifier: pid)?.executableURL?.lastPathComponent
}

// Metadata only. Does not request Screen Recording or activate any application.
func listWindows() -> [WindowInfo] {
    guard let info = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements],
                                               kCGNullWindowID) as? [[String: Any]] else { return [] }
    return info.compactMap { row in
        guard let id = row[kCGWindowNumber as String] as? UInt32,
              let pid = row[kCGWindowOwnerPID as String] as? Int32,
              let layer = row[kCGWindowLayer as String] as? Int, layer == 0,
              let executable = executableName(pid), wowNames.contains(executable.lowercased())
        else { return nil }
        return WindowInfo(id: id, pid: pid, executable: executable,
                          title: row[kCGWindowName as String] as? String ?? "World of Warcraft")
    }
}

@available(macOS 14.0, *)
func capture(_ id: UInt32, _ pid: Int32, _ executable: String) async throws {
    guard wowNames.contains(executable.lowercased()),
          executableName(pid) == executable,
          listWindows().contains(where: { $0.id == id && $0.pid == pid && $0.executable == executable })
    else { fail("windowChanged") }
    // Permission requests are restricted to the explicit request-permission action.
    guard CGPreflightScreenCaptureAccess() else { fail("permission") }
    let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
    guard let window = content.windows.first(where: {
        $0.windowID == id && $0.owningApplication?.processID == pid
    }), executableName(pid) == executable else { fail("windowChanged") }
    // Never create a display filter, region capture, stream, or desktop fallback.
    let filter = SCContentFilter(desktopIndependentWindow: window)
    let config = SCStreamConfiguration()
    let size = window.frame.size
    guard size.width >= 100 && size.height >= 100 else { fail("captureFailed") }
    let scale = min(2.0, 2048.0 / max(size.width, size.height))
    config.width = Int(size.width * scale)
    config.height = Int(size.height * scale)
    config.showsCursor = false
    config.capturesAudio = false
    config.ignoreShadowsSingleWindow = true
    let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
    let data = NSMutableData()
    guard let destination = CGImageDestinationCreateWithData(data, UTType.png.identifier as CFString, 1, nil)
    else { fail("captureFailed") }
    CGImageDestinationAddImage(destination, image, nil)
    guard CGImageDestinationFinalize(destination) else { fail("captureFailed") }
    FileHandle.standardOutput.write(data as Data)
}

@main struct CaptureHelper {
    static func main() async {
        let args = Array(CommandLine.arguments.dropFirst())
        do {
            switch args.first {
            case "list": try sendJSON(listWindows())
            case "request-permission":
                try sendJSON(["granted": CGPreflightScreenCaptureAccess() || CGRequestScreenCaptureAccess()])
            case "capture":
                guard args.count == 4, let id = UInt32(args[1]), id > 0,
                      let pid = Int32(args[2]), pid > 0 else { fail("windowChanged") }
                if #available(macOS 14.0, *) { try await capture(id, pid, args[3]) }
                else { fail("unsupported") }
            default: fail("unsupported")
            }
        } catch { fail("captureFailed") }
    }
}

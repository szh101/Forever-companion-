// One-shot Windows Graphics Capture for an explicitly selected WoW HWND.
// No desktop capture, GDI capture, injected hooks, input, or image files.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Text;
using System.Threading;
using Windows.Foundation;
using Windows.Foundation.Metadata;
using Windows.Graphics.Capture;
using Windows.Graphics.DirectX;
using Windows.Graphics.DirectX.Direct3D11;
using Windows.Graphics.Imaging;
using Windows.Storage.Streams;

internal static class WindowsCapture
{
    private const long MaxPixels = 40000000;
    private const int TimeoutMilliseconds = 4000;
    private static readonly HashSet<string> Executables = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
    {
        "wow.exe", "wowb.exe", "wowt.exe", "wowclassic.exe", "wowclassicb.exe",
        "wowforever.exe", "wowforeverb.exe", "wowf.exe"
    };

    private sealed class Failure : Exception
    {
        internal readonly string Code;
        internal Failure(string code) { Code = code; }
    }

    [ComImport, System.Runtime.InteropServices.GuidAttribute("3628E81B-3CAC-4C60-B7F4-23CE0E0C3356"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IGraphicsCaptureItemInterop
    {
        // Only the first method is needed. There is intentionally no monitor entry point.
        IntPtr CreateForWindow(IntPtr window, ref Guid iid);
    }

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr OpenProcess(uint access, bool inheritHandle, uint pid);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool QueryFullProcessImageName(IntPtr process, uint flags, StringBuilder filename, ref uint size);
    [DllImport("kernel32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(IntPtr handle);
    [DllImport("d3d11.dll", ExactSpelling = true)]
    private static extern int D3D11CreateDevice(IntPtr adapter, int driverType, IntPtr software, uint flags,
        IntPtr featureLevels, uint featureLevelCount, uint sdkVersion, out IntPtr device,
        out int featureLevel, out IntPtr immediateContext);
    [DllImport("d3d11.dll", ExactSpelling = true)]
    private static extern int CreateDirect3D11DeviceFromDXGIDevice(IntPtr dxgiDevice, out IntPtr graphicsDevice);

    [MTAThread]
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 1 && args[0] == "--check-support")
            {
                bool supported = GraphicsCaptureSession.IsSupported();
                Console.Out.WriteLine("{\"supported\":" + (supported ? "true" : "false") + ",\"captureStarted\":false}");
                return supported ? 0 : 2;
            }
            if (args.Length == 1 && args[0] == "--self-test")
            {
                TestBitmapTransfer();
                Console.Out.WriteLine("{\"passed\":true,\"captureStarted\":false,\"syntheticBitmap\":true}");
                return 0;
            }
            IntPtr hwnd;
            uint pid;
            string executable;
            ParseArguments(args, out hwnd, out pid, out executable);
            ValidateWindow(hwnd, pid, executable);
            if (!GraphicsCaptureSession.IsSupported()) throw new Failure("unsupported");
            Capture(hwnd, pid, executable);
            return 0;
        }
        catch (Failure failure) { Console.Error.WriteLine(failure.Code); return 2; }
        catch (Exception) { Console.Error.WriteLine("captureFailed"); return 2; }
    }

    private static void ParseArguments(string[] args, out IntPtr hwnd, out uint pid, out string executable)
    {
        hwnd = IntPtr.Zero;
        pid = 0;
        executable = null;
        ulong rawHandle;
        if (args.Length != 6 || args[0] != "--hwnd" || args[2] != "--pid" || args[4] != "--exe"
            || !UInt64.TryParse(args[1], NumberStyles.None, CultureInfo.InvariantCulture, out rawHandle)
            || rawHandle == 0 || rawHandle > Int64.MaxValue
            || !UInt32.TryParse(args[3], NumberStyles.None, CultureInfo.InvariantCulture, out pid) || pid == 0
            || !Executables.Contains(args[5])) throw new Failure("arguments");
        hwnd = new IntPtr((long)rawHandle);
        executable = args[5];
    }

    private static void ValidateWindow(IntPtr hwnd, uint pid, string executable)
    {
        uint currentPid;
        if (!IsWindow(hwnd) || !IsWindowVisible(hwnd)
            || GetWindowThreadProcessId(hwnd, out currentPid) == 0 || currentPid != pid)
            throw new Failure("windowChanged");
        if (IsIconic(hwnd)) throw new Failure("minimized");
        IntPtr process = OpenProcess(0x1000, false, pid); // QUERY_LIMITED_INFORMATION only.
        if (process == IntPtr.Zero) throw new Failure("windowChanged");
        try
        {
            StringBuilder path = new StringBuilder(32768);
            uint size = (uint)path.Capacity;
            if (!QueryFullProcessImageName(process, 0, path, ref size)
                || !String.Equals(Path.GetFileName(path.ToString()), executable, StringComparison.OrdinalIgnoreCase))
                throw new Failure("windowChanged");
        }
        finally { CloseHandle(process); }
    }

    private static GraphicsCaptureItem CreateItem(IntPtr hwnd)
    {
        var factory = (IGraphicsCaptureItemInterop)WindowsRuntimeMarshal.GetActivationFactory(typeof(GraphicsCaptureItem));
        Guid iid = new Guid("79C3F95B-31F7-4EC2-A464-632EF5D30760");
        IntPtr pointer = factory.CreateForWindow(hwnd, ref iid);
        if (pointer == IntPtr.Zero) throw new Failure("captureFailed");
        try { return (GraphicsCaptureItem)Marshal.GetObjectForIUnknown(pointer); }
        finally { Marshal.Release(pointer); }
    }

    private static IDirect3DDevice CreateDevice()
    {
        IntPtr device = IntPtr.Zero, context = IntPtr.Zero, dxgi = IntPtr.Zero, projected = IntPtr.Zero;
        try
        {
            int level;
            // Hardware device with BGRA support, without injection into the target process.
            Marshal.ThrowExceptionForHR(D3D11CreateDevice(IntPtr.Zero, 1, IntPtr.Zero, 0x20,
                IntPtr.Zero, 0, 7, out device, out level, out context));
            Guid iid = new Guid("54EC77FA-1377-44E6-8C32-88FD5F44C84C");
            Marshal.ThrowExceptionForHR(Marshal.QueryInterface(device, ref iid, out dxgi));
            Marshal.ThrowExceptionForHR(CreateDirect3D11DeviceFromDXGIDevice(dxgi, out projected));
            return (IDirect3DDevice)Marshal.GetObjectForIUnknown(projected);
        }
        finally
        {
            if (projected != IntPtr.Zero) Marshal.Release(projected);
            if (dxgi != IntPtr.Zero) Marshal.Release(dxgi);
            if (context != IntPtr.Zero) Marshal.Release(context);
            if (device != IntPtr.Zero) Marshal.Release(device);
        }
    }

    private static void CheckDeadline(Stopwatch clock)
    {
        if (clock.ElapsedMilliseconds >= TimeoutMilliseconds) throw new Failure("timeout");
    }

    private static byte[] ReadPixels(SoftwareBitmap source, int width, int height)
    {
        if (source.PixelWidth != width || source.PixelHeight != height
            || source.BitmapPixelFormat != BitmapPixelFormat.Bgra8) throw new Failure("resized");
        // WGC surfaces are premultiplied; the pipe protocol carries straight BGRA.
        using (SoftwareBitmap bitmap = SoftwareBitmap.Convert(source, BitmapPixelFormat.Bgra8, BitmapAlphaMode.Straight))
        {
            uint count = checked((uint)((long)width * height * 4));
            var buffer = new Windows.Storage.Streams.Buffer(count);
            bitmap.CopyToBuffer(buffer);
            if (buffer.Length != count) throw new Failure("captureFailed");
            byte[] pixels = new byte[count];
            using (DataReader reader = DataReader.FromBuffer(buffer)) reader.ReadBytes(pixels);
            return pixels;
        }
    }

    private static void TestBitmapTransfer()
    {
        // An entirely synthetic bitmap. No capture API, HWND, or desktop access.
        byte[] expected = new byte[] { 10, 20, 30, 255, 60, 50, 40, 255 };
        using (DataWriter writer = new DataWriter())
        using (SoftwareBitmap bitmap = new SoftwareBitmap(BitmapPixelFormat.Bgra8, 2, 1, BitmapAlphaMode.Premultiplied))
        {
            writer.WriteBytes(expected);
            bitmap.CopyFromBuffer(writer.DetachBuffer());
            byte[] actual = ReadPixels(bitmap, 2, 1);
            if (actual.Length != expected.Length) throw new Failure("captureFailed");
            for (int index = 0; index < expected.Length; index++)
                if (actual[index] != expected[index]) throw new Failure("captureFailed");
        }
    }

    private static void Capture(IntPtr hwnd, uint pid, string executable)
    {
        Stopwatch clock = Stopwatch.StartNew();
        GraphicsCaptureItem item = CreateItem(hwnd);
        var initialSize = item.Size;
        int width = initialSize.Width, height = initialSize.Height;
        if (width <= 0 || height <= 0 || (long)width * height > MaxPixels) throw new Failure("resized");
        byte[] pixels = null;
        using (IDirect3DDevice device = CreateDevice())
        using (Direct3D11CaptureFramePool pool = Direct3D11CaptureFramePool.CreateFreeThreaded(
            device, DirectXPixelFormat.B8G8R8A8UIntNormalized, 1, initialSize))
        using (GraphicsCaptureSession session = pool.CreateCaptureSession(item))
        {
            if (ApiInformation.IsPropertyPresent("Windows.Graphics.Capture.GraphicsCaptureSession", "IsCursorCaptureEnabled"))
                session.IsCursorCaptureEnabled = false;
            if (ApiInformation.IsPropertyPresent("Windows.Graphics.Capture.GraphicsCaptureSession", "IncludeSecondaryWindows"))
                session.IncludeSecondaryWindows = false;
            ValidateWindow(hwnd, pid, executable);
            CheckDeadline(clock);
            session.StartCapture();
            Direct3D11CaptureFrame frame = null;
            while (frame == null)
            {
                CheckDeadline(clock);
                frame = pool.TryGetNextFrame();
                if (frame == null) Thread.Sleep(10);
            }
            using (frame)
            {
                // Reject resize rather than exposing undefined pixels outside ContentSize.
                if (frame.ContentSize.Width != width || frame.ContentSize.Height != height
                    || item.Size.Width != width || item.Size.Height != height) throw new Failure("resized");
                IAsyncOperation<SoftwareBitmap> operation = SoftwareBitmap.CreateCopyFromSurfaceAsync(frame.Surface, BitmapAlphaMode.Premultiplied);
                try
                {
                    while (operation.Status == AsyncStatus.Started)
                    {
                        CheckDeadline(clock);
                        Thread.Sleep(5);
                    }
                    CheckDeadline(clock);
                    if (operation.Status != AsyncStatus.Completed) throw new Failure("captureFailed");
                    using (SoftwareBitmap bitmap = operation.GetResults())
                        pixels = ReadPixels(bitmap, width, height);
                }
                finally
                {
                    // Cleanup must not replace a bounded-timeout error with a COM error.
                    try { if (operation.Status == AsyncStatus.Started) operation.Cancel(); } catch (Exception) { }
                    try { operation.Close(); } catch (Exception) { }
                }
            }
        }
        CheckDeadline(clock);
        ValidateWindow(hwnd, pid, executable);
        // BinaryWriter writes integers little-endian. Capture stays entirely in memory.
        using (BinaryWriter output = new BinaryWriter(Console.OpenStandardOutput()))
        {
            output.Write(new byte[] { 70, 65, 73, 87, 71, 67, 49, 0 }); // FAIWGC1\0
            output.Write((uint)width);
            output.Write((uint)height);
            output.Write((uint)pixels.Length);
            output.Write(pixels);
        }
    }
}

param([long]$Handle, [int]$Left, [int]$Top, [int]$Right, [int]$Bottom, [switch]$CompileOnly)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName Accessibility,UIAutomationClient,UIAutomationTypes,WindowsBase
$references = @([Accessibility.IAccessible].Assembly.Location,
    [System.Windows.Automation.AutomationElement].Assembly.Location,
    [System.Windows.Automation.AutomationIdentifier].Assembly.Location,
    [System.Windows.Point].Assembly.Location)

Add-Type -ReferencedAssemblies $references -TypeDefinition @'
using Accessibility;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Windows.Automation;

public static class MixAccessibility
{
    [StructLayout(LayoutKind.Sequential)]
    private struct Point { public int X; public int Y; }

    [DllImport("oleacc.dll")]
    private static extern int AccessibleObjectFromWindow(IntPtr hwnd, uint objectId, ref Guid iid,
        [MarshalAs(UnmanagedType.Interface)] out IAccessible accessible);

    [DllImport("oleacc.dll")]
    private static extern int AccessibleObjectFromPoint(Point point,
        [MarshalAs(UnmanagedType.Interface)] out IAccessible accessible,
        [MarshalAs(UnmanagedType.Struct)] out object child);

    private static object Read(Func<object> getter)
    {
        try { return getter(); }
        catch (COMException exception) { return new { hresult = exception.ErrorCode }; }
    }

    private static object Describe(IAccessible accessible, object child)
    {
        if (accessible == null || child == null) return null;
        return new {
            child_id = child,
            name = Read(() => accessible.get_accName(child)),
            role = Read(() => accessible.get_accRole(child)),
            state = Read(() => accessible.get_accState(child)),
            value = Read(() => accessible.get_accValue(child)),
            default_action = Read(() => accessible.get_accDefaultAction(child))
        };
    }

    private static object Describe(AutomationElement element)
    {
        if (element == null) return null;
        var current = element.Current;
        return new {
            name = current.Name, type = current.ControlType.ProgrammaticName,
            runtime_id = element.GetRuntimeId(), hwnd = current.NativeWindowHandle,
            pid = current.ProcessId, patterns = element.GetSupportedPatterns().Select(pattern => pattern.ProgrammaticName).ToArray()
        };
    }

    private static object PointEvidence(int x, int y)
    {
        IAccessible accessible;
        object child;
        int result = AccessibleObjectFromPoint(new Point { X = x, Y = y }, out accessible, out child);
        return new {
            point = new[] { x, y }, msaa_result = result, msaa = Describe(accessible, child),
            uia = Read(() => Describe(AutomationElement.FromPoint(new System.Windows.Point(x, y))))
        };
    }

    public static object Scan(long handle, int left, int top, int right, int bottom)
    {
        if (right <= left || bottom <= top) throw new ArgumentException("Invalid popup bounds");
        IntPtr hwnd = new IntPtr(handle);
        Guid iid = typeof(IAccessible).GUID;
        IAccessible accessible;
        int result = AccessibleObjectFromWindow(hwnd, unchecked((uint)-4), ref iid, out accessible);
        AutomationElement root = AutomationElement.FromHandle(hwnd);
        var rawChildren = new List<object>();
        for (AutomationElement child = TreeWalker.RawViewWalker.GetFirstChild(root);
             child != null && rawChildren.Count < 32; child = TreeWalker.RawViewWalker.GetNextSibling(child))
            rawChildren.Add(Describe(child));

        var hits = new List<object>();
        // The frozen fixture shows four rows. Sample the badge and label of each.
        int height = bottom - top;
        for (int row = 0; row < 4; row++) {
            int y = top + (2 * row + 1) * height / 8;
            hits.Add(PointEvidence(left + (right - left) / 12, y));
            hits.Add(PointEvidence(left + (right - left) / 2, y));
        }
        return new {
            raw_root = Describe(root), raw_children = rawChildren,
            msaa_result = result, msaa_client = Describe(accessible, 0),
            msaa_child_count = accessible == null ? null : Read(() => accessible.accChildCount),
            hits = hits
        };
    }
}
'@

if (-not $CompileOnly) {
    [MixAccessibility]::Scan($Handle, $Left, $Top, $Right, $Bottom) | ConvertTo-Json -Depth 10 -Compress
}

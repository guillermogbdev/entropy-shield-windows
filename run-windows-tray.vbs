' Launch Entropy Shield without a console window, starting in the tray.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = root
pyw = "pythonw.exe"
On Error Resume Next
sh.Run """" & pyw & """ """ & root & "\main.py"" --tray", 0, False
If Err.Number <> 0 Then
    MsgBox "Could not start pythonw.exe. Install Python 3.10+ and run " & _
           "scripts\setup-windows.ps1 first.", 16, "Entropy Shield"
End If

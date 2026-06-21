' Start release dashboard with no visible console (used by start.bat).
Option Explicit

Dim fso, repoRoot, ps1, shell, args, showConsole

Set fso = CreateObject("Scripting.FileSystemObject")
repoRoot = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
ps1 = repoRoot & "\scripts\launch-release.ps1"

showConsole = False
If WScript.Arguments.Count > 0 Then
    If LCase(WScript.Arguments(0)) = "console" Then showConsole = True
End If

args = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & ps1 & """"
If showConsole Then args = args & " -ShowConsole"

Set shell = CreateObject("WScript.Shell")
' 0 = hidden window; wait on failure so start.bat console mode can surface exit codes.
If showConsole Then
    shell.Run "powershell.exe " & args, 1, True
Else
    shell.Run "powershell.exe " & args, 0, False
End If

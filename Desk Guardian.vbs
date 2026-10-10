Option Explicit
Dim fso, root, pythonw, command
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = root & "\.venv\Scripts\pythonw.exe"

If Not fso.FileExists(pythonw) Then
    MsgBox "Python 환경이 없습니다. README.md의 설치 단계를 먼저 진행하세요.", 16, "Desk Guardian"
    WScript.Quit 1
End If

command = Chr(34) & pythonw & Chr(34) & " " & Chr(34) & root & "\launcher.py" & Chr(34)
CreateObject("WScript.Shell").Run command, 0, False

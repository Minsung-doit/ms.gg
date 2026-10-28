Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
' use pythonw from PATH (no personal PC paths in the repo)
WshShell.Run "pythonw.exe run.py", 0, False

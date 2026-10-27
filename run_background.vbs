Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.Run """C:\Users\nkkju\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"" run.py", 0, False

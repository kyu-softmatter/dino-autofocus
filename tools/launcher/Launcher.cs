// "DINO Autofocus.exe": opens scripts\launcher.py with the system Python, no console.
// Built by tools\launcher\build.ps1; the exe only starts the launcher, so editing
// launcher.py needs no rebuild.
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("DINO Autofocus")]
[assembly: System.Reflection.AssemblyProduct("dino-autofocus")]

static class Program
{
    // build.ps1 rewrites this line to the clone it is run from, so the exe works on any PC
    const string Repo = @"D:\AutoFocus\dino-autofocus";

    static string FindPythonw()
    {
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string user = Path.Combine(local, @"Programs\Python\Python312\pythonw.exe");
        if (File.Exists(user)) return user;
        foreach (string dir in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';'))
        {
            try
            {
                string p = Path.Combine(dir.Trim(), "pythonw.exe");
                if (File.Exists(p) && !p.Contains("WindowsApps")) return p;
            }
            catch (ArgumentException) { }
        }
        return null;
    }

    [STAThread]
    static void Main()
    {
        string script = Path.Combine(Repo, @"scripts\launcher.py");
        string py = FindPythonw();
        if (py == null || !File.Exists(script))
        {
            MessageBox.Show(py == null ? "Python 3.12 (pythonw.exe) not found."
                                       : "Launcher not found:\n" + script,
                            "DINO Autofocus", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        var psi = new ProcessStartInfo(py, "\"" + script + "\"");
        psi.WorkingDirectory = Repo;
        psi.UseShellExecute = false;
        Process.Start(psi);
    }
}

// "DINO Autofocus.exe": starts the web app server with the repo's uv env (no console) and
// opens the browser. Built by tools\launcher\build.ps1; see docs\runbooks\launcher.md.
//   click             server already answering -> open the browser; else start it, wait for
//                     GET /api/health, then open the browser
//   Shift + click     old tkinter launcher (uv run python scripts\launcher.py), or --classic
//   Ctrl + click      stop the server this launcher started, or --stop
// Remote view is never switched on here: the server binds 127.0.0.1 only.
// Tests set DINO_AF_LAUNCHER_HEADLESS=<file>: messages, confirmations (answered OK) and browser
// opens are appended to that file instead of shown, no window opens, and server.log /
// server.pid go next to it instead of %LOCALAPPDATA%\dino-autofocus.
// Compiled by the .NET Framework csc (C# 5): no string interpolation, no ?. operator.
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("DINO Autofocus")]
[assembly: System.Reflection.AssemblyProduct("dino-autofocus")]

static class Program
{
    // build.ps1 rewrites these two lines (the clone it is run from, and -Port)
    const string Repo = @"D:\AutoFocus\dino-autofocus";
    const int Port = 8765;

    const string Title = "DINO Autofocus";
    const int StartTimeoutSec = 60;  // the first `uv run` after a pull may sync the env

    static string Url { get { return "http://127.0.0.1:" + Port + "/"; } }

    static readonly string Headless = Environment.GetEnvironmentVariable("DINO_AF_LAUNCHER_HEADLESS");

    static string DataDir
    {
        get
        {
            if (!string.IsNullOrEmpty(Headless))
                return Path.GetDirectoryName(Path.GetFullPath(Headless));
            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            return Path.Combine(local, "dino-autofocus");
        }
    }

    static string LogPath { get { return Path.Combine(DataDir, "server.log"); } }
    static string PidPath { get { return Path.Combine(DataDir, "server.pid"); } }

    // ---- uv ----------------------------------------------------------------------------

    static string FindUv()
    {
        foreach (string dir in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';'))
        {
            try
            {
                if (dir.Trim().Length == 0) continue;
                string p = Path.Combine(dir.Trim(), "uv.exe");
                if (File.Exists(p)) return p;
            }
            catch (ArgumentException) { }
        }
        string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string[] standard = {
            Path.Combine(home, @".local\bin\uv.exe"),               // official installer
            Path.Combine(home, @".cargo\bin\uv.exe"),               // older installer
            Path.Combine(local, @"Microsoft\WinGet\Links\uv.exe"),  // winget
            Path.Combine(home, @"scoop\shims\uv.exe"),              // scoop
        };
        foreach (string p in standard)
            if (File.Exists(p)) return p;
        return null;
    }

    // ---- server probes -----------------------------------------------------------------

    static bool HealthOk(int timeoutMs)
    {
        try
        {
            var req = (HttpWebRequest)WebRequest.Create(Url + "api/health");
            req.Timeout = timeoutMs;
            req.ReadWriteTimeout = timeoutMs;
            req.Proxy = null;
            using (var resp = (HttpWebResponse)req.GetResponse())
                return resp.StatusCode == HttpStatusCode.OK;
        }
        catch (WebException) { return false; }
    }

    static bool PortOpen()
    {
        try
        {
            using (var c = new TcpClient())
            {
                IAsyncResult r = c.BeginConnect(IPAddress.Loopback, Port, null, null);
                if (!r.AsyncWaitHandle.WaitOne(300)) return false;
                c.EndConnect(r);
                return true;
            }
        }
        catch (SocketException) { return false; }
    }

    // ---- messages ----------------------------------------------------------------------

    static bool Note(string kind, string text)
    {
        if (string.IsNullOrEmpty(Headless)) return false;
        File.AppendAllText(Headless, kind + ": " + text.Replace("\n", "\n    ") + "\r\n",
                           new UTF8Encoding(false));
        return true;
    }

    static void Error(string text)
    {
        if (Note("error", text)) return;
        MessageBox.Show(text, Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
    }

    static void Info(string text)
    {
        if (Note("info", text)) return;
        MessageBox.Show(text, Title, MessageBoxButtons.OK, MessageBoxIcon.Information);
    }

    static bool Confirm(string text)
    {
        if (Note("confirm", text)) return true;
        return MessageBox.Show(text, Title, MessageBoxButtons.OKCancel, MessageBoxIcon.Question)
               == DialogResult.OK;
    }

    static string LogTail(int lines)
    {
        try
        {
            using (var fs = new FileStream(LogPath, FileMode.Open, FileAccess.Read,
                                           FileShare.ReadWrite | FileShare.Delete))
            using (var sr = new StreamReader(fs))
            {
                string[] all = sr.ReadToEnd().Replace("\r", "").TrimEnd().Split('\n');
                int from = Math.Max(0, all.Length - lines);
                return string.Join("\n", all, from, all.Length - from);
            }
        }
        catch (IOException) { return ""; }
    }

    static void OpenBrowser()
    {
        if (Note("browser", Url)) return;
        Process.Start(new ProcessStartInfo(Url) { UseShellExecute = true });
    }

    // ---- start / stop ------------------------------------------------------------------

    // The server runs under a hidden cmd.exe that appends its output to the log file, so
    // nothing has to stay alive here to drain pipes. server.pid records that cmd.exe.
    static Process StartServer(string uv)
    {
        Directory.CreateDirectory(DataDir);
        string prev = Path.Combine(DataDir, "server.prev.log");
        try
        {
            if (File.Exists(LogPath)) { File.Delete(prev); File.Move(LogPath, prev); }
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }

        string args = "run python -m dino_autofocus.server --port " + Port;
        File.WriteAllText(LogPath, string.Format("# {0:yyyy-MM-dd HH:mm:ss} {1} {2}\r\n# cwd {3}\r\n",
                                                 DateTime.Now, uv, args, Repo), new UTF8Encoding(false));
        string line = "\"" + uv + "\" " + args + " >> \"" + LogPath + "\" 2>&1";
        var psi = new ProcessStartInfo(Path.Combine(Environment.SystemDirectory, "cmd.exe"),
                                       "/d /s /c \"" + line + "\"");
        psi.WorkingDirectory = Repo;
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        psi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
        psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        Process p = Process.Start(psi);
        File.WriteAllText(PidPath, p.Id + " " + p.StartTime.ToFileTimeUtc());
        return p;
    }

    // The process recorded in server.pid, if it is still the one this launcher started.
    static Process RecordedServer()
    {
        try
        {
            string[] parts = File.ReadAllText(PidPath).Trim().Split(' ');
            Process p = Process.GetProcessById(int.Parse(parts[0]));
            if (!p.HasExited && p.StartTime.ToFileTimeUtc() == long.Parse(parts[1])) return p;
        }
        catch (Exception e)
        {
            if (!(e is IOException || e is ArgumentException || e is FormatException
                  || e is IndexOutOfRangeException || e is InvalidOperationException
                  || e is UnauthorizedAccessException || e is System.ComponentModel.Win32Exception))
                throw;
        }
        return null;
    }

    static void StopServer()
    {
        Process p = RecordedServer();
        if (p == null)
        {
            string extra = PortOpen()
                ? "\n\nSomething is listening on port " + Port + ", but this launcher did not start it."
                : "";
            Info("No server started by this launcher is running." + extra);
            return;
        }
        if (!Confirm("Stop the DINO Autofocus server (" + Url + ")?\n\n"
                     + "Open pages lose their connection.")) return;
        // cmd.exe -> uv.exe -> python.exe: end the whole tree
        var kill = new ProcessStartInfo("taskkill", "/PID " + p.Id + " /T /F");
        kill.UseShellExecute = false;
        kill.CreateNoWindow = true;
        using (Process k = Process.Start(kill)) k.WaitForExit(10000);
        try { File.Delete(PidPath); } catch (IOException) { }
    }

    static void StartClassic(string uv)
    {
        string script = Path.Combine(Repo, @"scripts\launcher.py");
        if (!File.Exists(script)) { Error("Old launcher not found:\n" + script); return; }
        var psi = new ProcessStartInfo(uv, "run python \"" + script + "\"");
        psi.WorkingDirectory = Repo;
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        Process.Start(psi);
    }

    // ---- waiting window ----------------------------------------------------------------

    static bool PollHealth(Process server, Func<bool> cancelled)
    {
        DateTime end = DateTime.Now.AddSeconds(StartTimeoutSec);
        while (!cancelled() && DateTime.Now < end && !server.HasExited)
        {
            if (HealthOk(1000)) return true;
            Thread.Sleep(400);
        }
        return false;
    }

    // A small "starting" window while the server comes up. True once /api/health answers;
    // false on timeout, when the server exits, or when the user closes the window.
    static bool WaitForServer(Process server)
    {
        if (Note("wait", Url + "api/health"))
            return PollHealth(server, delegate { return false; });

        var form = new Form();
        form.Text = Title;
        form.FormBorderStyle = FormBorderStyle.FixedDialog;
        form.MaximizeBox = false;
        form.MinimizeBox = false;
        form.StartPosition = FormStartPosition.CenterScreen;
        form.ClientSize = new Size(380, 70);
        form.Font = new Font("Segoe UI", 10f);
        try { form.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); }
        catch (ArgumentException) { }
        var label = new Label();
        label.Dock = DockStyle.Fill;
        label.TextAlign = ContentAlignment.MiddleCenter;
        label.Text = "Starting the server on " + Url + " ...";
        form.Controls.Add(label);

        bool ok = false;
        bool done = false;
        form.FormClosing += delegate { done = true; };
        var poll = new Thread(delegate ()
        {
            ok = PollHealth(server, delegate { return done; });
            try { form.BeginInvoke((MethodInvoker)delegate { form.Close(); }); }
            catch (InvalidOperationException) { }  // already closed by the user
        });
        poll.IsBackground = true;
        form.Shown += delegate { poll.Start(); };
        Application.Run(form);
        return ok;
    }

    static void ReportStartFailure(Process server)
    {
        string why = server.HasExited
            ? "The server stopped while starting."
            : "The server did not answer " + Url + "api/health within " + StartTimeoutSec
              + " s. It may still be starting: click the launcher again to keep waiting, or "
              + "Ctrl + click to stop it.";
        string tail = LogTail(12);
        Error(why + "\n\nLog: " + LogPath + (tail.Length > 0 ? "\n\n" + tail : ""));
    }

    // ---- main --------------------------------------------------------------------------

    [STAThread]
    static void Main(string[] args)
    {
        Application.EnableVisualStyles();
        Keys mods = Control.ModifierKeys;
        bool stop = Array.IndexOf(args, "--stop") >= 0 || (mods & Keys.Control) != 0;
        bool classic = Array.IndexOf(args, "--classic") >= 0 || (mods & Keys.Shift) != 0;

        if (stop) { StopServer(); return; }

        if (!Directory.Exists(Repo))
        {
            Error("Repository not found:\n" + Repo + "\n\nRebuild the launcher from the clone "
                  + "you use (tools\\launcher\\build.ps1).");
            return;
        }
        string uv = FindUv();
        if (uv == null)
        {
            Error("uv not found (PATH, %USERPROFILE%\\.local\\bin, winget, scoop).\n\n"
                  + "Install uv, run `uv sync` in\n" + Repo + "\nand try again.");
            return;
        }
        if (classic) { StartClassic(uv); return; }

        if (HealthOk(1500)) { OpenBrowser(); return; }

        // A server from an earlier click may still be starting: wait for it, never start a second.
        Process mine = RecordedServer();
        if (mine != null)
        {
            if (WaitForServer(mine)) OpenBrowser(); else ReportStartFailure(mine);
            return;
        }
        if (PortOpen())
        {
            Error("Port " + Port + " is in use, but no DINO Autofocus server answers there\n("
                  + Url + "api/health).\n\nClose the program using the port, or rebuild the "
                  + "launcher with another port (build.ps1 -Port N).");
            return;
        }

        string module = Path.Combine(Repo, @"src\dino_autofocus\server\__main__.py");
        if (!File.Exists(module))
        {
            Error("Server not found in this clone:\n" + module + "\n\n"
                  + "Pull the latest main (the web server comes with task T-009), run `uv sync`, "
                  + "and try again. Shift + click opens the old launcher.");
            return;
        }

        Process server;
        try { server = StartServer(uv); }
        catch (Exception e)
        {
            Error("Could not start the server:\n" + e.Message + "\n\nLog: " + LogPath);
            return;
        }
        if (WaitForServer(server)) OpenBrowser(); else ReportStartFailure(server);
    }
}

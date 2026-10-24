using System.Text.Json;

namespace Atticus;

sealed class HubWindow : PageWindow
{
    readonly System.Windows.Forms.Timer refresh = new() { Interval = 2500 };
    readonly System.Windows.Forms.Timer reminders = new() { Interval = 2000 };
    bool polling;
    string tab = "history", query = "";

    public HubWindow() : base("hub.html", "hub", "Atticus Control Centre", 1020, 720)
    {
        FormBorderStyle = FormBorderStyle.Sizable; MaximizeBox = true; MinimumSize = new Size(720, 520);
        FormClosing += (_, e) => { if (e.CloseReason == CloseReason.UserClosing) { e.Cancel = true; Hide(); } };
        refresh.Tick += (_, _) => { if (Visible) RefreshState(); };
        reminders.Tick += async (_, _) =>
        {
            if (polling) return; polling = true;
            try
            {
                var result = await Call(new { action = "tick" });
                if (result.TryGetProperty("data", out var alerts) && alerts.ValueKind == JsonValueKind.Array)
                    foreach (var alert in alerts.EnumerateArray()) Program.Tray.Notify(alert.GetProperty("title").GetString() + ": " + alert.GetProperty("text").GetString());
            }
            finally { polling = false; }
        };
    }

    public void Start()
    {
        _ = Call(new { action = "recover" });
        reminders.Start(); refresh.Start();
    }

    public async void Open(string section = "history")
    {
        tab = section; Raise(); await Ensure(); RefreshState();
    }

    static async Task<JsonElement> Call(object value)
    {
        var text = await Task.Run(() => Py.RunWithInput(new[] { "--hub" }, Web.Json(value), 120));
        try { return JsonDocument.Parse(text).RootElement.Clone(); }
        catch { return JsonDocument.Parse("{\"ok\":false,\"error\":\"The local service did not respond. Try again.\"}").RootElement.Clone(); }
    }

    async void RefreshState()
    {
        var result = await Call(new { action = "state", query });
        if (result.TryGetProperty("data", out var data))
            Js($"hub.load({data.GetRawText()}, {Web.Json(tab)}, {Web.Json(new { recordingLimit = Prefs.Num("recordingLimit") })})");
        else if (result.TryGetProperty("error", out var error)) Js($"hub.result({Web.Json(error.GetString())}, false)");
    }

    protected override async void OnMessage(JsonElement message)
    {
        if (!message.TryGetProperty("action", out var action)) return;
        var operation = action.GetString();
        string S(string key) => message.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : "";
        if (operation == "ready") { RefreshState(); return; }
        if (operation == "search") { query = S("query"); RefreshState(); return; }
        if (operation == "tab") { tab = S("tab"); RefreshState(); return; }
        if (operation == "ask") { Program.Box.Demo(S("text")); return; }
        if (operation == "setup_apply")
        {
            if (MessageBox.Show(this, "Approve the project folders, saved commands and connector definitions shown in Review setup? Local servers and commands run with your Windows account access. Later file edits, commands and MCP calls still require approval. External account sign-ins remain separate.", "Approve reviewed setup", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        }
        if (operation == "project_grant")
        {
            using var dialog = new FolderBrowserDialog { Description = "Choose the project folder Atticus may read and propose edits to", UseDescriptionForTitle = true };
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            var result = await Call(new { action = "project_grant", path = dialog.SelectedPath, name = new DirectoryInfo(dialog.SelectedPath).Name });
            ShowResult(result); RefreshState(); return;
        }
        if (operation is "project_apply" or "project_run" or "mcp_save")
        {
            var details = operation switch
            {
                "project_apply" => "Apply the file change shown in the preview? The original will be backed up. A changed file will be rejected.",
                "project_run" => "Run the saved project command? It runs with your Windows account access, not in a filesystem sandbox. Check its executable and arguments first.",
                _ => "Connect this MCP server for future requests? A local server can run code with your account access. Every tool call will still ask for approval."
            };
            if (MessageBox.Show(this, details, "Approve action", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        }
        if (operation == "voice_limit")
        {
            if (!message.TryGetProperty("seconds", out var seconds)) return;
            Program.Settings.Apply("recordingLimit", Math.Clamp(seconds.GetDouble(), 60, 1800));
            Js("hub.result('Voice recording limit saved.', true)"); return;
        }
        if (operation == "meeting_start") { Program.Meeting.Start(); RefreshState(); return; }
        if (operation == "meeting_stop") { await Program.Meeting.Stop(); RefreshState(); return; }
        if (operation == "meeting_cancel") { Program.Meeting.Cancel(); return; }
        if (operation == "transcribe_file")
        {
            using var dialog = new OpenFileDialog { Filter = "Audio files|*.wav;*.mp3;*.m4a;*.flac;*.wma|All files|*.*" };
            if (dialog.ShowDialog(this) == DialogResult.OK) await Program.Meeting.TranscribeFile(dialog.FileName);
            RefreshState(); return;
        }
        var response = await Call(message); ShowResult(response);
        if (operation is "project_files" or "mcp_tools" && response.TryGetProperty("data", out var listing)) Js($"hub.list({listing.GetRawText()})");
        RefreshState();
    }

    void ShowResult(JsonElement result)
    {
        bool ok = result.TryGetProperty("ok", out var flag) && flag.GetBoolean();
        Js($"hub.result({Web.Json(ok ? "Saved. See the updated result below." : result.TryGetProperty("error", out var e) ? e.GetString() : "Action failed.")}, {(ok ? "true" : "false")})");
    }
}

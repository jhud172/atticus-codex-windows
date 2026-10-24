using NAudio.Wave;
using NAudio.Wave.SampleProviders;

namespace Atticus;

sealed class MeetingNotes
{
    WasapiRecorder system;
    WaveIn mic;
    WaveFileWriter systemWriter, micWriter;
    readonly object audioLock = new();
    string folder;
    DateTime started;
    CancellationTokenSource transcription;
    System.Windows.Forms.Timer limit;
    bool recording;

    void Status(string message) => Program.Hub.Js($"hub.meeting({Web.Json(new { recording, message })})");

    public void Start()
    {
        if (recording || transcription != null) { Status("Finish the current recording or transcription first."); return; }
        if (MessageBox.Show("Record system audio and your microphone locally for meeting notes? Make sure participants know you are recording. Audio is deleted after transcription; transcript text is saved locally.", "Start meeting recording", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        folder = Path.Combine(Paths.Local, "recording-" + Guid.NewGuid()); Directory.CreateDirectory(folder);
        try
        {
            system = new WasapiRecorderBuilder().WithLoopbackCapture().Build();
            systemWriter = new WaveFileWriter(Path.Combine(folder, "system.wav"), system.WaveFormat);
            system.DataAvailable += (buffer, flags, devicePosition, qpcPosition) => { lock (audioLock) systemWriter?.Write(buffer); };
            mic = new WaveIn { WaveFormat = new WaveFormat(16000, 16, 1), BufferMilliseconds = 100 };
            micWriter = new WaveFileWriter(Path.Combine(folder, "microphone.wav"), mic.WaveFormat);
            mic.DataAvailable += (_, e) => { lock (audioLock) micWriter?.Write(e.Buffer, 0, e.BytesRecorded); };
            system.StartRecording(); mic.StartRecording(); started = DateTime.Now; recording = true;
            limit = new System.Windows.Forms.Timer { Interval = 1000 };
            limit.Tick += async (_, _) => { if ((DateTime.Now - started).TotalHours >= 2) await Stop(); };
            limit.Start(); Status("Recording system audio and microphone. Stop when the meeting ends.");
            Program.Tray.Notify("Meeting recording started. Stop it in the control centre.");
        }
        catch (Exception error) { DisposeCapture(); recording = false; DeleteCapture(); Status("Could not record: " + error.Message); }
    }

    void DisposeCapture()
    {
        limit?.Stop(); limit?.Dispose(); limit = null;
        try { system?.StopRecording(); } catch { }
        try { mic?.StopRecording(); } catch { }
        system?.Dispose(); system = null; mic?.Dispose(); mic = null;
        lock (audioLock) { systemWriter?.Dispose(); systemWriter = null; micWriter?.Dispose(); micWriter = null; }
    }

    public async Task Stop()
    {
        if (!recording) { Status("No meeting is recording."); return; }
        recording = false; DisposeCapture();
        var captured = folder;
        await Transcribe(new[] { (Path.Combine(captured, "system.wav"), "System audio"), (Path.Combine(captured, "microphone.wav"), "Microphone") }, "Meeting " + started.ToString("dd MMM yyyy HH:mm"));
        foreach (var path in Directory.GetFiles(captured)) { try { File.Delete(path); } catch { } }
        try { Directory.Delete(captured); } catch { }
    }

    public Task TranscribeFile(string path) => Transcribe(new[] { (path, "Audio file") }, Path.GetFileNameWithoutExtension(path));

    async Task Transcribe((string path, string label)[] files, string title)
    {
        if (transcription != null) { Status("A transcription is already running."); return; }
        transcription = new CancellationTokenSource(); var token = transcription.Token;
        try
        {
            Status("Preparing local speech transcription…"); await Program.Speech.Load();
            if (!Program.Speech.Ready) throw new InvalidOperationException("Download a speech model in setup first.");
            var parts = new List<string>();
            foreach (var (path, label) in files)
            {
                parts.AddRange(await TranscribeAudio(path, label, message => Program.Post(() => Status(message)), token));
            }
            token.ThrowIfCancellationRequested();
            if (parts.Count == 0) { Status("No recognisable speech was found. No transcript was saved."); return; }
            var directory = Path.Combine(Paths.Config, "meetings"); Directory.CreateDirectory(directory);
            var filename = Path.Combine(directory, DateTime.Now.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N")[..8] + ".json");
            var transcript = string.Join("\n\n", parts);
            File.WriteAllText(filename, Web.Json(new { title, created = DateTimeOffset.Now.ToString("O"), transcript, note = "Source labels identify audio channels, not individual speakers. Review transcription accuracy." }));
            Status("Transcript saved locally. Review it before requesting a Codex summary."); Program.Tray.Notify("Meeting transcript is ready in the control centre.");
        }
        catch (OperationCanceledException) { Status("Transcription cancelled."); }
        catch (Exception error) { Status("Transcription failed: " + error.Message); }
        finally { transcription.Dispose(); transcription = null; }
    }

    internal static Task<List<string>> TranscribeAudio(string path, string label, Action<string> progress, CancellationToken token) => Task.Run(async () =>
    {
        var parts = new List<string>();
        using var reader = new AudioFileReader(path);
        ISampleProvider source = reader;
        if (source.WaveFormat.Channels == 2) source = new StereoToMonoSampleProvider(source);
        if (source.WaveFormat.Channels != 1) throw new InvalidOperationException("Choose mono or stereo audio.");
        if (source.WaveFormat.SampleRate != 16000) source = new WdlResamplingSampleProvider(source, 16000);
        var buffer = new float[16000 * 30]; int got, offset = 0;
        while ((got = Fill(source, buffer)) > 0)
        {
            token.ThrowIfCancellationRequested();
            progress?.Invoke("Transcribing " + label + " — " + offset + " seconds processed…");
            var text = await Program.Speech.TranscribeOnce(buffer.Take(got).ToArray());
            if (!string.IsNullOrWhiteSpace(text)) parts.Add($"[{label} {TimeSpan.FromSeconds(offset):hh\\:mm\\:ss}] {text}");
            offset += got / 16000;
        }
        return parts;
    }, token);

    static int Fill(ISampleProvider source, float[] buffer)
    {
        int got = 0, n;
        while (got < buffer.Length && (n = source.Read(buffer.AsSpan(got, buffer.Length - got))) > 0) got += n;
        return got;
    }

    public void Cancel() => transcription?.Cancel();
    void DeleteCapture()
    {
        if (folder == null) return;
        // Delete only the exact recording directory created by this instance.
        foreach (var name in new[] { "system.wav", "microphone.wav" }) { try { File.Delete(Path.Combine(folder, name)); } catch { } }
        try { Directory.Delete(folder); } catch { }
        folder = null;
    }
    public void Shutdown() { transcription?.Cancel(); recording = false; DisposeCapture(); DeleteCapture(); }
}

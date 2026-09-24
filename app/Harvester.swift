import AppKit
import SwiftUI
import AVKit
import UniformTypeIdentifiers

struct HarvestJob: Decodable, Identifiable, Equatable {
    let id: String
    let source: String
    let identity: String
    let input: String?
    let name: String?
    let state: String
    let outputPath: String?
    let videoPath: String?
    let error: String?
    let progress: Double?
    let progressLabel: String?
    let outputBytes: Int64?
    let options: ExportChoices?
    var sourceLabel: String { source.hasPrefix("web:") ? String(source.dropFirst(4)) : source.capitalized }
    var title: String { name ?? (source == "local" ? URL(fileURLWithPath: identity).lastPathComponent : source.hasPrefix("web:") ? (input ?? sourceLabel) : "\(sourceLabel) · \(identity)") }
    var active: Bool { ["downloading", "waiting_to_convert", "converting", "saving"].contains(state) }
    var retryable: Bool { ["failed", "cancelled", "interrupted"].contains(state) }
    var status: String { state.replacingOccurrences(of: "_", with: " ").capitalized }
}

struct ExportChoices: Decodable, Equatable {
    let start: Double?
    let end: Double?
    let videoPreset: String?
    let audioPreset: String?
    var description: String {
        var parts: [String] = []
        if start != nil || end != nil { parts.append("Clip \(start ?? 0)s–\(end.map { String($0) + "s" } ?? "end")") }
        if videoPreset == "h264_small" { parts.append("Smaller H.264") }
        if audioPreset == "flac_48k_24" { parts.append("FLAC audio") }
        return parts.joined(separator: " · ")
    }
}

struct MediaPreview: NSViewRepresentable {
    let player: AVPlayer
    func makeNSView(context: Context) -> AVPlayerView {
        let view = AVPlayerView()
        view.controlsStyle = .floating
        view.player = player
        return view
    }
    func updateNSView(_ view: AVPlayerView, context: Context) { view.player = player }
}

struct PreviewSheet: View {
    let job: HarvestJob
    @Environment(\.dismiss) private var dismiss
    @State private var player = AVPlayer()
    var body: some View {
        VStack(alignment: .leading) {
            HStack { Text(job.title).font(.headline); Spacer(); Button("Done") { dismiss() }.keyboardShortcut(.cancelAction) }
            MediaPreview(player: player).frame(minWidth: 640, minHeight: 360)
            Text("Silent video preview. The separate audio file is in the bundle.").font(.caption).foregroundStyle(.secondary)
        }.padding(16)
            .onAppear { if let path = job.videoPath { player.replaceCurrentItem(with: AVPlayerItem(url: URL(fileURLWithPath: path))) } }
            .onDisappear { player.pause(); player.replaceCurrentItem(with: nil) }
    }
}

struct QueueSnapshot: Decodable {
    let jobs: [HarvestJob]
    let pausedSources: [String]
    let runnerActive: Bool?
}

@MainActor final class QueueModel: ObservableObject {
    @Published var selectedVideos: Set<String> = []
    @Published var sendingToChromatron = false
    @Published var sentVideos: [String: Double] = UserDefaults.standard.dictionary(forKey: "chromatronHandoffs") as? [String: Double] ?? [:]
    @Published var links = ""
    @Published var adding = false
    @Published var renaming: HarvestJob?
    @Published var newName = ""
    @Published var jobs: [HarvestJob] = []
    @Published var pausedSources: [String] = []
    @Published var message = "Paste links and keep hunting."
    @Published var running = false
    @Published var sharedRunnerActive = false
    @Published var previewing: HarvestJob?
    @Published var trimStart = ""
    @Published var trimEnd = ""
    @Published var videoPreset = "h264_all_keyframes"
    @Published var audioPreset = "wav_48k_24"
    @AppStorage("maxDurationMinutes") var maxDurationMinutes = 60
    @AppStorage("maxSourceMB") var maxSourceMB = 500
    @Published var freeSpace = ""
    @Published var chromatron: URL?
    @Published var output: URL
    let root: URL
    let queueRoot: URL
    let isDevelopment: Bool
    private var runner: Process?
    private var refreshing = false
    private var refreshRevision = 0

    init() {
        let developmentPath = Bundle.main.object(forInfoDictionaryKey: "HarvesterDevelopmentRoot") as? String
        isDevelopment = developmentPath != nil
        root = developmentPath.map { URL(fileURLWithPath: $0) } ?? Bundle.main.resourceURL!
        queueRoot = developmentPath != nil ? root.appendingPathComponent("state/v2-queue") :
            FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/harvester/queue-v2")
        let previousOutput = developmentPath == nil
            ? UserDefaults(suiteName: "com.harvester.v2.development")?.url(forKey: "outputFolder") : nil
        let defaultOutput = developmentPath != nil ? root.appendingPathComponent("build/v2-output") :
            FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Movies/Harvester")
        output = UserDefaults.standard.url(forKey: "outputFolder") ?? previousOutput ?? defaultOutput
        chromatron = UserDefaults.standard.url(forKey: "chromatronApp") ?? (developmentPath == nil
            ? UserDefaults(suiteName: "com.harvester.v2.development")?.url(forKey: "chromatronApp") : nil)
    }

    func command(_ arguments: [String], input: String = "") async -> Data? {
        let executable = root.appendingPathComponent("scripts/harvester-v2")
        let fullArguments = ["--queue-root", queueRoot.path] + arguments
        return await Task.detached {
            let process = Process()
            process.executableURL = executable
            process.arguments = fullArguments
            let incoming = Pipe(), outgoing = Pipe()
            process.standardInput = incoming
            process.standardOutput = outgoing
            process.standardError = FileHandle.nullDevice
            do {
                try process.run()
                try incoming.fileHandleForWriting.write(contentsOf: Data(input.utf8))
                try incoming.fileHandleForWriting.close()
                let result = outgoing.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                return process.terminationStatus == 0 ? result : nil
            } catch { return nil }
        }.value
    }

    func refresh(force: Bool = false) async {
        guard force || !refreshing else { return }
        refreshing = true
        refreshRevision += 1
        let revision = refreshRevision
        defer { if revision == refreshRevision { refreshing = false } }
        if let data = await command(["status"]) {
            guard revision == refreshRevision else { return }
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            if let state = try? decoder.decode(QueueSnapshot.self, from: data) {
                let updatedJobs = Array(state.jobs.reversed())
                if jobs != updatedJobs { jobs = updatedJobs }
                if pausedSources != state.pausedSources { pausedSources = state.pausedSources }
                let active = state.runnerActive ?? false
                if sharedRunnerActive != active { sharedRunnerActive = active }
            } else {
                message = "Could not read the queue format. Your saved jobs have not been changed."
            }
        } else {
            message = "Could not read queue status. Check access to the app's backend and media tools."
        }
    }

    func add(_ links: String) async -> Bool {
        var arguments = ["add", "--stdin", "--video-preset", videoPreset, "--audio-preset", audioPreset]
        if !trimStart.isEmpty { arguments += ["--start", trimStart] }
        if !trimEnd.isEmpty { arguments += ["--end", trimEnd] }
        guard let data = await command(arguments, input: links),
              let results = try? JSONSerialization.jsonObject(with: data) as? [[String: String]] else {
            message = "Could not add items. Check the clip range (seconds or HH:MM:SS, end after start, up to 6 hours) and companion."
            return false
        }
        let added = results.filter { $0["status"] == "added" }.count
        let duplicate = results.filter { $0["status"] == "duplicate" }.count
        let rejected = results.filter { $0["status"] == "rejected" }.count
        message = "Added \(added) · Already in queue \(duplicate) · Rejected \(rejected)"
        if let reason = results.first(where: { $0["status"] == "rejected" })?["message"] { message += ". " + reason }
        await refresh(force: true)
        return rejected == 0
    }

    func submitDraft(startImmediately: Bool) async {
        guard !adding else { return }
        adding = true
        defer { adding = false }
        let draft = links
        if !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            let accepted = await add(draft)
            // Keep anything typed while the submission was being saved.
            if accepted && links == draft { links = "" }
        } else {
            await refresh(force: true)
        }
        if startImmediately {
            if running {
                // The existing watcher will pick up newly submitted work.
                return
            }
            if jobs.contains(where: { $0.state == "queued" && !pausedSources.contains($0.source) }) {
                start()
            } else if draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                message = "Paste a link or add a file to harvest. Failed jobs need Retry first."
            }
        }
    }

    func edit(_ action: String, job: HarvestJob, name: String? = nil) async {
        let result = await command([action, job.id] + (name.map { [$0] } ?? []))
        if result == nil { message = "That action is unavailable for this job right now." }
        await refresh()
    }

    func receiveBrowserSubmission(_ url: URL) async {
        guard !isDevelopment, ["harvester://queue/harvest", "harvester://queue/show"].contains(url.absoluteString) else { return }
        await refresh(force: true)
        if url.path == "/show" { message = "Queue ready. Harvest starts pending items; new links can be added while it runs."; return }
        if jobs.contains(where: { $0.state == "queued" && !pausedSources.contains($0.source) }) {
            start()
        } else {
            message = "Link already in queue. Failed or interrupted jobs need Retry."
        }
    }

    func resume(_ source: String) async {
        _ = await command(["resume-source", source])
        await refresh()
    }

    func chooseOutput() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.canCreateDirectories = true
        if panel.runModal() == .OK, let url = panel.url {
            output = url
            UserDefaults.standard.set(url, forKey: "outputFolder")
        }
    }

    func chooseFiles() async {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        if panel.runModal() == .OK {
            _ = await add(panel.urls.map(\.path).joined(separator: "\n"))
        }
    }

    func start() {
        guard runner == nil else { return }
        if sharedRunnerActive {
            message = "Queue already running. New items will be picked up automatically."
            return
        }
        let process = Process()
        process.executableURL = root.appendingPathComponent("scripts/harvester-v2")
        // Instagram is intentionally not given a profile automatically. Its
        // account authorization UI belongs to a later milestone.
        process.arguments = ["--queue-root", queueRoot.path, "run", "--watch", "--output", output.path,
                             "--max-duration-seconds", String(min(360, max(1, maxDurationMinutes)) * 60),
                             "--max-source-mb", String(min(5120, max(1, maxSourceMB)))]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        process.terminationHandler = { [weak self] finished in
            Task { @MainActor in
                self?.runner = nil
                self?.running = false
                await self?.refresh(force: true)
                self?.message = self?.sharedRunnerActive == true
                    ? "Queue is running in another window. New items will be picked up automatically."
                    : (finished.terminationStatus == 0 ? "Queue stopped. Pending jobs are saved." : "Queue could not start. Check the output folder and media tools.")
            }
        }
        do {
            try process.run()
            runner = process
            running = true
            message = "Queue running. Keep adding links."
        } catch { message = "Could not start the development companion." }
    }

    func stop() {
        runner?.terminate()
        message = "Stopping active jobs. Interrupted jobs can be retried."
    }

    func openVideo(_ job: HarvestJob) {
        guard let path = job.videoPath else { return }
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }

    func updateFreeSpace() {
        let parent = FileManager.default.fileExists(atPath: output.path) ? output : output.deletingLastPathComponent()
        if let attributes = try? FileManager.default.attributesOfFileSystem(forPath: parent.path),
           let bytes = attributes[.systemFreeSize] as? Int64 {
            freeSpace = ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file) + " available"
        }
    }

    func chooseChromatron() {
        let panel = NSOpenPanel()
        panel.title = "Choose your current Chromatron app"
        panel.allowedContentTypes = [.application]
        panel.canChooseDirectories = false
        if panel.runModal() == .OK, let url = panel.url {
            chromatron = url
            UserDefaults.standard.set(url, forKey: "chromatronApp")
        }
    }

    var completedVideos: [HarvestJob] {
        jobs.filter { $0.state == "complete" && $0.videoPath != nil }
    }

    func handoffKey(_ job: HarvestJob) -> String {
        queueRoot.path + "/" + job.id + ":" + (job.videoPath ?? "")
    }

    func wasSent(_ job: HarvestJob) -> Bool { sentVideos[handoffKey(job)] != nil }

    func sendToChromatron(_ requested: [HarvestJob]) {
        guard !sendingToChromatron else { return }
        let candidates = requested.filter { $0.state == "complete" && $0.videoPath != nil }
        guard !candidates.isEmpty else { return }
        if chromatron == nil { chooseChromatron() }
        guard let application = chromatron else { return }
        let available = candidates.filter { FileManager.default.isReadableFile(atPath: $0.videoPath!) }
        let missing = candidates.count - available.count
        guard !available.isEmpty else {
            message = "Selected video files are missing or unreadable. Use Show bundle to locate them."
            return
        }
        // Preserve queue order and submit each local URL once, even if two jobs share it.
        var paths = Set<String>()
        let urls = available.compactMap { job -> URL? in
            let url = URL(fileURLWithPath: job.videoPath!).standardizedFileURL
            return paths.insert(url.path).inserted ? url : nil
        }
        sendingToChromatron = true
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = false
        NSWorkspace.shared.open(urls, withApplicationAt: application,
                                configuration: configuration) { _, error in
            Task { @MainActor in
                self.sendingToChromatron = false
                guard error == nil else {
                    self.message = "Chromatron handoff was not confirmed. Selection kept; check Chromatron before retrying to avoid duplicates."
                    return
                }
                let now = Date().timeIntervalSince1970
                for job in available {
                    self.sentVideos[self.handoffKey(job)] = now
                    self.selectedVideos.remove(job.id)
                }
                UserDefaults.standard.set(self.sentVideos, forKey: "chromatronHandoffs")
                self.message = "Sent \(urls.count) video\(urls.count == 1 ? "" : "s") to Chromatron."
                    + (missing > 0 ? " Skipped \(missing) missing or unreadable file(s); those remain selected." : "")
            }
        }
    }

}

struct QueueView: View {
    @EnvironmentObject var model: QueueModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading) {
                    Text("Harvester").font(.largeTitle.bold())
                    Text("Find it. Queue it. Keep going.").foregroundStyle(.secondary)
                }
                Spacer()
                Text(model.isDevelopment ? "2.2 DEVELOPMENT" : "2.2").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                if model.running {
                    Button("Stop queue") { model.stop() }
                } else if model.sharedRunnerActive {
                    Text("Queue running").font(.caption).foregroundStyle(.secondary)
                }
            }
            Text("One link per line. Add :Name to give it a name.").font(.headline)
            Text("https://www.youtube.com/watch?v=NCxkLReX_YQ:Jim Jones Preaching In Los Angeles")
                .font(.caption.monospaced()).foregroundStyle(.secondary).textSelection(.enabled)
            TextEditor(text: $model.links).font(.body.monospaced()).frame(height: 84)
                .padding(6).background(.background).clipShape(RoundedRectangle(cornerRadius: 6))
            DisclosureGroup("Options for new submissions") {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Picker("Video", selection: $model.videoPreset) {
                            Text("All-keyframe H.264 · easiest seeking").tag("h264_all_keyframes")
                            Text("Smaller H.264 · regular keyframes").tag("h264_small")
                        }
                        Picker("Audio", selection: $model.audioPreset) {
                            Text("24-bit WAV").tag("wav_48k_24")
                            Text("FLAC · lossless, smaller").tag("flac_48k_24")
                        }
                    }
                    HStack {
                        Text("Clip range")
                        TextField("Start (0:00)", text: $model.trimStart).frame(width: 120)
                        TextField("End (optional)", text: $model.trimEnd).frame(width: 140)
                        Button("Full video") { model.trimStart = ""; model.trimEnd = "" }
                    }
                    Text("Applies to each new link or file. Full sources still download; source limits from Settings apply. WAV uses about 17 MB/minute; video size varies.")
                        .font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Button("Choose Chromatron…") { model.chooseChromatron() }
                        if let app = model.chromatron { Text(app.lastPathComponent).font(.caption) }
                        Spacer()
                        Text(model.freeSpace).font(.caption).foregroundStyle(.secondary)
                        Button("Refresh space") { model.updateFreeSpace() }
                    }
                }.padding(.top, 8)
            }.onAppear { model.updateFreeSpace() }
            HStack {
                Spacer()
                Button("Add files…") { Task { await model.chooseFiles() } }
                Button("Add to queue") {
                    Task { await model.submitDraft(startImmediately: false) }
                }.disabled(model.adding || model.links.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Button("Harvest") {
                    Task { await model.submitDraft(startImmediately: true) }
                }.buttonStyle(.borderedProminent)
                    .keyboardShortcut(.return, modifiers: .command)
                    .disabled(model.adding)
            }
            Text("Harvest starts now. You can keep adding to the queue while it runs.")
                .font(.caption).foregroundStyle(.secondary)
            Text(model.message).font(.callout).foregroundStyle(.secondary)
            HStack {
                Text("Save to: \(model.output.path)").font(.caption).lineLimit(1).truncationMode(.middle)
                Spacer()
                Button("Choose folder…") { model.chooseOutput() }.disabled(model.running || model.sharedRunnerActive)
            }
            ForEach(model.pausedSources, id: \.self) { source in
                HStack {
                    Text("\(source.capitalized) paused — check source access before retrying.")
                    Spacer()
                    Button("Resume source") { Task { await model.resume(source) } }
                }.font(.callout).foregroundStyle(.orange)
            }
            Divider()
            if model.jobs.isEmpty {
                Spacer()
                Text("Your next finds go here.").font(.title2).frame(maxWidth: .infinity)
                Text("Paste an individual public media page, a direct file link, or add a local file.\nSource support varies. Instagram account setup is still in development.")
                    .multilineTextAlignment(.center).foregroundStyle(.secondary).frame(maxWidth: .infinity)
                Spacer()
            } else {
                HStack {
                    Button("Select unsent") {
                        model.selectedVideos = Set(model.completedVideos.filter { !model.wasSent($0) }.map(\.id))
                    }
                    Button("Select all videos") { model.selectedVideos = Set(model.completedVideos.map(\.id)) }
                    Button("Clear") { model.selectedVideos.removeAll() }.disabled(model.selectedVideos.isEmpty)
                    Text("\(model.selectedVideos.count) selected").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button(model.sendingToChromatron ? "Sending…" : "Send selected to Chromatron") {
                        model.sendToChromatron(model.completedVideos.filter { model.selectedVideos.contains($0.id) })
                    }.disabled(model.selectedVideos.isEmpty || model.sendingToChromatron)
                }
                List(model.jobs) { job in
                    HStack(alignment: .top, spacing: 12) {
                        if job.state == "complete", job.videoPath != nil {
                            Toggle("Select \(job.title)", isOn: Binding(
                                get: { model.selectedVideos.contains(job.id) },
                                set: { if $0 { model.selectedVideos.insert(job.id) } else { model.selectedVideos.remove(job.id) } }
                            )).toggleStyle(.checkbox).labelsHidden()
                                .disabled(model.sendingToChromatron)
                        }
                        Image(systemName: job.state == "complete" ? "checkmark.circle.fill" : "film")
                            .foregroundStyle(job.state == "complete" ? .green : .secondary)
                        VStack(alignment: .leading, spacing: 5) {
                            Text(job.title).font(.headline).textSelection(.enabled)
                            Text("\(job.sourceLabel) · \(job.status)").font(.caption).foregroundStyle(.secondary)
                            if model.wasSent(job) {
                                Label("Sent to Chromatron", systemImage: "paperplane.fill")
                                    .font(.caption).foregroundStyle(.secondary)
                                    .help("macOS accepted the handoff. This does not indicate processing has finished in Chromatron.")
                            }
                            if let options = job.options, !options.description.isEmpty { Text(options.description).font(.caption).foregroundStyle(.secondary) }
                            if job.active, let progress = job.progress, let label = job.progressLabel {
                                ProgressView(value: progress).frame(maxWidth: 300)
                                Text("\(label) · \(Int(progress * 100))% of this stage").font(.caption).foregroundStyle(.secondary)
                            }
                            if let size = job.outputBytes { Text(ByteCountFormatter.string(fromByteCount: size, countStyle: .file)).font(.caption).foregroundStyle(.secondary) }
                            if let error = job.error { Text(error).font(.caption).foregroundStyle(.orange) }
                        }
                        Spacer()
                        if let output = job.outputPath, job.state == "complete" {
                            VStack(alignment: .trailing, spacing: 6) {
                                HStack {
                                    if job.videoPath != nil {
                                        Button("Open video") { model.openVideo(job) }
                                        Button("Preview") { model.previewing = job }
                                    }
                                    Button("Show bundle") { NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: output)]) }
                                }
                                if job.videoPath != nil {
                                    Button(model.wasSent(job) ? "Send again" : "Send to Chromatron") { model.sendToChromatron([job]) }
                                        .disabled(model.sendingToChromatron)
                                }
                            }
                        }
                        if job.state == "queued" || job.retryable {
                            Button("Name…") { model.newName = job.name ?? ""; model.renaming = job }
                        }
                        if job.retryable { Button("Retry") { Task { await model.edit("retry", job: job) } } }
                        if job.active || job.state == "queued" {
                            Button("Cancel") { Task { await model.edit("cancel", job: job) } }
                        }
                    }.padding(.vertical, 8)
                }.listStyle(.plain)
            }
        }.padding(24).frame(minWidth: 840, minHeight: 620)
            .onReceive(Timer.publish(every: 1, on: .main, in: .common).autoconnect()) { _ in Task { await model.refresh() } }
            .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in model.stop() }
            .sheet(item: $model.previewing) { job in PreviewSheet(job: job) }
            .sheet(item: $model.renaming) { job in
                VStack(alignment: .leading, spacing: 16) {
                    Text("Name this harvest").font(.headline)
                    TextField("Bundle name", text: $model.newName)
                    HStack {
                        Button("Cancel") { model.renaming = nil }
                        Spacer()
                        Button("Save") { Task { await model.edit("rename", job: job, name: model.newName); model.renaming = nil } }
                            .keyboardShortcut(.defaultAction)
                    }
                }.padding(24).frame(width: 380)
            }
    }
}

struct HarvestSettings: View {
    @AppStorage("maxDurationMinutes") private var minutes = 60
    @AppStorage("maxSourceMB") private var megabytes = 500
    var body: some View {
        Form {
            TextField("Maximum source duration (minutes)", value: $minutes, format: .number)
                .onChange(of: minutes) { minutes = min(360, max(1, $0)) }
            Stepper("Maximum source duration: \(minutes) minutes", value: $minutes, in: 1...360, step: 1)
            TextField("Maximum download size (MB)", value: $megabytes, format: .number)
                .onChange(of: megabytes) { megabytes = min(5120, max(1, $0)) }
            Stepper("Maximum download size: \(megabytes) MB", value: $megabytes, in: 1...5120, step: 1)
            Text("Defaults: 60 minutes and 500 MB. Maximum: 6 hours and 5 GB per source. These limits apply to the full source, even when trimming.")
                .font(.caption).foregroundStyle(.secondary)
            Text("Changes apply the next time you start the queue. Stop the queue first if you want to apply them to pending items. All-keyframe video and WAV output can be much larger than the download.")
                .font(.caption).foregroundStyle(.secondary)
            Button("Restore defaults") { minutes = 60; megabytes = 500 }
        }.padding(24).frame(width: 510)
    }
}

final class HarvesterAppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Refresh the running Dock icon after replacing a locally installed build.
        if let url = Bundle.main.url(forResource: "Harvester", withExtension: "icns"),
           let icon = NSImage(contentsOf: url) {
            NSApplication.shared.applicationIconImage = icon
        }
    }
}

@main struct HarvesterApp: App {
    @NSApplicationDelegateAdaptor(HarvesterAppDelegate.self) private var delegate
    @StateObject private var model = QueueModel()
    var body: some Scene {
        WindowGroup(Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "Harvester") {
            QueueView().environmentObject(model)
                .onOpenURL { url in Task { await model.receiveBrowserSubmission(url) } }
        }
        Settings { HarvestSettings() }
    }
}

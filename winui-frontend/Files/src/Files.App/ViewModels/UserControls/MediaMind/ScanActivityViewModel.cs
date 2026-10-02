// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Services.MediaMind;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using System.Collections.Concurrent;
using System.Text.Json;

namespace Files.App.ViewModels.UserControls.MediaMind
{
	// MediaMind: what the engine is doing right now, in plain sentences, on the page
	// itself. The Status centre card showed "0 items/s, Discovering items…" while a
	// scan was working, which reads as stalled; this strip states the phase, the counts,
	// the file being processed, and — when one file takes long — that it is still alive.
	public sealed partial class ScanActivityViewModel : ObservableObject
	{
		private static readonly TimeSpan FinishedLinger = TimeSpan.FromSeconds(12);

		private readonly ConcurrentDictionary<string, string> libraryNames = new();
		private readonly DispatcherQueueTimer? timer;

		public ObservableCollection<ScanJobRowViewModel> Rows { get; } = [];

		// Jobs a page is showing on its own activity card (TeachPage): not doubled here. The page
		// removes its entry when the user leaves, and the strip takes the job over.
		public static readonly ConcurrentDictionary<string, bool> ShownOnPage = new();

		// True while any job is still running (not just finished and lingering on the strip).
		public bool IsBusy => Rows.Any(r => !r.IsFinished);

		public Visibility StripVisibility => Rows.Count > 0 ? Visibility.Visible : Visibility.Collapsed;

		public ScanActivityViewModel(IMediaMindEngineService engine)
		{
			engine.JobUpdated += (_, job) => MainWindow.Instance.DispatcherQueue.TryEnqueue(() => OnJobUpdated(job));

			timer = MainWindow.Instance.DispatcherQueue.CreateTimer();
			timer.Interval = TimeSpan.FromSeconds(1);
			timer.Tick += (_, _) => Tick();
			timer.Start();
		}

		private void OnJobUpdated(JobSnapshot job)
		{
			var row = Rows.FirstOrDefault(r => r.JobId == job.Id);
			if (ShownOnPage.ContainsKey(job.Id))
			{
				if (row is not null)
					Dismiss(row);
				return;
			}
			if (row is null)
			{
				// A job that ended before anything was shown needs no card.
				if (job.State is "succeeded" or "failed" or "cancelled" && job.Type != "faces")
					return;

				row = new ScanJobRowViewModel(job.Id, job.LibraryId, JobTitle(job.Type), LibraryName(job.LibraryId));
				Rows.Add(row);
				OnPropertyChanged(nameof(StripVisibility));
			}

			row.Update(job);
		}

		private void Tick()
		{
			foreach (var row in Rows.ToList())
			{
				row.Tick();
				// A finished scan that found duplicates stays until the user reviews or closes it.
				if (row.IsFinished && !row.IsFailed && row.DuplicateGroups == 0 && DateTimeOffset.UtcNow - row.FinishedAt > FinishedLinger)
					Dismiss(row);
			}
		}

		public void Dismiss(ScanJobRowViewModel row)
		{
			Rows.Remove(row);
			OnPropertyChanged(nameof(StripVisibility));
		}

		private static string JobTitle(string jobType) => jobType switch
		{
			"faces" => "MediaMind_JobType_Faces".GetLocalizedResource(),
			"dedupe" => "MediaMind_JobType_Dedupe".GetLocalizedResource(),
			"organize-execute" => "MediaMind_JobType_Organize".GetLocalizedResource(),
			"people-move" => "MediaMind_JobRunning_PeopleMove".GetLocalizedResource(),
			"people-move-plan" => "MediaMind_JobRunning_MovePlan".GetLocalizedResource(),
			"teach-sort" => "MediaMind_JobRunning_Sort".GetLocalizedResource(),
			"auto-file" => "MediaMind_JobRunning_AutoFile".GetLocalizedResource(),
			"dedupe-execute" => "MediaMind_JobRunning_RemoveCopies".GetLocalizedResource(),
			"global-move-execute" => "MediaMind_JobRunning_PeopleMove".GetLocalizedResource(),
			// Never a raw code on screen.
			_ => "MediaMind_JobRunning_Other".GetLocalizedResource(),
		};

		// The folder's name is looked up once; the row shows the id-less title until it arrives.
		private string LibraryName(string libraryId)
		{
			if (libraryNames.TryGetValue(libraryId, out var name))
				return name;

			_ = LoadLibraryNamesAsync();
			return string.Empty;
		}

		private async Task LoadLibraryNamesAsync()
		{
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
					return;

				foreach (var library in await engine.Api.Libraries.ListAsync())
					libraryNames[library.Id] = library.Name;

				await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() =>
				{
					foreach (var row in Rows)
						row.LibraryName = NameOf(row.LibraryId);
				});
			}
			// Best-effort: the title just stays without the folder name.
			catch (Exception)
			{
			}
		}

		public string? NameOf(string libraryId)
			=> libraryNames.TryGetValue(libraryId, out var name) ? name : null;
	}

	// One running (or just finished) job, worded for a person.
	public sealed partial class ScanJobRowViewModel : ObservableObject
	{
		private readonly string jobTitle;
		private JobSnapshot? last;
		private string? lastKey;
		private DateTimeOffset lastChange = DateTimeOffset.UtcNow;

		public string JobId { get; }

		public DateTimeOffset FinishedAt { get; private set; } = DateTimeOffset.MaxValue;

		public bool IsFinished { get; private set; }

		public bool IsFailed { get; private set; }

		public string JobType { get; private set; } = string.Empty;

		// Jobs that stop cleanly: scans only read files (a stopped scan saves nothing), and a
		// stopped move puts back what it already moved. Deleting and organizing have no undo on a
		// stop yet, so they don't offer one.
		private static readonly HashSet<string> Cancellable = ["faces", "dedupe", "teach-sort", "people-move-plan", "people-move"];

		public bool IsMove => JobType == "people-move";

		private bool cancelRequested;

		public Visibility CancelVisibility
			=> !IsFinished && !cancelRequested && Cancellable.Contains(JobType) ? Visibility.Visible : Visibility.Collapsed;

		public void MarkCancelling()
		{
			cancelRequested = true;
			PhaseText = (IsMove ? "MediaMind_JobStoppingMove" : "MediaMind_JobStopping").GetLocalizedResource();
			DetailText = string.Empty;
			OnPropertyChanged(nameof(CancelVisibility));
		}

		public string LibraryId { get; }

		public ScanJobRowViewModel(string jobId, string libraryId, string jobTitle, string libraryName)
		{
			JobId = jobId;
			LibraryId = libraryId;
			this.jobTitle = jobTitle;
			LibraryName = libraryName;
			title = BuildTitle();
		}

		private string? libraryName;
		public string? LibraryName
		{
			get => libraryName;
			set
			{
				if (SetProperty(ref libraryName, value))
					Title = BuildTitle();
			}
		}

		private string BuildTitle()
			=> string.IsNullOrEmpty(LibraryName)
				? jobTitle
				: string.Format("MediaMind_ScanTitle".GetLocalizedResource(), jobTitle, LibraryName);

		private string title;
		public string Title
		{
			get => title;
			private set => SetProperty(ref title, value);
		}

		private string phaseText = string.Empty;
		public string PhaseText
		{
			get => phaseText;
			private set => SetProperty(ref phaseText, value);
		}

		private string countersText = string.Empty;
		public string CountersText
		{
			get => countersText;
			private set => SetProperty(ref countersText, value);
		}

		private string detailText = string.Empty;
		public string DetailText
		{
			get => detailText;
			private set
			{
				if (SetProperty(ref detailText, value))
					OnPropertyChanged(nameof(DetailVisibility));
			}
		}

		public Visibility DetailVisibility => string.IsNullOrEmpty(DetailText) ? Visibility.Collapsed : Visibility.Visible;

		private string heartbeatText = string.Empty;
		public string HeartbeatText
		{
			get => heartbeatText;
			private set
			{
				if (SetProperty(ref heartbeatText, value))
					OnPropertyChanged(nameof(HeartbeatVisibility));
			}
		}

		public Visibility HeartbeatVisibility => string.IsNullOrEmpty(HeartbeatText) ? Visibility.Collapsed : Visibility.Visible;

		private double progress;
		public double Progress
		{
			get => progress;
			private set => SetProperty(ref progress, value);
		}

		private bool isIndeterminate = true;
		public bool IsIndeterminate
		{
			get => isIndeterminate;
			private set => SetProperty(ref isIndeterminate, value);
		}

		public Visibility ProgressVisibility => IsFinished ? Visibility.Collapsed : Visibility.Visible;

		public Visibility DismissVisibility => IsFailed || DuplicateGroups > 0 || IsFinished && cancelRequested ? Visibility.Visible : Visibility.Collapsed;

		// Sets of copies the people scan's first stage found (result["duplicates"]["groups"]).
		public int DuplicateGroups { get; private set; }

		public Visibility ReviewDuplicatesVisibility => DuplicateGroups > 0 ? Visibility.Visible : Visibility.Collapsed;

		public string ReviewDuplicatesText => string.Format("MediaMind_ScanReviewDuplicates".GetLocalizedResource(), DuplicateGroups);

		private static int DuplicateGroupsIn(JobSnapshot job)
			=> job.Result is not null && job.Result.TryGetValue("duplicates", out var value)
				&& value is JsonElement { ValueKind: JsonValueKind.Object } d
				&& d.TryGetProperty("groups", out var groups) && groups.TryGetInt32(out var n) ? n : 0;

		public void Update(JobSnapshot job)
		{
			last = job;
			if (JobType != job.Type)
			{
				JobType = job.Type;
				OnPropertyChanged(nameof(CancelVisibility));
			}

			// Anything that moves counts as alive; the heartbeat only speaks when nothing does.
			var key = $"{job.Phase}|{job.Detail}|{job.Done}";
			if (key != lastKey)
			{
				lastKey = key;
				lastChange = DateTimeOffset.UtcNow;
			}

			var stats = job.Stats;
			CountersText = stats is not null && stats.TryGetValue("faces", out var faces)
				? string.Format("MediaMind_ScanCounters".GetLocalizedResource(), faces, stats.GetValueOrDefault("unreadable"))
				: string.Empty;

			switch (job.State)
			{
				case "succeeded":
					DuplicateGroups = DuplicateGroupsIn(job);
					Finish(false, string.Format(
						"MediaMind_ScanFinished".GetLocalizedResource(),
						stats?.GetValueOrDefault("files") ?? 0,
						stats?.GetValueOrDefault("faces") ?? 0,
						stats?.GetValueOrDefault("unreadable") ?? 0));
					OnPropertyChanged(nameof(ReviewDuplicatesVisibility));
					OnPropertyChanged(nameof(ReviewDuplicatesText));
					return;
				case "failed":
					Finish(true, string.Format("MediaMind_ScanStopped".GetLocalizedResource(), job.Error));
					return;
				case "cancelled":
					Finish(false, CancelledMessage(job));
					return;
			}

			PhaseText = job.State == "queued" ? "MediaMind_ScanQueued".GetLocalizedResource() : PhaseSentence(job);
			DetailText = string.IsNullOrEmpty(job.Detail) || job.Phase is "scanning" or "reading"
				? string.Empty
				: string.Format("MediaMind_ScanNow".GetLocalizedResource(), job.Detail);

			var counted = job.Total > 0 && job.Phase is not "scanning";
			IsIndeterminate = !counted;
			Progress = counted ? Math.Min(100d, job.Done * 100d / job.Total) : 0;
			OnPropertyChanged(nameof(ProgressVisibility));
		}

		// What a stop left behind, in plain words: nothing for a scan, the files put back for a move.
		private static string CancelledMessage(JobSnapshot job)
		{
			if (job.Type != "people-move")
				return "MediaMind_JobStoppedNothingChanged".GetLocalizedResource();
			var back = job.Result is not null && job.Result.TryGetValue("rolled_back", out var value) && value is JsonElement element
				&& element.TryGetInt32(out var n) ? n : 0;
			return back > 0
				? string.Format("MediaMind_JobStoppedPutBack".GetLocalizedResource(), back)
				: "MediaMind_JobStoppedNothingMoved".GetLocalizedResource();
		}

		private void Finish(bool failed, string message)
		{
			IsFinished = true;
			IsFailed = failed;
			FinishedAt = DateTimeOffset.UtcNow;
			PhaseText = message;
			DetailText = string.Empty;
			HeartbeatText = string.Empty;
			IsIndeterminate = false;
			Progress = 100;
			OnPropertyChanged(nameof(ProgressVisibility));
			OnPropertyChanged(nameof(DismissVisibility));
			OnPropertyChanged(nameof(CancelVisibility));
		}

		private static string PhaseSentence(JobSnapshot job)
		{
			string F(string key, params object[] args) => string.Format($"MediaMind_ScanPhase_{key}".GetLocalizedResource(), args);

			return job.Phase switch
			{
				"scanning" => F("scanning", string.IsNullOrEmpty(job.Detail) ? $"{job.Done} files found so far" : job.Detail),
				"reading" => F("reading", job.Done, job.Total),
				"hashing" => F("hashing", job.Done, job.Total),
				"detecting" => F("detecting", job.Done, job.Total),
				"retrying" => F("retrying", job.Done, job.Total),
				"clustering" => F("clustering"),
				"saving" => F("saving"),
				"sorting" => F("sorting"),
				"checking" when !string.IsNullOrEmpty(job.Detail) && job.Type is "people-move" or "people-move-plan" or "teach-sort"
					=> F("checkingFolders", job.Done, job.Total),
				"checking" => F("checking", job.Done, job.Total),
				"comparing" => F("comparing", job.Done, job.Total),
				"moving" => F("moving", job.Done, job.Total),
				"deleting" => F("deleting", job.Done, job.Total),
				"undoing" => F("undoing", job.Done, job.Total),
				"reviewable" => F("reviewable"),
				"duplicates" => job.Total > 0 ? F("duplicates", job.Done, job.Total) : F("duplicatesStart"),
				// An unmapped phase still reads as a sentence, never as a raw code with "0 of 0".
				_ when job.Total > 0 => F("other", job.Phase, job.Done, job.Total),
				_ => job.Phase,
			};
		}

		// Once a second: a file that takes long says so, instead of the strip looking frozen.
		public void Tick()
		{
			if (IsFinished || last is null)
				return;

			var quiet = (DateTimeOffset.UtcNow - lastChange).TotalSeconds;
			HeartbeatText = quiet >= 10 && last.Phase is "hashing" or "detecting" or "retrying"
				? string.Format("MediaMind_ScanStillWorking".GetLocalizedResource(), (int)quiet)
				: string.Empty;
		}
	}
}

// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Services.MediaMind;
using Files.App.ViewModels.UserControls.MediaMind;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;

namespace Files.App.ViewModels.People
{
	// The activity card: what a long action on this page is doing right now, where the user
	// clicked. Choosing a folder, building a move plan, moving, sorting and reloading could each
	// take a minute on a network drive behind a bare spinner (2026-09-27). The card says what is
	// happening, how far along it is, the file or folder being worked on, and how long it has
	// taken. It only appears when an action is still running after ActivityDelay, so quick
	// actions don't flash it. Engine jobs followed here are kept off the bottom strip meanwhile
	// (ScanActivityViewModel.ShownOnPage) and go back to it when the user leaves the page.
	public sealed partial class TeachPageViewModel
	{
		private static readonly TimeSpan ActivityDelay = TimeSpan.FromMilliseconds(400);

		private DispatcherQueueTimer? activityTimer;
		private DateTimeOffset activityStarted;
		private int activityDepth;
		private string? activityJobId;

		// A stopped move puts back what it moved; the page asks before stopping one.
		public bool ActivityJobIsMove { get; private set; }
		private bool activityCancelable;
		private bool activityCancelRequested;

		private bool activityOpen;
		public Visibility ActivityVisibility => activityOpen ? Visibility.Visible : Visibility.Collapsed;

		private string activityTitle = string.Empty;
		public string ActivityTitle
		{
			get => activityTitle;
			private set => SetProperty(ref activityTitle, value);
		}

		private string activityDetail = string.Empty;
		public string ActivityDetail
		{
			get => activityDetail;
			private set => SetProperty(ref activityDetail, value);
		}

		private string activityCounts = string.Empty;
		public string ActivityCounts
		{
			get => activityCounts;
			private set => SetProperty(ref activityCounts, value);
		}

		private string activityElapsed = string.Empty;
		public string ActivityElapsed
		{
			get => activityElapsed;
			private set => SetProperty(ref activityElapsed, value);
		}

		private double activityValue;
		public double ActivityValue
		{
			get => activityValue;
			private set => SetProperty(ref activityValue, value);
		}

		private bool activityIndeterminate = true;
		public bool ActivityIndeterminate
		{
			get => activityIndeterminate;
			private set => SetProperty(ref activityIndeterminate, value);
		}

		public Visibility ActivityCancelVisibility
			=> activityCancelable && !activityCancelRequested ? Visibility.Visible : Visibility.Collapsed;

		// Nested calls (an action, then the reload it triggers) share one card: the outer title stays.
		private void BeginActivity(string title)
		{
			if (activityDepth++ > 0)
				return;
			OnUi(() =>
			{
				activityStarted = DateTimeOffset.UtcNow;
				ActivityTitle = title;
				ActivityDetail = string.Empty;
				ActivityCounts = string.Empty;
				ActivityElapsed = string.Empty;
				ActivityIndeterminate = true;
				ActivityValue = 0;
				if (activityTimer is null)
				{
					activityTimer = MainWindow.Instance.DispatcherQueue.CreateTimer();
					activityTimer.Interval = TimeSpan.FromMilliseconds(250);
					activityTimer.Tick += (_, _) => ActivityTick();
				}
				activityTimer.Start();
			});
		}

		private void ActivityTick()
		{
			var elapsed = DateTimeOffset.UtcNow - activityStarted;
			if (!activityOpen && elapsed >= ActivityDelay)
			{
				activityOpen = true;
				OnPropertyChanged(nameof(ActivityVisibility));
			}
			ActivityElapsed = elapsed.TotalSeconds < 1 ? string.Empty
				: elapsed.TotalHours >= 1 ? elapsed.ToString(@"h\:mm\:ss") : elapsed.ToString(@"m\:ss");
		}

		// `unit` names what is counted ("folders", "files"); a zero total shows the moving bar.
		private void ReportActivity(string detail, long done = 0, long total = 0, string? unit = null)
			=> OnUi(() =>
			{
				ActivityDetail = detail;
				ActivityIndeterminate = total <= 0;
				ActivityValue = total > 0 ? Math.Min(100d, done * 100d / total) : 0;
				ActivityCounts = total > 0
					? string.Format(Strings.MediaMind_ActivityCounts.GetLocalizedResource(), done.ToString("N0"), total.ToString("N0"), unit ?? string.Empty).TrimEnd()
					: string.Empty;
			});

		private void EndActivity()
		{
			if (activityDepth == 0 || --activityDepth > 0)
				return;
			OnUi(() =>
			{
				activityTimer?.Stop();
				activityOpen = false;
				activityCancelable = false;
				activityCancelRequested = false;
				OnPropertyChanged(nameof(ActivityVisibility));
				OnPropertyChanged(nameof(ActivityCancelVisibility));
			});
		}

		private static void OnUi(Action action)
		{
			if (MainWindow.Instance.DispatcherQueue.HasThreadAccess)
				action();
			else
				MainWindow.Instance.DispatcherQueue.TryEnqueue(() => action());
		}

		// Follows an engine job to its end, putting its progress on the card. With `cancelable`,
		// the card's Cancel asks the engine to stop (a move stops between two files; nothing is
		// left half-copied). Returns the last snapshot.
		private async Task<JobSnapshot> FollowJobAsync(MediaMindApiClient api, JobSnapshot job, bool cancelable)
		{
			activityJobId = job.Id;
			ActivityJobIsMove = job.Type == "people-move";
			ScanActivityViewModel.ShownOnPage[job.Id] = true;
			OnUi(() =>
			{
				activityCancelable = cancelable;
				OnPropertyChanged(nameof(ActivityCancelVisibility));
			});
			try
			{
				while (true)
				{
					DescribeJob(job);
					if (job.State is "succeeded" or "failed" or "cancelled")
						return job;
					await Task.Delay(500);
					job = await api.Scans.GetAsync(LibraryId, job.Id);
				}
			}
			finally
			{
				ScanActivityViewModel.ShownOnPage.TryRemove(job.Id, out _);
				activityJobId = null;
			}
		}

		public async Task CancelActivityAsync()
		{
			if (activityJobId is not { } jobId || activityCancelRequested || await ApiAsync() is not { } api)
				return;
			activityCancelRequested = true;
			OnPropertyChanged(nameof(ActivityCancelVisibility));
			ReportActivity((ActivityJobIsMove ? Strings.MediaMind_JobStoppingMove : Strings.MediaMind_ActivityStopping).GetLocalizedResource());
			try
			{
				await api.Scans.CancelAsync(LibraryId, jobId);
			}
			// Already finished: the follow loop reports how it ended.
			catch (Exception)
			{
			}
		}

		private void DescribeJob(JobSnapshot job)
		{
			if (activityCancelRequested)
				return;
			string F(string key, params object[] args) => string.Format($"MediaMind_Activity_{key}".GetLocalizedResource(), args);
			var what = job.Detail ?? string.Empty;
			switch (job.State == "queued" ? "queued" : job.Phase)
			{
				case "queued":
					ReportActivity(F("queued"));
					break;
				case "checking":
					ReportActivity(what.Length > 0 ? F("checking", what) : F("checkingStart"), job.Done, job.Total, F("folders"));
					break;
				case "comparing":
					ReportActivity(F("comparing", what), job.Done, job.Total, F("files"));
					break;
				case "moving":
					ReportActivity(F("moving", what), job.Done, job.Total, F("files"));
					break;
				case "sorting":
					ReportActivity(F("sorting"));
					break;
				default:
					ReportActivity(what, job.Done, job.Total);
					break;
			}
		}

		// Pages follow their own jobs; when the user leaves, the bottom strip takes them over.
		private void ReleaseJobsToStrip()
		{
			if (activityJobId is { } id)
				ScanActivityViewModel.ShownOnPage.TryRemove(id, out _);
		}

		// A job's result (a JSON object of JsonElements) read back as one of the API's records.
		private static T? ResultAs<T>(JobSnapshot job, JsonTypeInfo<T> info) where T : class
		{
			if (job.Result is null)
				return null;
			using var buffer = new SystemIO.MemoryStream();
			using (var writer = new Utf8JsonWriter(buffer))
			{
				writer.WriteStartObject();
				foreach (var pair in job.Result)
				{
					writer.WritePropertyName(pair.Key);
					if (pair.Value is JsonElement element)
						element.WriteTo(writer);
					else
						writer.WriteNullValue();
				}
				writer.WriteEndObject();
			}
			return JsonSerializer.Deserialize(buffer.ToArray(), info);
		}
	}
}

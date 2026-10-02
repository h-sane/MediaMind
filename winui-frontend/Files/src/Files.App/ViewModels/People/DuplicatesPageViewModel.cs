// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Services.MediaMind;
using System.Text.Json;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Files.App.ViewModels.People
{
	// MediaMind: "Duplicates" — copies of the same photo or video in a scanned library, one set
	// at a time: the copies side by side, one marked to keep, the others go (Recycle Bin where
	// the drive has one; every removal is in the engine's manifest). Found by every Scan for
	// People (its first stage) or by Find duplicates here. Backend: api/routes/duplicates.py.
	// Navigated via "duplicates:{libraryId}:{groupId}:{under}" or "duplicates:::{folderPath}".
	public sealed partial class DuplicatesPageViewModel : ObservableObject
	{
		public string LibraryId { get; }

		public string UnscannedFolder { get; }

		private readonly string under;
		private readonly long? focusGroupId;
		private string libraryRoot = string.Empty;
		private bool recycleBin = true;
		private string? scanJobId;

		// Every set found; Groups is the part the Exact / Look alike switch shows.
		private List<DuplicateGroupViewModel> allGroups = [];

		public ObservableCollection<DuplicateGroupViewModel> Groups { get; } = [];

		private bool showExact = true;
		public bool ShowExact
		{
			get => showExact;
			set
			{
				if (SetProperty(ref showExact, value))
				{
					OnPropertyChanged(nameof(SelectAllVisibility));
					ApplyMode();
				}
			}
		}

		public string ExactLabel => string.Format(Strings.MediaMind_DupModeExact.GetLocalizedResource(), allGroups.Count(g => g.IsExact));

		public string LookAlikeLabel => string.Format(Strings.MediaMind_DupModeLookAlike.GetLocalizedResource(), allGroups.Count(g => !g.IsExact));

		// Exact copies can be cleared in bulk: identical files, nothing to judge.
		public Visibility SelectAllVisibility => ShowExact && Groups.Count > 1 ? Visibility.Visible : Visibility.Collapsed;

		private void ApplyMode()
		{
			Groups.Clear();
			foreach (var g in allGroups.Where(g => g.IsExact == ShowExact))
				Groups.Add(g);
			OnPropertyChanged(nameof(CountText));
			OnPropertyChanged(nameof(SelectAllVisibility));
			Select(Groups.Count > 0 ? [Groups[0]] : []);
		}

		private void RefreshLabels()
		{
			OnPropertyChanged(nameof(ExactLabel));
			OnPropertyChanged(nameof(LookAlikeLabel));
			OnPropertyChanged(nameof(CountText));
			OnPropertyChanged(nameof(SelectAllVisibility));
		}

		// The page mirrors the list's selection here; the first selected set is shown.
		private IReadOnlyList<DuplicateGroupViewModel> selection = [];

		public void Select(IReadOnlyList<DuplicateGroupViewModel> groups)
		{
			selection = groups;
			Current = groups.Count > 0 ? groups[0] : null;
			OnPropertyChanged(nameof(KeepText));
		}

		private List<DuplicateGroupViewModel> Targets()
			=> selection.Count > 0 ? selection.Where(Groups.Contains).ToList() : Current is null ? [] : [Current];

		private DuplicateGroupViewModel? current;
		public DuplicateGroupViewModel? Current
		{
			get => current;
			private set
			{
				if (SetProperty(ref current, value))
				{
					current?.Members.ToList().ForEach(m => m.EnsureThumbnail(768));
					OnPropertyChanged(nameof(CanDecide));
					OnPropertyChanged(nameof(MatchText));
					OnPropertyChanged(nameof(KeepText));
					OnPropertyChanged(nameof(CompareVisibility));
					OnPropertyChanged(nameof(DoneVisibility));
				}
			}
		}

		public bool CanDecide => Current is not null && !IsLoading;

		public string MatchText => Current is null
			? string.Empty
			: (Current.IsExact ? Strings.MediaMind_DupExactExplain : Strings.MediaMind_DupLookAlikeExplain).GetLocalizedResource();

		public string KeepText => Current is null
			? string.Empty
			: selection.Count > 1
				? string.Format(Strings.MediaMind_DupKeepMany.GetLocalizedResource(), selection.Sum(g => g.Members.Count - 1), selection.Count)
				: string.Format(Strings.MediaMind_DupKeep.GetLocalizedResource(), Current.Keeper.Number, Current.Members.Count - 1);

		public string CountText => string.Format(Strings.MediaMind_DupRemaining.GetLocalizedResource(),
			Groups.Count, Groups.Sum(g => g.Frees).ToSizeString());

		public Visibility CompareVisibility => Current is null ? Visibility.Collapsed : Visibility.Visible;

		public Visibility DoneVisibility => Current is null && !IsLoading && string.IsNullOrEmpty(BlockingText) ? Visibility.Visible : Visibility.Collapsed;

		private string title = Strings.MediaMind_DupTitle.GetLocalizedResource();
		public string Title
		{
			get => title;
			private set => SetProperty(ref title, value);
		}

		private bool isLoading = true;
		public bool IsLoading
		{
			get => isLoading;
			private set
			{
				if (SetProperty(ref isLoading, value))
				{
					OnPropertyChanged(nameof(CanDecide));
					OnPropertyChanged(nameof(IsWorking));
					OnPropertyChanged(nameof(DoneVisibility));
					OnPropertyChanged(nameof(CanScan));
				}
			}
		}

		private bool isScanning;
		public bool IsScanning
		{
			get => isScanning;
			private set
			{
				if (SetProperty(ref isScanning, value))
				{
					OnPropertyChanged(nameof(CanScan));
					OnPropertyChanged(nameof(IsWorking));
				}
			}
		}

		public bool IsWorking => IsScanning || IsLoading;

		public bool CanScan => !IsScanning && !IsLoading && LibraryId.Length + UnscannedFolder.Length > 0;

		// The page cannot show sets at all (no duplicate check yet, engine down): replaces the body.
		private string blockingText = string.Empty;
		public string BlockingText
		{
			get => blockingText;
			private set
			{
				if (SetProperty(ref blockingText, value))
				{
					OnPropertyChanged(nameof(BlockingVisibility));
					OnPropertyChanged(nameof(ContentVisibility));
					OnPropertyChanged(nameof(DoneVisibility));
				}
			}
		}

		public Visibility BlockingVisibility => string.IsNullOrEmpty(BlockingText) ? Visibility.Collapsed : Visibility.Visible;

		public Visibility ContentVisibility => string.IsNullOrEmpty(BlockingText) ? Visibility.Visible : Visibility.Collapsed;

		private string errorText = string.Empty;
		public string ErrorText
		{
			get => errorText;
			private set
			{
				if (SetProperty(ref errorText, value))
					OnPropertyChanged(nameof(ErrorVisibility));
			}
		}

		public Visibility ErrorVisibility => ErrorText.Length > 0 ? Visibility.Visible : Visibility.Collapsed;

		// The one message area (InfoBar) for scans and loading.
		private bool statusOpen;
		public bool StatusOpen
		{
			get => statusOpen;
			set => SetProperty(ref statusOpen, value);
		}

		private string statusMessage = string.Empty;
		public string StatusMessage
		{
			get => statusMessage;
			private set => SetProperty(ref statusMessage, value);
		}

		private InfoBarSeverity statusSeverity = InfoBarSeverity.Informational;
		public InfoBarSeverity StatusSeverity
		{
			get => statusSeverity;
			private set => SetProperty(ref statusSeverity, value);
		}

		public DuplicatesPageViewModel(string libraryId, long? focusGroupId, string under, string unscannedFolder)
		{
			LibraryId = libraryId;
			this.focusGroupId = focusGroupId;
			this.under = under;
			UnscannedFolder = unscannedFolder;
			Engine.JobUpdated += Engine_JobUpdated;
			_ = LoadAsync();
		}

		public void Detach() => Engine.JobUpdated -= Engine_JobUpdated;

		private static IMediaMindEngineService Engine => Ioc.Default.GetRequiredService<IMediaMindEngineService>();

		private async Task<MediaMindApiClient?> ApiAsync()
			=> await Engine.EnsureStartedAsync(CancellationToken.None) ? Engine.Api : null;

		public async Task LoadAsync()
		{
			if (UnscannedFolder.Length > 0)
			{
				Title = string.Format(Strings.MediaMind_DupTitleFor.GetLocalizedResource(), SystemIO.Path.GetFileName(UnscannedFolder.TrimEnd('\\')));
				BlockingText = Strings.MediaMind_DupNotChecked.GetLocalizedResource();
				IsLoading = false;
				return;
			}

			IsLoading = true;
			try
			{
				var api = await ApiAsync();
				if (api is null)
				{
					BlockingText = Strings.MediaMind_TeachEngineDown.GetLocalizedResource();
					return;
				}
				var library = (await api.Libraries.ListAsync()).FirstOrDefault(l => l.Id == LibraryId);
				if (library is not null)
				{
					libraryRoot = library.Path;
					Title = string.Format(Strings.MediaMind_DupTitleFor.GetLocalizedResource(), library.Name);
				}
				DuplicatesOut found;
				try
				{
					found = await api.Duplicates.ListAsync(LibraryId);
				}
				catch (MediaMindApiException ex) when (ex.StatusCode == System.Net.HttpStatusCode.NotFound)
				{
					BlockingText = Strings.MediaMind_DupNotChecked.GetLocalizedResource();
					return;
				}
				recycleBin = (await api.Duplicates.RecycleBinCheckAsync(LibraryId)).RecycleBinSupported;

				// Removals chosen in an earlier, unfinished session are not carried out behind the
				// user's back: they go back to "keep" and are decided again here.
				var stale = found.Groups.SelectMany(g => g.Files).Where(f => f.Resolution == "trash").ToList();
				if (stale.Count > 0)
					await api.Duplicates.ResolveAsync(LibraryId, stale.Select(f => new DuplicateResolution(f.Id, "keep")).ToList());

				BlockingText = string.Empty;
				// Within each kind, the sets that free the most space first.
				allGroups = found.Groups
					.Where(InScope)
					.Select(g => new DuplicateGroupViewModel(LibraryId, libraryRoot, g))
					.OrderByDescending(g => g.Frees)
					.ToList();
				var focus = allGroups.FirstOrDefault(g => g.Group.Id == focusGroupId);
				showExact = focus?.IsExact ?? allGroups.Any(g => g.IsExact);
				OnPropertyChanged(nameof(ShowExact));
				RefreshLabels();
				ApplyMode();
				if (focus is not null)
					Select([focus]);
			}
			catch (MediaMindApiException ex)
			{
				BlockingText = ex.Message;
			}
			catch (Exception)
			{
				BlockingText = Strings.MediaMind_DupLoadFailed.GetLocalizedResource();
			}
			finally
			{
				IsLoading = false;
			}
		}

		// Opened from a subfolder: only sets with at least one copy in it.
		private bool InScope(DuplicateGroup g)
			=> under.Length == 0 || g.Files.Any(f => f.Path.StartsWith(under + "/", StringComparison.OrdinalIgnoreCase));

		// "Find duplicates": a duplicates-only scan (fast; no face work). The page reloads when it ends.
		public async Task ScanAsync()
		{
			if (!CanScan)
				return;
			IsScanning = true;
			try
			{
				var api = await ApiAsync() ?? throw new InvalidOperationException(Strings.MediaMind_ReviewEngineDown.GetLocalizedResource());
				var libraryId = LibraryId.Length > 0 ? LibraryId : (await api.Libraries.AddAsync(Utils.MediaMind.MediaMindPaths.Canonical(UnscannedFolder))).Id;
				var started = await api.Scans.StartAsync(libraryId, "dedupe");
				scanJobId = started.Id;
				ShowStatus(InfoBarSeverity.Informational, Strings.MediaMind_DupScanning.GetLocalizedResource());
				if (LibraryId.Length == 0)
					NavigateToLibrary?.Invoke(libraryId);
				// A small folder can finish before its "done" event could be matched to this id: the
				// page then waited forever (ARIN, 2026-09-27). Follow the job itself until it ends.
				var job = started;
				while (job.State is not ("succeeded" or "failed" or "cancelled") && scanJobId == started.Id)
				{
					await Task.Delay(1000);
					job = await api.Scans.GetAsync(libraryId, started.Id);
				}
				if (scanJobId == started.Id)
					Engine_JobUpdated(null, job);
			}
			catch (Exception ex)
			{
				IsScanning = false;
				ShowStatus(InfoBarSeverity.Error, string.Format(Strings.MediaMind_DupScanFailed.GetLocalizedResource(), ex.Message));
			}
		}

		// Set by the page: a folder that was not a library yet reopens as one once it is registered.
		public Action<string>? NavigateToLibrary { get; set; }

		private void Engine_JobUpdated(object? sender, JobSnapshot job)
		{
			if (job.Id != scanJobId || job.State is not ("succeeded" or "failed" or "cancelled"))
				return;
			MainWindow.Instance.DispatcherQueue.TryEnqueue(async () =>
			{
				IsScanning = false;
				scanJobId = null;
				if (job.State == "failed")
				{
					ShowStatus(InfoBarSeverity.Error, string.Format(Strings.MediaMind_DupScanFailed.GetLocalizedResource(), job.Error));
					return;
				}
				await LoadAsync();
				ShowStatus(InfoBarSeverity.Success, Groups.Count == 0
					? Strings.MediaMind_DupNoneFound.GetLocalizedResource()
					: string.Format(Strings.MediaMind_DupFound.GetLocalizedResource(), Groups.Count));
			});
		}

		private void ShowStatus(InfoBarSeverity severity, string message)
		{
			StatusSeverity = severity;
			StatusMessage = message;
			StatusOpen = true;
		}

		public void ChooseKeeper(int number)
		{
			var member = Current?.Members.FirstOrDefault(m => m.Number == number);
			if (member is null)
				return;
			Current!.ChooseKeeper(member);
			OnPropertyChanged(nameof(KeepText));
			OnPropertyChanged(nameof(CountText));
		}

		public void Skip()
		{
			if (Current is null || Groups.Count < 2)
				return;
			Select([Groups[(Groups.IndexOf(Current) + 1) % Groups.Count]]);
		}

		// Removals run one at a time: the engine checks the expected count of files to remove
		// against its own list, so two overlapping batches would refuse each other.
		private readonly SemaphoreSlim removals = new(1, 1);

		// Keep the chosen copy of each selected set and remove the others. `confirm` shows the
		// delete confirmation (once for the whole batch). The sets leave the list at once and the
		// next one shows; the removal finishes in the background, and sets whose files are still
		// there afterwards come back with the reason.
		public async Task KeepChosenAsync(Func<IReadOnlyList<string>, bool, Task<bool>> confirm)
		{
			var targets = Targets();
			if (targets.Count == 0 || !CanDecide)
				return;
			var remove = targets.SelectMany(g => g.Members.Where(m => !m.IsKeeper)).ToList();
			if (!await confirm(remove.Select(m => m.AbsPath).ToList(), recycleBin))
				return;

			var positions = TakeOut(targets);
			await removals.WaitAsync();
			try
			{
				var api = await ApiAsync() ?? throw new InvalidOperationException(Strings.MediaMind_ReviewEngineDown.GetLocalizedResource());
				await api.Duplicates.ResolveAsync(LibraryId, targets
					.SelectMany(g => g.Members.Select(m => new DuplicateResolution(m.File.Id, m.IsKeeper ? "keep" : "trash")))
					.ToList());
				// A job, so the strip at the bottom counts the removals ("Deleting 40 of 312")
				// instead of a long silent call.
				var job = await api.Duplicates.ExecuteJobAsync(LibraryId, expectedTrashCount: remove.Count, permanent: !recycleBin);
				while (job.State is not ("succeeded" or "failed" or "cancelled"))
				{
					await Task.Delay(700);
					job = await api.Scans.GetAsync(LibraryId, job.Id);
				}
				if (job.State != "succeeded")
					throw new InvalidOperationException(string.IsNullOrEmpty(job.Error) ? job.State : job.Error);
				if (job.Result is not null && job.Result.TryGetValue("ok", out var ok) && ok is JsonElement okElement
					&& okElement.ValueKind == JsonValueKind.False)
				{
					string? reason = null;
					if (job.Result.TryGetValue("errors", out var errors) && errors is JsonElement list && list.ValueKind == JsonValueKind.Array)
						foreach (var e in list.EnumerateArray())
							if (reason is null && e.TryGetProperty("error", out var why))
								reason = why.GetString();
					throw new InvalidOperationException(reason ?? string.Empty);
				}
			}
			catch (Exception ex)
			{
				var failed = targets.Where(g => g.Members.Any(m => !m.IsKeeper && SystemIO.File.Exists(m.AbsPath))).ToList();
				if (failed.Count > 0)
				{
					PutBack(failed, positions);
					ErrorText = string.Format(Strings.MediaMind_DupRemoveFailed.GetLocalizedResource(), ex.Message);
				}
			}
			finally
			{
				removals.Release();
			}
		}

		// "Not duplicates" for every selected set: hidden now and after rescans unless the files change.
		public async Task NotDuplicatesAsync()
		{
			var targets = Targets();
			if (targets.Count == 0 || !CanDecide)
				return;
			var positions = TakeOut(targets);
			var failed = new List<DuplicateGroupViewModel>();
			var reason = string.Empty;
			var api = await ApiAsync();
			foreach (var group in targets)
			{
				try
				{
					if (api is null)
						throw new InvalidOperationException(Strings.MediaMind_ReviewEngineDown.GetLocalizedResource());
					await api.Duplicates.DismissGroupAsync(LibraryId, group.Group.Id);
				}
				catch (Exception ex)
				{
					failed.Add(group);
					reason = ex.Message;
				}
			}
			if (failed.Count > 0)
			{
				PutBack(failed, positions);
				ErrorText = string.Format(Strings.MediaMind_DupDismissFailed.GetLocalizedResource(), reason);
			}
		}

		private Dictionary<DuplicateGroupViewModel, int> TakeOut(IReadOnlyList<DuplicateGroupViewModel> groups)
		{
			ErrorText = string.Empty;
			var positions = groups.ToDictionary(g => g, g => Groups.IndexOf(g));
			var next = Groups.Skip(positions.Values.Max() + 1).FirstOrDefault(g => !groups.Contains(g))
				?? Groups.LastOrDefault(g => !groups.Contains(g));
			foreach (var g in groups)
			{
				Groups.Remove(g);
				allGroups.Remove(g);
			}
			RefreshLabels();
			Select(next is null ? [] : [next]);
			return positions;
		}

		private void PutBack(IReadOnlyList<DuplicateGroupViewModel> groups, Dictionary<DuplicateGroupViewModel, int> positions)
		{
			foreach (var g in groups.OrderBy(g => positions[g]))
			{
				if (allGroups.Contains(g))
					continue;
				allGroups.Add(g);
				if (g.IsExact == ShowExact)
					Groups.Insert(Math.Min(positions[g], Groups.Count), g);
			}
			RefreshLabels();
			if (Current is null && Groups.Count > 0)
				Select([Groups[0]]);
		}
	}
}

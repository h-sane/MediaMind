// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Services.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Files.App.ViewModels.People
{
	// People folders (docs/PEOPLE_FOLDERS_AUTOFILE_PLAN.md): how many files are sorted, a person's
	// own folder and moving their pictures there, and group pictures that need a place. The folder
	// belongs to the name, so it is the same in every scanned folder. Backend:
	// api/routes/people_folders.py.
	public sealed partial class TeachPageViewModel
	{
		// --- counts (files, not faces) ---

		private TeachStats? stats;

		public string StatsText => stats is null ? string.Empty
			: string.Format(Strings.MediaMind_TeachStats.GetLocalizedResource(), stats.Total, stats.Sorted, stats.Unsorted, stats.NoFaces);

		private async Task LoadStatsAsync()
		{
			try
			{
				if (await ApiAsync() is { } api)
					stats = await api.Teach.StatsAsync(LibraryId, SelectedFolder?.Path);
			}
			// Counts are extra: the page works without them.
			catch (Exception)
			{
				stats = null;
			}
			MainWindow.Instance.DispatcherQueue.TryEnqueue(() => OnPropertyChanged(nameof(StatsText)));
		}

		// --- the selected person's folder ---

		private TeachPerson? SelectedPerson
			=> SelectedFilter is { Kind: TeachFilterKind.Person, PersonId: long id } ? lastPeople.FirstOrDefault(p => p.PersonId == id) : null;

		public string PrimaryFolderText => SelectedPerson?.PrimaryLocation ?? Strings.MediaMind_TeachNoFolderYet.GetLocalizedResource();

		public double PrimaryFolderOpacity => SelectedPerson?.PrimaryLocation is null ? 0.7 : 1.0;

		public bool CanMoveFiles => !IsBusy && SelectedPerson?.PrimaryLocation is not null;

		private void OnPersonBarChanged()
		{
			OnPropertyChanged(nameof(PrimaryFolderText));
			OnPropertyChanged(nameof(PrimaryFolderOpacity));
			OnPropertyChanged(nameof(CanMoveFiles));
		}

		public Task SetPrimaryFolderAsync(string path)
		{
			if (SelectedPerson is not { PersonId: long id } person)
				return Task.CompletedTask;
			return RunAsync(string.Format(Strings.MediaMind_ActivitySettingFolder.GetLocalizedResource(), person.Name), async api =>
			{
				var result = await api.Teach.SetPrimaryLocationAsync(LibraryId, id, path);
				ShowStatus(InfoBarSeverity.Success,
					string.Format(Strings.MediaMind_TeachFolderSetTitle.GetLocalizedResource(), person.Name),
					string.Format(Strings.MediaMind_TeachFolderSetMessage.GetLocalizedResource(), result.PrimaryLocation));
			});
		}

		// What Move files would do, for the confirm dialog; null (with the reason shown) if it can't
		// or the user cancelled. Reading every scanned folder can take a minute on a network drive,
		// so it runs as a job and the card names the folder being read.
		public async Task<PersonMovePlan?> GetMovePlanAsync()
		{
			if (IsBusy || SelectedPerson is not { PersonId: long id } person || await ApiAsync() is not { } api)
				return null;
			IsBusy = true;
			BeginActivity(string.Format(Strings.MediaMind_ActivityPlanning.GetLocalizedResource(), person.Name));
			try
			{
				var job = await FollowJobAsync(api, await api.Teach.StartMovePlanAsync(LibraryId, id), cancelable: true);
				if (job.State == "cancelled")
					return null;
				if (job.State != "succeeded" || ResultAs(job, MediaMindJsonContext.Default.PersonMovePlan) is not { } plan)
					throw new InvalidOperationException(string.IsNullOrEmpty(job.Error) ? job.State : job.Error);
				return plan;
			}
			catch (Exception ex)
			{
				ShowStatus(InfoBarSeverity.Error, Strings.MediaMind_TeachActionFailed.GetLocalizedResource(), ex.Message);
				return null;
			}
			finally
			{
				IsBusy = false;
				EndActivity();
			}
		}

		// Starts the move and follows it to the end, so the result shows here and the page reloads.
		public Task MoveFilesAsync(long personId, PersonMovePlan plan)
			=> RunAsync(string.Format(Strings.MediaMind_ActivityMoving.GetLocalizedResource(), plan.Name), async api =>
			{
				// A cancelled move stops between two files; what moved so far stays moved (and undoable).
				var job = await FollowJobAsync(api, await api.Teach.MoveAsync(LibraryId, personId, plan.PlanHash), cancelable: true);
				if (job.State == "failed")
					throw new InvalidOperationException(string.IsNullOrEmpty(job.Error) ? job.State : job.Error);
				if (job.State == "cancelled")
				{
					var back = job.Result is { } c && c.TryGetValue("rolled_back", out var b) && int.TryParse(b?.ToString(), out var nb) ? nb : 0;
					ShowStatus(InfoBarSeverity.Informational, Strings.MediaMind_TeachMoveStoppedTitle.GetLocalizedResource(), back > 0
						? string.Format(Strings.MediaMind_JobStoppedPutBack.GetLocalizedResource(), back)
						: Strings.MediaMind_JobStoppedNothingMoved.GetLocalizedResource());
					return;
				}
				var moved = job.Result is { } r && r.TryGetValue("moved", out var m) && int.TryParse(m?.ToString(), out var n) ? n : plan.Moves;
				Utils.MediaMind.FolderPicker.Remember(plan.PrimaryLocation);
				var waiting = plan.GroupsWaiting > 0
					? " " + string.Format(Strings.MediaMind_TeachGroupsWaiting.GetLocalizedResource(), plan.GroupsWaiting)
					: string.Empty;
				ShowStatus(moved == plan.Moves ? InfoBarSeverity.Success : InfoBarSeverity.Warning,
					string.Format(Strings.MediaMind_TeachMovedTitle.GetLocalizedResource(), moved, plan.Moves, plan.Name),
					string.Format(Strings.MediaMind_TeachMovedMessage.GetLocalizedResource(), plan.PrimaryLocation) + waiting);
			});

		// --- group pictures ---

		public ObservableCollection<TeachGroupItem> Groups { get; } = [];

		public bool IsPlacingGroups => SelectedFilter?.Kind == TeachFilterKind.Groups;

		public Visibility GroupsVisibility => IsPlacingGroups ? Visibility.Visible : Visibility.Collapsed;

		private async Task<List<GroupQuestion>> LoadGroupsAsync(MediaMindApiClient api)
		{
			try
			{
				return await api.Teach.GroupsAsync(LibraryId);
			}
			// Nobody has a folder yet, or the drive is offline: nothing to place.
			catch (Exception)
			{
				return [];
			}
		}

		private void SetGroups(IEnumerable<GroupQuestion> questions)
		{
			// The one on screen stays selected; after an answer, the next one in the list takes its place.
			var index = CurrentGroup is { } current ? Groups.IndexOf(current) : 0;
			var keepId = CurrentGroup?.Question.FileId;
			Groups.Clear();
			foreach (var q in questions.Where(q => InFolder(q.Path)))
				Groups.Add(new TeachGroupItem(LibraryId, q));
			CurrentGroup = Groups.FirstOrDefault(g => g.Question.FileId == keepId)
				?? (Groups.Count > 0 ? Groups[Math.Clamp(index, 0, Groups.Count - 1)] : null);
		}

		// choice: "person" (into `person`'s folder), "new" (a new folder called `folderName`),
		// "existing" (the folder at `folderPath`, already there) or "stay".
		public Task PlaceGroupAsync(TeachGroupItem item, string choice, string? person, string? folderName, bool remember, string? folderPath = null)
			=> RunAsync(Strings.MediaMind_ActivityPlacingGroup.GetLocalizedResource(), async api =>
			{
				var result = await api.Teach.PlaceGroupAsync(LibraryId, new GroupPlaceBody(item.Question.FileId, choice, person, folderName, remember, folderPath));
				Utils.MediaMind.FolderPicker.Remember(folderPath ?? (folderName is not null ? SystemIO.Path.Combine(item.Question.NewFolderParent, folderName) : null));
				var title = choice == "stay"
					? Strings.MediaMind_TeachGroupStayed.GetLocalizedResource()
					: string.Format(Strings.MediaMind_TeachGroupMoved.GetLocalizedResource(), result.Moved);
				ShowStatus(InfoBarSeverity.Success, title, remember
					? string.Format(Strings.MediaMind_TeachGroupRemembered.GetLocalizedResource(), string.Join(", ", item.Question.People))
					: string.Empty);
			});
	}

	public sealed partial class TeachGroupItem : ObservableObject
	{
		public GroupQuestion Question { get; }

		private readonly string libraryId;

		public string FileName => SystemIO.Path.GetFileName(Question.Path);

		public string PeopleText => string.Join(", ", Question.People);

		public string NewFolderHint => string.Format(Strings.MediaMind_TeachGroupNewHint.GetLocalizedResource(), Question.NewFolderParent);

		private BitmapImage? thumbnail;
		public BitmapImage? Thumbnail
		{
			get => thumbnail;
			private set => SetProperty(ref thumbnail, value);
		}

		private bool thumbnailRequested;

		public bool IsVideo => Question.Kind == "video";

		// Folders already where a new group folder would go, shown relative to that place ("OT4").
		public IReadOnlyList<GroupExistingFolder> ExistingFolders { get; }

		// A copy WinUI can bind: an IReadOnlyList from JSON as ItemsSource threw ArgumentException
		// (0x80070057) the moment the Group pictures list drew its first row (2026-09-27).
		public ObservableCollection<GroupFolderOption> Folders { get; }

		public TeachGroupItem(string libraryId, GroupQuestion question)
		{
			this.libraryId = libraryId;
			Question = question;
			Folders = new(question.Folders);
			var parent = question.NewFolderParent.TrimEnd('\\', '/');
			ExistingFolders = (question.ExistingFolders ?? [])
				.Select(p => new GroupExistingFolder(
					p.StartsWith(parent + SystemIO.Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) ? p[(parent.Length + 1)..] : p, p))
				.ToList();
		}

		public async void EnsureThumbnail()
		{
			if (thumbnailRequested)
				return;
			thumbnailRequested = true;
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (engine.Api is not null)
					Thumbnail = await (await engine.Api.Teach.FileThumbnailAsync(libraryId, Question.Path, 192)).ToBitmapAsync();
			}
			// A picture that can't be decoded still gets its row and choices.
			catch (Exception)
			{
			}
		}
	}
}

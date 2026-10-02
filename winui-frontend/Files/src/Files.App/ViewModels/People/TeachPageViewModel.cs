// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Services.MediaMind;
using Files.App.ViewModels.UserControls.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Files.App.ViewModels.People
{
	// MediaMind: "Who's who" — the user picks a few clear faces per person and names
	// them; Sort people now re-sorts every face in this library against those
	// examples (and against examples named in any other library). Backend:
	// api/routes/teach.py. Navigated via "teach:{libraryId}:{under}", or
	// "teach::{folderPath}" when the folder has not been scanned for people yet.
	public sealed partial class TeachPageViewModel : ObservableObject
	{
		public string LibraryId { get; }

		public string UnscannedFolder { get; }

		private List<TeachFaceTileViewModel> allFaces = [];

		public ObservableCollection<TeachFilterItem> Filters { get; } = [];

		public ObservableCollection<TeachFolderOption> Folders { get; } = [];

		public ObservableCollection<string> PersonNames { get; } = [];

		private IReadOnlyList<TeachFaceTileViewModel> visibleFaces = [];
		public IReadOnlyList<TeachFaceTileViewModel> VisibleFaces
		{
			get => visibleFaces;
			private set
			{
				if (SetProperty(ref visibleFaces, value))
				{
					OnPropertyChanged(nameof(GridVisibility));
					OnPropertyChanged(nameof(EmptyVisibility));
					OnPropertyChanged(nameof(ShownText));
				}
			}
		}

		private string libraryPath = string.Empty;

		// The folder being worked on, on disk: this folder, or the subfolder picked in the folder row.
		public string WorkingFolder => libraryPath.Length == 0 ? string.Empty
			: SystemIO.Path.Combine(libraryPath, (SelectedFolder?.Path ?? string.Empty).Replace('/', '\\'));

		private TeachFilterItem? selectedFilter;
		public TeachFilterItem? SelectedFilter
		{
			get => selectedFilter;
			set
			{
				if (value is not null && !value.IsHeader && SetProperty(ref selectedFilter, value))
				{
					OnPropertyChanged(nameof(MembershipVisibility));
					OnPropertyChanged(nameof(BelongsHere));
					OnPersonBarChanged();
					OnPropertyChanged(nameof(GroupsVisibility));
					OnPropertyChanged(nameof(NoFacesVisibility));
					Viewer.Close();
					OnPropertyChanged(nameof(IsReviewing));
					OnPropertyChanged(nameof(ReviewVisibility));
					OnPropertyChanged(nameof(FacesAreaVisibility));
					ApplyFilter();
				}
			}
		}

		private TeachFolderOption? selectedFolder;
		public TeachFolderOption? SelectedFolder
		{
			get => selectedFolder;
			set
			{
				if (value is not null && SetProperty(ref selectedFolder, value))
				{
					_ = LoadStatsAsync();
					LoadReview();
					BuildFilters(lastPeople);
					ApplyFilter();
				}
			}
		}

		private bool isLoading = true;
		public bool IsLoading
		{
			get => isLoading;
			private set
			{
				if (SetProperty(ref isLoading, value))
				{
					OnPropertyChanged(nameof(GridVisibility));
					OnPropertyChanged(nameof(EmptyVisibility));
					OnPropertyChanged(nameof(ContentVisibility));
					OnPropertyChanged(nameof(CanSort));
				}
			}
		}

		private bool isBusy;
		public bool IsBusy
		{
			get => isBusy;
			private set
			{
				if (SetProperty(ref isBusy, value))
				{
					OnPropertyChanged(nameof(CanAct));
					OnPropertyChanged(nameof(CanSort));
					OnPropertyChanged(nameof(CanMoveFiles));
				}
			}
		}

		public bool CanAct => !IsBusy && SelectedCount > 0;

		// The switch under the folder row: a person of this folder, or a guest in a few of its pictures.
		public Visibility MembershipVisibility
			=> SelectedFilter is { Kind: TeachFilterKind.Person, PersonId: not null } ? Visibility.Visible : Visibility.Collapsed;

		public bool BelongsHere
		{
			get => SelectedFilter is { IsGuest: false };
			set
			{
				if (SelectedFilter is { PersonId: long id } person && value == person.IsGuest)
					_ = SetMembershipAsync(id, person.Name, value);
			}
		}

		private async Task SetMembershipAsync(long personId, string name, bool member)
		{
			var done = await RunAsync(string.Format(Strings.MediaMind_ActivityMembership.GetLocalizedResource(), name), async api =>
			{
				await api.Teach.SetMembershipAsync(LibraryId, personId, member ? "member" : "guest");
				ShowStatus(InfoBarSeverity.Success, string.Format((member
					? Strings.MediaMind_TeachMovedToMembers : Strings.MediaMind_TeachMovedToGuests).GetLocalizedResource(), name), string.Empty);
			});
			// Didn't happen (busy, engine down): put the switch back where it was.
			if (!done)
				OnPropertyChanged(nameof(BelongsHere));
		}

		public bool CanSort => !IsBusy && !IsLoading && string.IsNullOrEmpty(BlockingText) && Filters.Any(f => f.PersonId is not null || f.IsElsewhereOnly);

		// Set when the page cannot work at all (not scanned, engine down): replaces the whole body.
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
					OnPropertyChanged(nameof(CanSort));
				}
			}
		}

		public Visibility BlockingVisibility => string.IsNullOrEmpty(BlockingText) ? Visibility.Collapsed : Visibility.Visible;

		public Visibility ScanButtonVisibility => UnscannedFolder.Length > 0 ? Visibility.Visible : Visibility.Collapsed;

		public Visibility ContentVisibility => string.IsNullOrEmpty(BlockingText) ? Visibility.Visible : Visibility.Collapsed;

		public Visibility GridVisibility => !IsLoading && VisibleFaces.Count > 0 ? Visibility.Visible : Visibility.Collapsed;

		public Visibility EmptyVisibility => !IsLoading && VisibleFaces.Count == 0 ? Visibility.Visible : Visibility.Collapsed;

		private string emptyText = string.Empty;
		public string EmptyText
		{
			get => emptyText;
			private set => SetProperty(ref emptyText, value);
		}

		private string title = Strings.MediaMind_TeachTitle.GetLocalizedResource();
		public string Title
		{
			get => title;
			private set => SetProperty(ref title, value);
		}

		public string ShownText
			=> string.Format(Strings.MediaMind_TeachShownCount.GetLocalizedResource(), VisibleFaces.Count);

		private int selectedCount;
		public int SelectedCount
		{
			get => selectedCount;
			private set
			{
				if (SetProperty(ref selectedCount, value))
				{
					OnPropertyChanged(nameof(CanAct));
					OnPropertyChanged(nameof(SelectedText));
					OnPropertyChanged(nameof(SelectionBarVisibility));
				}
			}
		}

		public string SelectedText
			=> string.Format(Strings.MediaMind_TeachSelectedCount.GetLocalizedResource(), SelectedCount);

		public Visibility SelectionBarVisibility => SelectedCount > 0 ? Visibility.Visible : Visibility.Collapsed;

		private bool anySelectedIsExample;
		public Visibility RemoveExamplesVisibility => anySelectedIsExample ? Visibility.Visible : Visibility.Collapsed;

		private List<TeachFaceTileViewModel> selected = [];

		// The one message area (InfoBar): result of the last action, success or failure.
		private bool statusOpen;
		public bool StatusOpen
		{
			get => statusOpen;
			set => SetProperty(ref statusOpen, value);
		}

		private string statusTitle = string.Empty;
		public string StatusTitle
		{
			get => statusTitle;
			private set => SetProperty(ref statusTitle, value);
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

		private readonly string initialUnder;

		private IReadOnlyList<TeachPerson> lastPeople = [];

		public TeachReviewViewModel Review { get; }

		public TeachViewerViewModel Viewer { get; }

		private IReadOnlyList<PendingMatch> lastPending = [];

		public bool IsReviewing => SelectedFilter?.Kind == TeachFilterKind.Review;

		public Visibility ReviewVisibility => IsReviewing ? Visibility.Visible : Visibility.Collapsed;

		public Visibility FacesAreaVisibility => IsReviewing || IsPlacingGroups || IsShowingNoFaces || Viewer.IsOpen ? Visibility.Collapsed : Visibility.Visible;

		public IEnumerable<TeachFilterItem> ReassignTargets
			=> Filters.Where(f => f.Kind == TeachFilterKind.Person && f.PersonId is not null);

		public TeachPageViewModel(string libraryId, string under, string unscannedFolder)
		{
			LibraryId = libraryId;
			initialUnder = under;
			UnscannedFolder = unscannedFolder;
			Review = new TeachReviewViewModel(libraryId, ExamplesOf, OnReviewDecided, OnFileDeleted, OnFaceIgnored);
			Viewer = new TeachViewerViewModel(libraryId, NameTileAsync);
			Viewer.PropertyChanged += (_, e) =>
			{
				if (e.PropertyName == nameof(TeachViewerViewModel.IsOpen))
					OnPropertyChanged(nameof(FacesAreaVisibility));
			};
			_ = LoadAsync(firstLoad: true);
		}

		// The folder picked above the grid scopes every tab: faces, counts and the review queue.
		private bool InFolder(string path)
		{
			var folder = SelectedFolder?.Path ?? string.Empty;
			if (folder.Length == 0)
				return true;
			var dir = TeachFaceTileViewModel.FolderOf(path);
			return dir.Equals(folder, StringComparison.OrdinalIgnoreCase)
				|| dir.StartsWith(folder + "/", StringComparison.OrdinalIgnoreCase);
		}

		private List<long> PersonOrder()
			=> lastPeople.Where(p => p.PersonId is not null).Select(p => p.PersonId!.Value).Order().ToList();

		private void LoadReview()
			=> Review.Load(lastPending.Where(m => InFolder(m.Path)), PersonOrder());

		private void LoadViewerPeople()
		{
			var order = PersonOrder();
			var members = lastPeople.Where(p => p.PersonId is not null && !p.Guest).ToList();
			Viewer.SetPeople(members.Select((p, i) =>
				new TeachViewerPerson(p.Name, i < 9 ? (i + 1).ToString() : string.Empty, TeachReviewViewModel.TintOf(p.PersonId!.Value, order)))
				.Concat(lastPeople.Where(p => p.PersonId is not null && p.Guest).Select(p =>
					new TeachViewerPerson(p.Name, string.Empty, TeachReviewViewModel.TintOf(p.PersonId!.Value, order)))));
		}

		// Named from the viewer: the same call as the selection bar's Name as, for this one face.
		private async Task<bool> NameTileAsync(TeachFaceTileViewModel tile, string name)
		{
			if (IsBusy)
				return false;
			SetSelection([tile]);
			return await NameSelectedAsync(name);
		}

		public void OpenViewer(TeachFaceTileViewModel tile)
			=> Viewer.Open(tile, VisibleFaces);

		// Files deleted anywhere (in review, in Explorer) leave index rows behind, and with them
		// questions and tiles for files that are gone. Clear them after load and after a delete;
		// reload only if something went.
		private bool forgetting;

		private async Task ForgetMissingAsync()
		{
			if (forgetting || LibraryId.Length == 0)
				return;
			forgetting = true;
			try
			{
				if (await ApiAsync() is { } api && (await api.Teach.ForgetMissingAsync(LibraryId)).Removed > 0)
					await LoadAsync();
			}
			// Best-effort: an offline drive keeps its index, and the page stays as it is.
			catch (Exception)
			{
			}
			finally
			{
				forgetting = false;
			}
		}

		private static IMediaMindEngineService Engine => Ioc.Default.GetRequiredService<IMediaMindEngineService>();

		private async Task<MediaMindApiClient?> ApiAsync()
		{
			var engine = Engine;
			return await engine.EnsureStartedAsync(CancellationToken.None) ? engine.Api : null;
		}

		public async Task LoadAsync(bool firstLoad = false)
		{
			if (UnscannedFolder.Length > 0)
			{
				Title = string.Format(Strings.MediaMind_TeachTitleFor.GetLocalizedResource(), SystemIO.Path.GetFileName(UnscannedFolder.TrimEnd('\\')));
				BlockingText = Strings.MediaMind_TeachNotScanned.GetLocalizedResource();
				IsLoading = false;
				return;
			}

			IsLoading = true;
			BeginActivity(Strings.MediaMind_ActivityLoading.GetLocalizedResource());
			try
			{
				var api = await ApiAsync();
				if (api is null)
				{
					BlockingText = Strings.MediaMind_TeachEngineDown.GetLocalizedResource();
					return;
				}

				var libraries = await api.Libraries.ListAsync();
				var library = libraries.FirstOrDefault(l => l.Id == LibraryId);
				if (library is not null)
					libraryPath = library.Path;

				// Each part says when it has arrived, so a slow one is named on the card.
				var waiting = new List<string>();
				var parts = 0;
				Task<T> Part<T>(Task<T> task, string name)
				{
					lock (waiting)
						waiting.Add(name);
					parts++;
					return task.ContinueWith(t =>
					{
						int left;
						string still;
						lock (waiting)
						{
							waiting.Remove(name);
							left = waiting.Count;
							still = string.Join(", ", waiting);
						}
						if (left > 0)
							ReportActivity(string.Format(Strings.MediaMind_ActivityStillLoading.GetLocalizedResource(), still), parts - left, parts, Strings.MediaMind_Activity_parts.GetLocalizedResource());
						return t;
					}, TaskScheduler.Default).Unwrap();
				}
				// When one part fails (a folder not scanned yet), the others are never awaited: their
				// errors are read here so they don't surface later as unobserved.
				Task<T> Observed<T>(Task<T> task)
				{
					_ = task.ContinueWith(t => _ = t.Exception, CancellationToken.None, TaskContinuationOptions.OnlyOnFaulted, TaskScheduler.Default);
					return task;
				}
				var facesTask = Observed(Part(api.Teach.FacesAsync(LibraryId, null, unnamedOnly: false, includeBackground: false, limit: 5000), Strings.MediaMind_ActivityPartFaces.GetLocalizedResource()));
				var peopleTask = Observed(Part(api.Teach.PeopleAsync(LibraryId), Strings.MediaMind_ActivityPartPeople.GetLocalizedResource()));
				var pendingTask = Observed(Part(api.Pending.ListAsync(LibraryId), Strings.MediaMind_ActivityPartReview.GetLocalizedResource()));
				var duplicatesTask = Observed(Part(api.Duplicates.ListAsync(LibraryId), Strings.MediaMind_ActivityPartCopies.GetLocalizedResource()));
				var noFacesTask = Observed(Part(LoadNoFacesAsync(api), Strings.MediaMind_ActivityPartNoFaces.GetLocalizedResource()));
				var groupsTask = Observed(Part(LoadGroupsAsync(api), Strings.MediaMind_ActivityPartGroups.GetLocalizedResource()));
				_ = LoadStatsAsync();
				var faces = await facesTask;
				var people = await peopleTask;
				var pending = await pendingTask;
				try
				{
					copies = (await duplicatesTask).Groups
						.SelectMany(g => g.Files.Select(f => (f.Path, g.Id, g.Files.Count)))
						.GroupBy(x => x.Path, StringComparer.OrdinalIgnoreCase)
						.ToDictionary(x => x.Key, x => (x.First().Id, x.First().Count), StringComparer.OrdinalIgnoreCase);
				}
				// No duplicate check has run here yet: no copies to point at.
				catch (MediaMindApiException)
				{
					copies = [];
				}

				var groups = await groupsTask;
				var noFaces = await noFacesTask;
				await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() =>
				{
					SetGroups(groups);
					SetNoFaces(noFaces);
					if (library is not null)
						Title = string.Format(Strings.MediaMind_TeachTitleFor.GetLocalizedResource(), library.Name);

					var keep = allFaces.ToDictionary(f => f.Face.FaceId);
					allFaces = faces.Faces.Select(f => keep.TryGetValue(f.FaceId, out var old) ? old.Update(f) : new TeachFaceTileViewModel(LibraryId, f)).ToList();
					lastPeople = people;
					lastPending = pending;
					if (firstLoad)
						BuildFolders();
					LoadReview();
					LoadViewerPeople();
					BuildFilters(people);
					ApplyFilter();
					OnPropertyChanged(nameof(CanSort));
				});
				if (firstLoad)
					_ = ForgetMissingAsync();
			}
			catch (MediaMindApiException ex)
			{
				BlockingText = ex.Message;
			}
			catch (Exception)
			{
				BlockingText = Strings.MediaMind_TeachLoadFailed.GetLocalizedResource();
			}
			finally
			{
				IsLoading = false;
				EndActivity();
			}
		}

		private void BuildFilters(IReadOnlyList<TeachPerson> people)
		{
			var previous = SelectedFilter;
			Filters.Clear();
			Filters.Add(reviewFilter = TeachFilterItem.ForReview(Review.Items.Count));
			if (Groups.Count > 0)
				Filters.Add(TeachFilterItem.ForGroups(Groups.Count));
			if (NoFaceFiles.Count > 0)
				Filters.Add(TeachFilterItem.ForNoFaces(NoFaceFiles.Count));
			var sorted = SortedFiles();
			var here = allFaces.Where(f => InFolder(f.Face.Path)).ToList();
			var noOne = here.Where(f => string.IsNullOrEmpty(f.Face.PersonName) && !sorted.Contains(f.Face.FileId)).ToList();
			Filters.Add(TeachFilterItem.NoOneNamed(noOne.Select(f => f.Face.FileId).Distinct().Count()));
			Filters.Add(TeachFilterItem.Others(here.Count(f => string.IsNullOrEmpty(f.Face.PersonName)) - noOne.Count));
			Filters.Add(TeachFilterItem.All(here.Count));
			TeachFilterItem ForPerson(TeachPerson p) => TeachFilterItem.ForPerson(p, p.PersonId is long id
				? here.Where(f => f.Face.PersonId == id).Select(f => f.Face.FileId).Distinct().Count()
				: 0);
			foreach (var p in people.Where(p => !p.Guest))
				Filters.Add(ForPerson(p));
			if (people.Any(p => p.Guest))
			{
				Filters.Add(TeachFilterItem.GuestsHeader());
				foreach (var p in people.Where(p => p.Guest))
					Filters.Add(ForPerson(p));
			}

			PersonNames.Clear();
			foreach (var p in people)
				PersonNames.Add(p.Name);

			selectedFilter = (openReviewNext && Review.Items.Count > 0 ? reviewFilter : null)
				?? Filters.FirstOrDefault(f => previous is not null && f.Key == previous.Key)
				?? Filters[1];
			openReviewNext = false;
			OnPropertyChanged(nameof(SelectedFilter));
			OnPropertyChanged(nameof(IsReviewing));
			OnPropertyChanged(nameof(ReviewVisibility));
			OnPropertyChanged(nameof(FacesAreaVisibility));
			OnPropertyChanged(nameof(ReassignTargets));
			OnPropertyChanged(nameof(MembershipVisibility));
			OnPropertyChanged(nameof(BelongsHere));
			OnPropertyChanged(nameof(GroupsVisibility));
			OnPropertyChanged(nameof(NoFacesVisibility));
			OnPersonBarChanged();
		}

		private Dictionary<string, (long GroupId, int Count)> copies = [];

		// The set of copies a file (library-relative path) belongs to, if the duplicate check found one.
		public (long GroupId, int Count)? CopiesOf(string path)
			=> copies.TryGetValue(path, out var c) ? c : null;

		private TeachFilterItem? reviewFilter;
		private bool openReviewNext;

		private IEnumerable<TeachFaceTileViewModel> ExamplesOf(long? personId)
			=> allFaces.Where(f => f.Face.PersonId == personId && f.IsExample).OrderByDescending(f => f.Face.Width);

		// A decision in the review tab: the face joins a person (and becomes an example) or stays unnamed.
		private int answersSinceSort;

		// Every yes is a new example; they only change the sorting once a sort runs. Sort by
		// itself when the queue runs out, and quietly when the user leaves with answers unsorted.
		private void SortIfQueueDone()
		{
			if (Review.Items.Count > 0 || answersSinceSort == 0 || IsBusy)
				return;
			answersSinceSort = 0;
			_ = SortAsync();
		}

		public void OnLeaving()
		{
			ReleaseJobsToStrip();
			if (answersSinceSort == 0 || LibraryId.Length == 0)
				return;
			answersSinceSort = 0;
			var libraryId = LibraryId;
			_ = Task.Run(async () =>
			{
				try
				{
					if (await ApiAsync() is { } api)
						await api.Teach.ApplyAsync(libraryId);
				}
				// Best-effort: the next scan or sort applies the answers anyway.
				catch (Exception)
				{
				}
			});
		}

		private void OnReviewDecided(long faceId, long? personId, string? name)
		{
			if (personId is not null)
				answersSinceSort++;
			var tile = allFaces.FirstOrDefault(f => f.Face.FaceId == faceId);
			tile?.Update(tile.Face with { PersonId = personId ?? tile.Face.PersonId, PersonName = personId is null ? tile.Face.PersonName : name, IsExample = personId is not null });
			reviewFilter?.SetCount(Review.Items.Count);
			SortIfQueueDone();
		}

		private void OnFaceIgnored(long faceId)
		{
			allFaces.RemoveAll(f => f.Face.FaceId == faceId);
			reviewFilter?.SetCount(Review.Items.Count);
			ApplyFilter();
			SortIfQueueDone();
		}

		private void OnFileDeleted(string absPath)
		{
			allFaces.RemoveAll(f => string.Equals(f.Face.AbsPath, absPath, StringComparison.OrdinalIgnoreCase));
			reviewFilter?.SetCount(Review.Items.Count);
			ApplyFilter();
			SortIfQueueDone();
			// The file's other faces and questions leave the index too, so they are never asked.
			_ = ForgetMissingAsync();
		}

		private void BuildFolders()
		{
			Folders.Clear();
			var all = new TeachFolderOption(string.Empty, Strings.MediaMind_TeachAllFolders.GetLocalizedResource());
			Folders.Add(all);
			foreach (var g in allFaces.GroupBy(f => f.Folder).OrderBy(g => g.Key, StringComparer.OrdinalIgnoreCase))
			{
				if (g.Key.Length == 0)
					continue;
				Folders.Add(new TeachFolderOption(g.Key, $"{g.Key}  ({g.Count()})"));
			}

			var start = initialUnder.Trim('/');
			selectedFolder = start.Length == 0
				? all
				: Folders.FirstOrDefault(o => o.Path.Equals(start, StringComparison.OrdinalIgnoreCase))
					?? AddFolder(new TeachFolderOption(start, start));
			OnPropertyChanged(nameof(SelectedFolder));
		}

		private TeachFolderOption AddFolder(TeachFolderOption option)
		{
			Folders.Insert(1, option);
			return option;
		}

		private void ApplyFilter()
		{
			var filter = SelectedFilter;
			if (filter is null)
				return;

			var q = allFaces.Where(f => InFolder(f.Face.Path));
			q = filter.Kind switch
			{
				TeachFilterKind.NoOneNamed => q.Where(f => string.IsNullOrEmpty(f.Face.PersonName) && !SortedFiles().Contains(f.Face.FileId)),
				TeachFilterKind.Others => q.Where(f => string.IsNullOrEmpty(f.Face.PersonName) && SortedFiles().Contains(f.Face.FileId)),
				TeachFilterKind.Person => q.Where(f => f.Face.PersonId == filter.PersonId),
				TeachFilterKind.Review or TeachFilterKind.Groups => [],
				_ => q,
			};
			// A new list means the grid drops its selection; mirror that here.
			SetSelection([]);
			// Examples first, then the largest (clearest) faces: the best picks sit on top.
			VisibleFaces = q.OrderByDescending(f => f.IsExample).ThenByDescending(f => f.Face.Width).ToList();
			Viewer.SetList(VisibleFaces);

			EmptyText = filter.Kind switch
			{
				TeachFilterKind.NoOneNamed => Strings.MediaMind_TeachEmptyNoOne.GetLocalizedResource(),
				TeachFilterKind.Others => Strings.MediaMind_TeachEmptyOthers.GetLocalizedResource(),
				TeachFilterKind.Person when filter.PersonId is null
					=> string.Format(Strings.MediaMind_TeachEmptyElsewhere.GetLocalizedResource(), filter.Name),
				TeachFilterKind.Person => string.Format(Strings.MediaMind_TeachEmptyPerson.GetLocalizedResource(), filter.Name),
				_ => Strings.MediaMind_TeachEmptyAll.GetLocalizedResource(),
			};
		}

		// Files in which someone already has a name: their other faces need nothing from the user.
		private HashSet<long> SortedFiles()
			=> allFaces.Where(f => !string.IsNullOrEmpty(f.Face.PersonName)).Select(f => f.Face.FileId).ToHashSet();

		public void SetSelection(IEnumerable<TeachFaceTileViewModel> items)
		{
			selected = items.ToList();
			SelectedCount = selected.Count;
			anySelectedIsExample = selected.Any(s => s.IsExample);
			OnPropertyChanged(nameof(RemoveExamplesVisibility));
		}

		public async Task<bool> NameSelectedAsync(string name)
		{
			name = string.Join(' ', name.Split(' ', StringSplitOptions.RemoveEmptyEntries));
			if (name.Length == 0 || selected.Count == 0)
				return false;

			var existing = Filters.FirstOrDefault(f => f.Kind == TeachFilterKind.Person && f.PersonId is not null
				&& string.Equals(f.Name, name, StringComparison.CurrentCultureIgnoreCase));
			return await RunAsync(string.Format(Strings.MediaMind_ActivityNaming.GetLocalizedResource(), name), async api =>
			{
				var faces = selected;
				await api.Teach.AddExamplesAsync(LibraryId, faces.Select(f => f.Face.FaceId).ToList(), existing?.PersonId, existing is null ? name : null);
				ShowStatus(InfoBarSeverity.Success,
					string.Format(Strings.MediaMind_TeachNamedTitle.GetLocalizedResource(), faces.Count, name),
					Strings.MediaMind_TeachNamedMessage.GetLocalizedResource());
			});
		}

		public Task RemoveSelectedExamplesAsync()
			=> RunAsync(Strings.MediaMind_ActivityRemovingExamples.GetLocalizedResource(), async api =>
			{
				var faces = selected.Where(f => f.IsExample).ToList();
				await api.Teach.RemoveExamplesAsync(LibraryId, faces.Select(f => f.Face.FaceId).ToList());
				ShowStatus(InfoBarSeverity.Informational,
					string.Format(Strings.MediaMind_TeachRemovedTitle.GetLocalizedResource(), faces.Count), string.Empty);
			});

		public Task SortAsync()
			=> RunAsync(Strings.MediaMind_TeachSorting.GetLocalizedResource(), async api =>
			{
				var job = await FollowJobAsync(api, await api.Teach.StartApplyAsync(LibraryId), cancelable: false);
				if (job.State != "succeeded" || ResultAs(job, MediaMindJsonContext.Default.TeachApplyResult) is not { } result)
					throw new InvalidOperationException(string.IsNullOrEmpty(job.Error) ? job.State : job.Error);
				openReviewNext = result.Pending > 0;
				var people = string.Join(", ", result.People.Select(p =>
					string.Format(Strings.MediaMind_TeachSortedPerson.GetLocalizedResource(), p.Name, p.Files)));
				var review = result.Pending > 0
					? " " + string.Format(Strings.MediaMind_TeachSortedReview.GetLocalizedResource(), result.Pending)
					: string.Empty;
				ShowStatus(InfoBarSeverity.Success, Strings.MediaMind_TeachSortedTitle.GetLocalizedResource(), people + "." + review);

				// Both surfaces a sort changes: person tiles (new counts) and Suggestions (new questions).
				_ = App.PeopleManager.RefreshAsync();
				_ = Ioc.Default.GetRequiredService<SuggestionsViewModel>().RefreshAsync();
			});

		// True when the action ran and the page reloaded. `activity` is the card's title while it runs.
		private async Task<bool> RunAsync(string activity, Func<MediaMindApiClient, Task> action)
		{
			if (IsBusy)
				return false;
			IsBusy = true;
			BeginActivity(activity);
			try
			{
				var api = await ApiAsync();
				if (api is null)
				{
					ShowStatus(InfoBarSeverity.Error, Strings.MediaMind_TeachEngineDown.GetLocalizedResource(), string.Empty);
					return false;
				}
				await action(api);
				await LoadAsync();
				return true;
			}
			catch (MediaMindApiException ex)
			{
				ShowStatus(InfoBarSeverity.Error, Strings.MediaMind_TeachActionFailed.GetLocalizedResource(), ex.Message);
			}
			catch (Exception ex)
			{
				ShowStatus(InfoBarSeverity.Error, Strings.MediaMind_TeachActionFailed.GetLocalizedResource(), ex.Message);
			}
			finally
			{
				IsBusy = false;
				EndActivity();
			}
			return false;
		}

		private void ShowStatus(InfoBarSeverity severity, string title, string message)
		{
			MainWindow.Instance.DispatcherQueue.TryEnqueue(() =>
			{
				StatusSeverity = severity;
				StatusTitle = title;
				StatusMessage = message;
				StatusOpen = true;
			});
		}
	}

	public enum TeachFilterKind { Review, Groups, NoFaces, NoOneNamed, Others, All, Person, GuestsHeader }

	// One row of the left pane: "Faces without a name", "All faces", or a person.
	public sealed partial class TeachFilterItem : ObservableObject
	{
		public TeachFilterKind Kind { get; private init; }

		public string Key { get; private init; } = string.Empty;

		public string Name { get; private init; } = string.Empty;

		public long? PersonId { get; private init; }

		public bool IsElsewhereOnly => Kind == TeachFilterKind.Person && PersonId is null;

		public bool IsGuest { get; private init; }

		// The "Guests" label row: not a filter, never selected.
		public bool IsHeader => Kind == TeachFilterKind.GuestsHeader;

		public double RowOpacity => IsHeader ? 0.7 : 1.0;

		public Thickness RowPadding => IsHeader ? new(0, 16, 0, 4) : new(0, 8, 0, 8);

		// Lines the label up with the pane's "People" header, which has no icon column.
		public Thickness RowMargin => IsHeader ? new(-28, 0, 0, 0) : new(0);

		public Windows.UI.Text.FontWeight NameWeight => IsHeader ? Microsoft.UI.Text.FontWeights.SemiBold : Microsoft.UI.Text.FontWeights.Normal;

		// Pictures with two or more named people: each can only go one place, so the user picks.
		public static TeachFilterItem ForNoFaces(int count) => new()
		{
			Kind = TeachFilterKind.NoFaces,
			Key = "nofaces",
			Name = Strings.MediaMind_NoFacesTab.GetLocalizedResource(),
			Detail = string.Format(Strings.MediaMind_NoFacesDetail.GetLocalizedResource(), count),
			Glyph = "\uE91B",
		};

		public static TeachFilterItem ForGroups(int count) => new()
		{
			Kind = TeachFilterKind.Groups,
			Key = "groups",
			Name = Strings.MediaMind_TeachGroupsTab.GetLocalizedResource(),
			Detail = string.Format(Strings.MediaMind_TeachGroupsDetail.GetLocalizedResource(), count),
			Glyph = "",
		};

		public static TeachFilterItem GuestsHeader() => new()
		{
			Kind = TeachFilterKind.GuestsHeader,
			Key = "guests",
			Name = Strings.MediaMind_TeachGuestsHeader.GetLocalizedResource(),
			Detail = Strings.MediaMind_TeachGuestsDetail.GetLocalizedResource(),
			Glyph = string.Empty,
		};

		private string detail = string.Empty;
		public string Detail
		{
			get => detail;
			private set => SetProperty(ref detail, value);
		}

		public static TeachFilterItem ForReview(int count)
		{
			var item = new TeachFilterItem
			{
				Kind = TeachFilterKind.Review,
				Key = "review",
				Name = Strings.MediaMind_ReviewTab.GetLocalizedResource(),
				Glyph = "",
			};
			item.SetCount(count);
			return item;
		}

		public void SetCount(int count)
			=> Detail = count > 0
				? string.Format(Strings.MediaMind_TeachFaceCount.GetLocalizedResource(), count)
				: Strings.MediaMind_ReviewNothing.GetLocalizedResource();

		public string Glyph { get; private init; } = "";

		// Faces in files where nobody is named yet: the real to-do, counted in files.
		public static TeachFilterItem NoOneNamed(int files) => new()
		{
			Kind = TeachFilterKind.NoOneNamed,
			Key = "noone",
			Name = Strings.MediaMind_TeachFilterNoOne.GetLocalizedResource(),
			Detail = string.Format(Strings.MediaMind_TeachFileCount.GetLocalizedResource(), files),
			Glyph = "",
		};

		// Unnamed faces in files that already have someone named (background, crowds, other
		// frames, the first scan's leftover groups): shown for completeness, not as work.
		public static TeachFilterItem Others(int faces) => new()
		{
			Kind = TeachFilterKind.Others,
			Key = "others",
			Name = Strings.MediaMind_TeachFilterOthers.GetLocalizedResource(),
			Detail = string.Format(Strings.MediaMind_TeachOthersDetail.GetLocalizedResource(), faces),
			Glyph = "",
		};

		public static TeachFilterItem All(int count) => new()
		{
			Kind = TeachFilterKind.All,
			Key = "all",
			Name = Strings.MediaMind_TeachFilterAll.GetLocalizedResource(),
			Detail = string.Format(Strings.MediaMind_TeachFaceCount.GetLocalizedResource(), count),
			Glyph = "",
		};

		// "557 files, 301 examples": what is sorted here first, then what it learns from.
		public static TeachFilterItem ForPerson(TeachPerson p, int files) => new()
		{
			Kind = TeachFilterKind.Person,
			Key = p.PersonId is long id ? $"p{id}" : $"n{p.Name}",
			Name = p.Name,
			PersonId = p.PersonId,
			IsGuest = p.Guest,
			Detail = (files > 0 ? string.Format(Strings.MediaMind_TeachFileCount.GetLocalizedResource(), files) + ", " : string.Empty) + p.ExamplesHere switch
			{
				0 when p.ExamplesElsewhere > 0 => string.Format(Strings.MediaMind_TeachExamplesElsewhere.GetLocalizedResource(), p.ExamplesElsewhere),
				0 => Strings.MediaMind_TeachNoExamples.GetLocalizedResource(),
				_ when p.ExamplesElsewhere > 0 => string.Format(Strings.MediaMind_TeachExamplesBoth.GetLocalizedResource(), p.ExamplesHere, p.ExamplesElsewhere),
				_ => string.Format(Strings.MediaMind_TeachExamplesHere.GetLocalizedResource(), p.ExamplesHere),
			},
		};
	}

	public sealed record TeachFolderOption(string Path, string Label);

	// One face crop in the grid. The thumbnail loads only when the tile is realized
	// (TeachPage's ContainerContentChanging), so thousands of faces cost nothing up front.
	public sealed partial class TeachFaceTileViewModel : ObservableObject
	{
		private static readonly SemaphoreSlim ThumbnailGate = new(6);

		private readonly string libraryId;
		private bool thumbnailRequested;

		public TeachFace Face { get; private set; }

		public string Folder { get; private set; }

		public string FileName => SystemIO.Path.GetFileName(Face.Path);

		public bool IsExample => Face.IsExample;

		public Visibility ExampleBadgeVisibility => Face.IsExample ? Visibility.Visible : Visibility.Collapsed;

		public Visibility VideoBadgeVisibility => Face.Kind == "video" ? Visibility.Visible : Visibility.Collapsed;

		public string NameText => Face.PersonName ?? Strings.MediaMind_TeachNoName.GetLocalizedResource();

		public double NameOpacity => Face.PersonName is null ? 0.6 : 1.0;

		public string ToolTip => $"{Face.Path}";

		private BitmapImage? thumbnail;
		public BitmapImage? Thumbnail
		{
			get => thumbnail;
			private set => SetProperty(ref thumbnail, value);
		}

		public TeachFaceTileViewModel(string libraryId, TeachFace face)
		{
			this.libraryId = libraryId;
			Face = face;
			Folder = FolderOf(face.Path);
		}

		internal static string FolderOf(string path)
		{
			path = path.Replace('\\', '/');
			var i = path.LastIndexOf('/');
			return i > 0 ? path[..i] : string.Empty;
		}

		public TeachFaceTileViewModel Update(TeachFace face)
		{
			Face = face;
			Folder = FolderOf(face.Path);
			OnPropertyChanged(nameof(IsExample));
			OnPropertyChanged(nameof(ExampleBadgeVisibility));
			OnPropertyChanged(nameof(NameText));
			OnPropertyChanged(nameof(NameOpacity));
			return this;
		}

		public void EnsureThumbnail()
		{
			if (thumbnailRequested)
				return;
			thumbnailRequested = true;
			_ = LoadThumbnailAsync();
		}

		private async Task LoadThumbnailAsync()
		{
			await ThumbnailGate.WaitAsync();
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (engine.Api is null)
					return;
				var bytes = await engine.Api.Persons.FaceThumbnailAsync(libraryId, Face.FaceId, 192);
				var bitmap = await bytes.ToBitmapAsync();
				if (bitmap is not null)
					await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() => Thumbnail = bitmap);
			}
			// Best-effort: the tile keeps its placeholder glyph.
			catch (Exception)
			{
				thumbnailRequested = false;
			}
			finally
			{
				ThumbnailGate.Release();
			}
		}
	}
}

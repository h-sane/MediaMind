// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Services.MediaMind;
using Microsoft.UI.Xaml;
using System.Collections.Specialized;
using Windows.Storage;

namespace Files.App.ViewModels.People
{
	// MediaMind: the People page (docs/PEOPLE_VIEW_V2_DESIGN.md) — every scanned
	// library at once, in two modes: Faces (a flat grid of everyone, the default) and
	// Folders (people grouped by the folders they came from, with in-page drilling).
	// Pins and collections are layered on top in both. Everything here is a view over
	// the engine's /people-view/overview; nothing moves a file on disk.
	public sealed partial class PeopleHomePageViewModel : ObservableObject, IDisposable
	{
		private const string ModeSettingKey = "MediaMindPeopleFoldersMode";

		private PeopleOverview? overview;
		private Dictionary<string, PeopleEntry> entriesById = [];
		private Dictionary<string, PeopleNode> nodesById = [];
		private readonly List<string> navStack = [];
		private int refreshVersion;

		// Persons already checked by the background sweep this run (shared across page visits).
		private static readonly HashSet<string> verifiedKeys = [];
		private readonly CancellationTokenSource sweepCts = new();
		private bool sweepStarted;

		public ObservableCollection<PeopleTileViewModel> MainPeople { get; } = [];

		public ObservableCollection<PeopleTileViewModel> DuplicatePeople { get; } = [];

		public ObservableCollection<PeopleTileViewModel> PinnedPeople { get; } = [];

		public ObservableCollection<FolderCardViewModel> PinnedFolders { get; } = [];

		public ObservableCollection<FolderCardViewModel> FolderCards { get; } = [];

		public ObservableCollection<CollectionChipViewModel> Collections { get; } = [];

		public ObservableCollection<BreadcrumbItemViewModel> Breadcrumb { get; } = [];

		// People the user removed; kept so they can be restored from the toolbar.
		public ObservableCollection<PeopleTileViewModel> HiddenPeople { get; } = [];

		public Visibility HiddenVisibility => HiddenPeople.Count > 0 ? Visibility.Visible : Visibility.Collapsed;

		public string HiddenLabel => string.Format("MediaMind_PeopleHiddenButton".GetLocalizedResource(), HiddenPeople.Count);

		private PersonDetailViewModel? detail;
		public PersonDetailViewModel? Detail
		{
			get => detail;
			private set
			{
				if (SetProperty(ref detail, value))
					OnPropertyChanged(nameof(DetailVisibility));
			}
		}

		public Visibility DetailVisibility => Detail is null ? Visibility.Collapsed : Visibility.Visible;

		public void OpenDetail(PeopleTileViewModel tile)
			=> Detail = new PersonDetailViewModel(tile);

		public void CloseDetail()
			=> Detail = null;

		private bool isFoldersMode;
		public bool IsFoldersMode
		{
			get => isFoldersMode;
			set
			{
				if (!SetProperty(ref isFoldersMode, value))
					return;

				SaveMode(value);
				Rebuild();
			}
		}

		private string searchText = string.Empty;
		public string SearchText
		{
			get => searchText;
			set
			{
				if (SetProperty(ref searchText, value))
					Rebuild();
			}
		}

		private bool showOnlyUnnamed;
		public bool ShowOnlyUnnamed
		{
			get => showOnlyUnnamed;
			set
			{
				if (SetProperty(ref showOnlyUnnamed, value))
					Rebuild();
			}
		}

		private bool isLoading = true;
		public bool IsLoading
		{
			get => isLoading;
			private set
			{
				if (SetProperty(ref isLoading, value))
					RaiseVisibility();
			}
		}

		private string? errorText;
		public string? ErrorText
		{
			get => errorText;
			private set
			{
				if (SetProperty(ref errorText, value))
					OnPropertyChanged(nameof(ErrorVisibility));
			}
		}

		public Visibility ErrorVisibility => ErrorText is null ? Visibility.Collapsed : Visibility.Visible;

		public Visibility LoadingVisibility => IsLoading ? Visibility.Visible : Visibility.Collapsed;

		public Visibility EmptyVisibility => !IsLoading && ErrorText is null && (overview?.Entries.Count ?? 0) == 0 ? Visibility.Visible : Visibility.Collapsed;

		public Visibility FacesOnlyVisibility => IsFoldersMode ? Visibility.Collapsed : Visibility.Visible;

		public Visibility FoldersOnlyVisibility => IsFoldersMode ? Visibility.Visible : Visibility.Collapsed;

		public Visibility PinnedVisibility => PinnedPeople.Count + PinnedFolders.Count > 0 ? Visibility.Visible : Visibility.Collapsed;

		public Visibility PinnedPeopleVisibility => PinnedPeople.Count > 0 ? Visibility.Visible : Visibility.Collapsed;

		public Visibility PinnedFoldersVisibility => PinnedFolders.Count > 0 ? Visibility.Visible : Visibility.Collapsed;

		public Visibility DuplicatesVisibility => !IsFoldersMode && DuplicatePeople.Count > 0 ? Visibility.Visible : Visibility.Collapsed;

		public Visibility FolderCardsVisibility => IsFoldersMode && FolderCards.Count > 0 ? Visibility.Visible : Visibility.Collapsed;

		public Visibility CollectionChipsVisibility => Collections.Count > 0 ? Visibility.Visible : Visibility.Collapsed;

		public IReadOnlyList<CollectionChipViewModel> CollectionList => Collections;

		// True while browsing inside a collection, where a folder card can be sent back to its automatic place.
		public bool ViewingCollection => navStack.Count > 0 && nodesById.TryGetValue(navStack[0], out var root) && root.Kind == "collection";

		public PeopleHomePageViewModel()
		{
			isFoldersMode = LoadMode();
			App.PeopleManager.DataChanged += PeopleManager_DataChanged;
			_ = RefreshAsync();
		}

		// A completed scan (PeopleManager.RefreshAsync, triggered by JobUpdated) must
		// show up live. DataChanged fires from the engine's background callback.
		private async void PeopleManager_DataChanged(object? sender, NotifyCollectionChangedEventArgs e)
			=> await RefreshAsync();

		public async Task RefreshAsync()
		{
			var version = Interlocked.Increment(ref refreshVersion);
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
				{
					await OnUiAsync(() => Fail());
					return;
				}

				var fresh = await engine.Api.PeopleView.OverviewAsync();
				if (version != refreshVersion)
					return; // a newer refresh is already on its way

				await OnUiAsync(() =>
				{
					overview = fresh;
					entriesById = fresh.Entries.ToDictionary(e => e.Id);
					nodesById = [];
					foreach (var root in fresh.Tree)
						IndexNode(root);

					ErrorText = null;
					IsLoading = false;
					Rebuild();
				});

				StartSweep();
			}
			// Cause and effect: a failed load says so on the page instead of leaving it blank.
			catch (Exception)
			{
				await OnUiAsync(() => Fail());
			}
		}

		// After the page is up, the engine checks everyone in small batches: a "person"
		// none of whose faces can be shown is a recognition mistake and leaves the page,
		// so no card is left without a face. Best-effort — the per-card check still runs.
		private void StartSweep()
		{
			if (sweepStarted)
				return;

			sweepStarted = true;
			_ = Task.Run(async () =>
			{
				try
				{
					var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
					var activity = Ioc.Default.GetRequiredService<Files.App.ViewModels.UserControls.MediaMind.ScanActivityViewModel>();
					while (!sweepCts.IsCancellationRequested && engine.Api is { } api)
					{
						// A scan is using the CPU and the drive: the sweep waits until it is done.
						if (activity.IsBusy)
						{
							await Task.Delay(TimeSpan.FromSeconds(5), sweepCts.Token);
							continue;
						}

						var batch = (overview?.Entries ?? [])
							.SelectMany(e => e.Keys)
							.Where(k => !verifiedKeys.Contains(k))
							.Take(20)
							.ToList();
						if (batch.Count == 0)
							break;

						var result = await api.PeopleView.VerifyAsync(batch, sweepCts.Token);
						foreach (var key in batch)
							verifiedKeys.Add(key);

						if (result.Unusable.Count > 0)
							await RefreshAsync();
					}
				}
				catch (Exception)
				{
				}
			});
		}

		private void Fail()
		{
			IsLoading = false;
			ErrorText = "MediaMind_PeopleActionFailed".GetLocalizedResource();
			RaiseVisibility();
		}

		private static Task OnUiAsync(Action action)
			=> MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(action);

		private void IndexNode(PeopleNode node)
		{
			nodesById[node.Id] = node;
			foreach (var child in node.Subgroups)
				IndexNode(child);
		}

		// ---- mode / navigation ------------------------------------------------

		public void OpenNode(string nodeId)
		{
			if (!nodesById.ContainsKey(nodeId))
				return;

			navStack.Add(nodeId);
			IsFoldersMode = true; // no-op when already there, rebuilds otherwise
			Rebuild();
		}

		public void OpenCollection(string collectionId)
		{
			navStack.Clear();
			OpenNode(collectionId);
		}

		public void NavigateTo(string? nodeId)
		{
			if (nodeId is null)
				navStack.Clear();
			else
			{
				var index = navStack.IndexOf(nodeId);
				if (index >= 0)
					navStack.RemoveRange(index + 1, navStack.Count - index - 1);
			}

			Rebuild();
		}

		// ---- building the visible lists ---------------------------------------

		private void Rebuild()
		{
			if (overview is null)
			{
				RaiseVisibility();
				return;
			}

			// A refresh can remove the node being viewed (e.g. its last person moved
			// into a collection): fall back to the nearest surviving ancestor.
			while (navStack.Count > 0 && !nodesById.ContainsKey(navStack[^1]))
				navStack.RemoveAt(navStack.Count - 1);

			BuildCollections();
			BuildPinned();
			BuildHidden();
			BuildBreadcrumb();

			MainPeople.Clear();
			DuplicatePeople.Clear();
			FolderCards.Clear();

			if (IsFoldersMode)
			{
				var current = navStack.Count > 0 ? nodesById[navStack[^1]] : null;
				var subgroups = current?.Subgroups ?? overview.Tree;
				foreach (var node in subgroups)
					FolderCards.Add(new FolderCardViewModel(node, entriesById));

				foreach (var id in current?.PersonIds ?? [])
					if (entriesById.TryGetValue(id, out var entry) && Matches(entry))
						MainPeople.Add(Track(new PeopleTileViewModel(entry)));
			}
			else
			{
				// Possible duplicates are pulled out of the main grid into their own section
				// so they can never be mistaken for two different people.
				foreach (var entry in Ordered(overview.Entries.Where(Matches)))
				{
					if (entry.Duplicates.Count > 0)
						DuplicatePeople.Add(Track(new PeopleTileViewModel(entry, DuplicateLabelFor(entry))));
					else
						MainPeople.Add(Track(new PeopleTileViewModel(entry)));
				}
			}

			RaiseVisibility();
		}

		private bool Matches(PeopleEntry entry)
		{
			if (ShowOnlyUnnamed && entry.Name is not null)
				return false;

			return string.IsNullOrWhiteSpace(SearchText)
				|| (entry.Name ?? entry.AutoLabel).Contains(SearchText.Trim(), StringComparison.CurrentCultureIgnoreCase);
		}

		// Pinned first, then named before unnamed, then the most-photographed first — so a
		// one-photo background face sinks below the people who matter.
		private static IEnumerable<PeopleEntry> Ordered(IEnumerable<PeopleEntry> entries)
			=> entries
				.OrderBy(e => e.Pinned ? 0 : 1)
				.ThenBy(e => e.Name is null ? 1 : 0)
				.ThenByDescending(e => e.MediaCount);

		private string DuplicateLabelFor(PeopleEntry entry)
		{
			var other = entry.Duplicates
				.OrderByDescending(d => d.Similarity)
				.Select(d => entriesById.GetValueOrDefault(d.EntryId))
				.FirstOrDefault(e => e is not null);

			return string.Format("MediaMind_PeopleDuplicateBadge".GetLocalizedResource(), other?.Name ?? other?.AutoLabel ?? "?");
		}

		private void BuildCollections()
		{
			Collections.Clear();
			foreach (var collection in overview!.Collections)
			{
				var count = nodesById.TryGetValue(collection.Id, out var node) ? node.TotalPersons : 0;
				Collections.Add(new CollectionChipViewModel(collection, count));
			}
		}

		private PeopleTileViewModel Track(PeopleTileViewModel tile)
		{
			tile.Unusable += OnTileUnusable;
			return tile;
		}

		// The engine could not crop any face of this "person": a recognition mistake,
		// already recorded by the engine, so the card just leaves every list it is in.
		private void OnTileUnusable(PeopleTileViewModel tile)
		{
			foreach (var list in new[] { MainPeople, DuplicatePeople, PinnedPeople })
				foreach (var match in list.Where(t => t.Entry.Id == tile.Entry.Id).ToList())
					list.Remove(match);

			OnPropertyChanged(nameof(DuplicatesVisibility));
			OnPropertyChanged(nameof(PinnedVisibility));
			OnPropertyChanged(nameof(PinnedPeopleVisibility));
		}

		private void BuildHidden()
		{
			HiddenPeople.Clear();
			foreach (var entry in overview!.Hidden ?? [])
				HiddenPeople.Add(new PeopleTileViewModel(entry));

			OnPropertyChanged(nameof(HiddenVisibility));
			OnPropertyChanged(nameof(HiddenLabel));
		}

		private void BuildPinned()
		{
			PinnedPeople.Clear();
			PinnedFolders.Clear();
			foreach (var pin in overview!.Pins)
			{
				if (pin.Kind == "person" && pin.Available && pin.RefId is not null && entriesById.TryGetValue(pin.RefId, out var entry))
					PinnedPeople.Add(Track(new PeopleTileViewModel(entry) { IsPinned = true }));
				else if (pin.Available && pin.RefId is not null && nodesById.TryGetValue(pin.RefId, out var node))
					PinnedFolders.Add(new FolderCardViewModel(node, entriesById) { IsPinned = true });
				else
					PinnedFolders.Add(new FolderCardViewModel(pin));
			}
		}

		private void BuildBreadcrumb()
		{
			Breadcrumb.Clear();
			Breadcrumb.Add(new BreadcrumbItemViewModel(null, "People"));
			foreach (var id in navStack)
				if (nodesById.TryGetValue(id, out var node))
					Breadcrumb.Add(new BreadcrumbItemViewModel(node.Id, node.Name));
		}

		private void RaiseVisibility()
		{
			OnPropertyChanged(nameof(LoadingVisibility));
			OnPropertyChanged(nameof(EmptyVisibility));
			OnPropertyChanged(nameof(FacesOnlyVisibility));
			OnPropertyChanged(nameof(FoldersOnlyVisibility));
			OnPropertyChanged(nameof(PinnedVisibility));
			OnPropertyChanged(nameof(PinnedPeopleVisibility));
			OnPropertyChanged(nameof(PinnedFoldersVisibility));
			OnPropertyChanged(nameof(DuplicatesVisibility));
			OnPropertyChanged(nameof(FolderCardsVisibility));
			OnPropertyChanged(nameof(CollectionChipsVisibility));
		}

		// ---- actions (each ends in a refresh so the page shows the result) ------

		public Task TogglePinAsync(PeopleTileViewModel tile)
			=> TogglePinAsync(tile.IsPinned, tile.Keys, tile.Keys[0]);

		public Task TogglePinAsync(FolderCardViewModel card)
			=> TogglePinAsync(card.IsPinned, [card.Key], card.Key);

		private Task TogglePinAsync(bool isPinned, IReadOnlyList<string> allKeys, string pinKey)
			=> RunAsync(api => isPinned
				? api.PeopleView.UnpinAsync(allKeys)
				: api.PeopleView.PinAsync(pinKey));

		// "Remove person": ignored from now on, restorable from the Hidden button.
		public Task HideAsync(PeopleTileViewModel tile)
			=> RunAsync(api => api.PeopleView.HideAsync(tile.Keys));

		public Task UnhideAsync(PeopleTileViewModel tile)
			=> RunAsync(api => api.PeopleView.UnhideAsync(tile.Keys));

		// The other person a typed name refers to: same name, most-photographed first.
		public PeopleTileViewModel? FindMergeTarget(PeopleTileViewModel source, string name)
		{
			name = name.Trim();
			var match = overview?.Entries
				.Where(e => e.Id != source.Entry.Id && e.Name is not null && string.Equals(e.Name, name, StringComparison.CurrentCultureIgnoreCase))
				.OrderByDescending(e => e.MediaCount)
				.FirstOrDefault();
			return match is null ? null : new PeopleTileViewModel(match);
		}

		public IEnumerable<string> MergeNameChoices(PeopleTileViewModel source, string typed)
			=> (overview?.Entries ?? [])
				.Where(e => e.Id != source.Entry.Id && e.Name is not null && e.Name.Contains(typed.Trim(), StringComparison.CurrentCultureIgnoreCase))
				.Select(e => e.Name!)
				.Distinct(StringComparer.CurrentCultureIgnoreCase)
				.Order(StringComparer.CurrentCultureIgnoreCase);

		public Task MergeAsync(PeopleTileViewModel source, PeopleTileViewModel target)
			=> RunAsync(api => api.PeopleView.MergeAsync(source.Keys, target.Keys));

		public Task CreateCollectionAsync(string name)
			=> RunAsync(api => api.PeopleView.CreateCollectionAsync(name));

		public Task RenameCollectionAsync(string id, string name)
			=> RunAsync(api => api.PeopleView.RenameCollectionAsync(id, name));

		public Task DeleteCollectionAsync(string id)
			=> RunAsync(api => api.PeopleView.DeleteCollectionAsync(id));

		public Task MoveToCollectionAsync(string collectionId, IReadOnlyList<string> keys)
			=> RunAsync(api => api.PeopleView.AddToCollectionAsync(collectionId, keys));

		public Task RemoveFromCollectionAsync(IReadOnlyList<string> keys)
			=> RunAsync(api => api.PeopleView.RemoveFromCollectionsAsync(keys));

		public Task LinkDuplicateAsync(PeopleTileViewModel tile, bool same)
		{
			var other = tile.Entry.Duplicates
				.OrderByDescending(d => d.Similarity)
				.Select(d => entriesById.GetValueOrDefault(d.EntryId))
				.FirstOrDefault(e => e is not null);
			if (other is null)
				return Task.CompletedTask;

			var a = tile.Entry.Members[0];
			var b = other.Members[0];
			var pair = new GlobalLinkSuggestionPair(a.LibraryId, a.LocalPersonId, b.LibraryId, b.LocalPersonId);
			return RunAsync(api => same
				? api.GlobalPeople.AcceptLinkSuggestionAsync(pair)
				: api.GlobalPeople.DismissLinkSuggestionAsync(pair));
		}

		// The entry a possible-duplicate tile is being compared with (for the dialog).
		public PeopleTileViewModel? DuplicateCounterpart(PeopleTileViewModel tile)
		{
			var other = tile.Entry.Duplicates
				.OrderByDescending(d => d.Similarity)
				.Select(d => entriesById.GetValueOrDefault(d.EntryId))
				.FirstOrDefault(e => e is not null);
			return other is null ? null : new PeopleTileViewModel(other);
		}

		public async Task NamedAsync(PeopleTileViewModel tile, string name)
		{
			if (await tile.NameAsync(name))
				await RefreshAsync();
		}

		private async Task RunAsync(Func<MediaMindApiClient, Task> action)
		{
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
				{
					await OnUiAsync(() => ErrorText = "MediaMind_PeopleActionFailed".GetLocalizedResource());
					return;
				}

				await action(engine.Api);
				await OnUiAsync(() => ErrorText = null);
			}
			catch (Exception)
			{
				await OnUiAsync(() => ErrorText = "MediaMind_PeopleActionFailed".GetLocalizedResource());
			}

			await RefreshAsync();
		}

		// ---- persisted view mode ---------------------------------------------

		private static bool LoadMode()
		{
			try
			{
				return ApplicationData.Current.LocalSettings.Values[ModeSettingKey] is true;
			}
			catch (Exception)
			{
				return false;
			}
		}

		private static void SaveMode(bool foldersMode)
		{
			try
			{
				ApplicationData.Current.LocalSettings.Values[ModeSettingKey] = foldersMode;
			}
			catch (Exception)
			{
			}
		}

		public void Dispose()
		{
			sweepCts.Cancel();
			App.PeopleManager.DataChanged -= PeopleManager_DataChanged;
		}
	}
}

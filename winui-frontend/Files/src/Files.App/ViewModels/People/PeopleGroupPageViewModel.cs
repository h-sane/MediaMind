// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Data.Items.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media.Imaging;
using System.Collections.Specialized;

namespace Files.App.ViewModels.People
{
	// MediaMind: backs PeopleGroupPage (ADR-0007) — a Group's content is only its
	// direct child Groups and Persons, never media, so this is a small tile-grid
	// view model rather than anything BaseLayoutPage-shaped.
	public sealed partial class PeopleGroupPageViewModel : ObservableObject, IDisposable
	{
		private readonly string libraryId;
		private readonly string groupPath;

		private PeopleGroupItem group;
		public PeopleGroupItem Group
		{
			get => group;
			private set => SetProperty(ref group, value);
		}

		public ObservableCollection<GroupTileViewModel> Subgroups { get; } = [];

		public ObservableCollection<PersonTileViewModel> Persons { get; } = [];

		// Drives PeopleGroupPage's empty-state block via the same
		// EmptyListToVisibilityConverter idiom PeopleHomePage already uses.
		public int TotalCount => Subgroups.Count + Persons.Count;

		private bool showEverythingBelow;
		public bool ShowEverythingBelow
		{
			get => showEverythingBelow;
			set
			{
				if (SetProperty(ref showEverythingBelow, value))
					RebuildPersons();
			}
		}

		public PeopleGroupPageViewModel(PeopleGroupItem group)
		{
			this.group = group;
			libraryId = group.LibraryId;
			groupPath = group.Group.Path;

			Subgroups.CollectionChanged += (_, _) => OnPropertyChanged(nameof(TotalCount));
			Persons.CollectionChanged += (_, _) => OnPropertyChanged(nameof(TotalCount));

			RebuildSubgroups();
			RebuildPersons();

			App.PeopleManager.DataChanged += PeopleManager_DataChanged;
		}

		// A completed scan rebuilds the whole tree (PeopleManager.RefreshAsync), so
		// this Group's PeopleGroupItem instance goes stale — re-resolve it by
		// identity rather than trying to patch the old one. Dispatched because
		// DataChanged fires from the engine's background job-update callback.
		private async void PeopleManager_DataChanged(object? sender, NotifyCollectionChangedEventArgs e)
			=> await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(RefreshFromManager);

		private void RefreshFromManager()
		{
			var fresh = App.PeopleManager.FindGroup(libraryId, groupPath);
			if (fresh is null)
				return; // library/group no longer exists; leave the last-known content visible

			Group = fresh;
			RebuildSubgroups();
			RebuildPersons();
		}

		private void RebuildSubgroups()
		{
			Subgroups.Clear();
			foreach (var subgroup in Group.Subgroups)
				Subgroups.Add(new GroupTileViewModel(subgroup));
		}

		private void RebuildPersons()
		{
			Persons.Clear();
			foreach (var person in OrderForDisplay(CollectPersons(Group, showEverythingBelow)))
				Persons.Add(new PersonTileViewModel(person));
		}

		public void Dispose()
			=> App.PeopleManager.DataChanged -= PeopleManager_DataChanged;

		// ADR-0007 direct-contents default: only Group.ChildPersons unless the
		// toggle asks for the full subtree. The whole tree is already in memory
		// (one TreeAsync call), so "everything below" is a local walk, not a new
		// backend call — revisit only if a library's tree gets slow to walk this way.
		private static IEnumerable<PersonItem> CollectPersons(PeopleGroupItem group, bool recursive)
		{
			foreach (var person in group.ChildPersons)
				yield return person;

			if (!recursive)
				yield break;

			foreach (var subgroup in group.Subgroups)
				foreach (var person in CollectPersons(subgroup, true))
					yield return person;
		}

		// Default browsing order (a per-view sort/filter UI is a separate, larger
		// piece of future work): named people first — once you've named someone
		// they should read as "done", not sit wherever the tree happened to put
		// them — then by descending media count, so a person appearing in one or
		// two photos (likely a background/false-positive face) sinks to the
		// bottom instead of scattering randomly among real people.
		internal static IEnumerable<PersonItem> OrderForDisplay(IEnumerable<PersonItem> persons) =>
			persons
				.OrderBy(p => p.Person.Name is null ? 1 : 0)
				.ThenByDescending(p => p.Person.MediaCount);
	}

	// Folder-style tile (ADR-0007 Group): previews the first few persons found
	// anywhere in this subtree as a face stack, Google Photos "People" album
	// style, plus a "+N" badge for everyone else — so a Group with only nested
	// Subgroups (e.g. "Family" holding "Cousins"/"Grandparents") still shows real faces
	// instead of an empty card.
	public sealed partial class GroupTileViewModel : ObservableObject
	{
		private const int PreviewCount = 3;

		public PeopleGroupItem Item { get; }

		public string Text => Item.Text ?? string.Empty;

		public int TotalPersons => Item.Group.TotalPersons;

		public PersonTileViewModel? Person1 { get; }
		public PersonTileViewModel? Person2 { get; }
		public PersonTileViewModel? Person3 { get; }

		public int RemainingCount { get; }

		public string RemainingLabel => $"+{RemainingCount}";

		public GroupTileViewModel(PeopleGroupItem item)
		{
			Item = item;

			var preview = PeopleGroupPageViewModel.OrderForDisplay(CollectPreviewPersons(item)).Take(PreviewCount + 1).ToList();
			Person1 = preview.Count > 0 ? new PersonTileViewModel(preview[0]) : null;
			Person2 = preview.Count > 1 ? new PersonTileViewModel(preview[1]) : null;
			Person3 = preview.Count > 2 ? new PersonTileViewModel(preview[2]) : null;
			RemainingCount = Math.Max(0, TotalPersons - Math.Min(preview.Count, PreviewCount));
		}

		// Depth-first: this group's own persons first, then descend into
		// subgroups, so a folder with any direct members previews those first.
		private static IEnumerable<PersonItem> CollectPreviewPersons(PeopleGroupItem group)
		{
			foreach (var person in group.ChildPersons)
				yield return person;

			foreach (var subgroup in group.Subgroups)
				foreach (var person in CollectPreviewPersons(subgroup))
					yield return person;
		}
	}

	// Loads its own sample-face thumbnail lazily (fire-and-forget in the ctor),
	// same shape as PeopleSearch's per-tile thumbnail loading.
	public sealed partial class PersonTileViewModel : ObservableObject
	{
		public PersonItem Item { get; }

		public string Text => Item.Text ?? string.Empty;

		public int MediaCount => Item.Person.MediaCount;

		// A real, clustered-but-unnamed person (Tier 1) is nameable directly on its
		// People-view tile — no dialog. See store/people_tree.py's tree filter fix.
		public bool IsUnnamed => Item.Person.Name is null;

		public Visibility NameVisibility => IsUnnamed ? Visibility.Collapsed : Visibility.Visible;

		public Visibility NameBoxVisibility => IsUnnamed ? Visibility.Visible : Visibility.Collapsed;

		// Cause-and-effect for the inline name box: a failed save must say so, not
		// silently leave the box sitting there looking like nothing happened.
		private string? nameError;
		public string? NameError
		{
			get => nameError;
			private set => SetProperty(ref nameError, value);
		}

		public Visibility NameErrorVisibility => NameError is null ? Visibility.Collapsed : Visibility.Visible;

		private BitmapImage? thumbnail;
		public BitmapImage? Thumbnail
		{
			get => thumbnail;
			private set => SetProperty(ref thumbnail, value);
		}

		public PersonTileViewModel(PersonItem item)
		{
			Item = item;
			_ = LoadThumbnailAsync();
		}

		private async Task LoadThumbnailAsync()
		{
			if (Item.Person.SampleFaceIds.Count == 0)
				return;

			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
					return;

				var bytes = await engine.Api.Persons.FaceThumbnailAsync(Item.LibraryId, Item.Person.SampleFaceIds[0], 128);
				var bitmap = await bytes.ToBitmapAsync();
				if (bitmap is null)
					return;

				await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() => Thumbnail = bitmap);
			}
			// Thumbnail loading is best-effort; the tile just shows its fallback glyph.
			catch (Exception)
			{
			}
		}

		// Committed from the tile's inline name box (Enter key, LostFocus, or the
		// confirm button) instead of the Settings page's rename dialog — this is
		// the browsing-view path.
		public async Task NameAsync(string name)
		{
			name = name.Trim();
			if (string.IsNullOrEmpty(name) || !IsUnnamed)
				return;

			NameError = null;
			OnPropertyChanged(nameof(NameErrorVisibility));

			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
				{
					NameError = Strings.MediaMind_NameSaveFailed.GetLocalizedResource();
					OnPropertyChanged(nameof(NameErrorVisibility));
					return;
				}

				await engine.Api.Persons.RenameAsync(Item.LibraryId, Item.Person.Id, name);
				Item.UpdateFrom(Item.Person with { Name = name });
				OnPropertyChanged(nameof(Text));
				OnPropertyChanged(nameof(IsUnnamed));
				OnPropertyChanged(nameof(NameVisibility));
				OnPropertyChanged(nameof(NameBoxVisibility));
			}
			// The box stays visible with what the user typed (IsUnnamed is still true)
			// so nothing is lost — but silence would read as "it saved" when it didn't.
			catch (Exception)
			{
				NameError = Strings.MediaMind_NameSaveFailed.GetLocalizedResource();
				OnPropertyChanged(nameof(NameErrorVisibility));
			}
		}
	}
}

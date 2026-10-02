// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Services.MediaMind;
using Microsoft.UI.Xaml;
using System.Net;
using System.Net.Http;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Files.App.ViewModels.People
{
	// MediaMind: the item view models of the People page (docs/PEOPLE_VIEW_V2_DESIGN.md).

	// What a drag carries. WinUI drag data is only readable asynchronously, so the
	// dragged keys ride in this static instead — a People drag never leaves the page.
	internal static class PeopleDragPayload
	{
		public static IReadOnlyList<string>? Keys { get; set; }

		public static string? Label { get; set; }
	}

	// One person (identity) tile. The thumbnail is fetched the first time the tile
	// is actually bound (i.e. realized by the virtualizing GridView), and through a
	// small gate, so thousands of tiles never fire thousands of requests at once.
	public sealed partial class PeopleTileViewModel : ObservableObject
	{
		private static readonly SemaphoreSlim thumbnailGate = new(6);

		public PeopleEntry Entry { get; }

		public IReadOnlyList<string> Keys => Entry.Keys;

		public string Text => Entry.Name ?? Entry.AutoLabel;

		public int MediaCount => Entry.MediaCount;

		public bool IsUnnamed => Entry.Name is null;

		public Visibility NameVisibility => IsUnnamed ? Visibility.Collapsed : Visibility.Visible;

		public Visibility NameBoxVisibility => IsUnnamed ? Visibility.Visible : Visibility.Collapsed;

		public string? DuplicateLabel { get; }

		public Visibility DuplicateVisibility => DuplicateLabel is null ? Visibility.Collapsed : Visibility.Visible;

		// The engine's person-media view is per library; a linked identity opens its first member's.
		public string Path => $"person:{Entry.Members[0].LibraryId}:{Entry.Members[0].LocalPersonId}";

		private bool isPinned;
		public bool IsPinned
		{
			get => isPinned;
			set
			{
				if (SetProperty(ref isPinned, value))
				{
					OnPropertyChanged(nameof(PinGlyph));
					OnPropertyChanged(nameof(PinButtonVisibility));
				}
			}
		}

		public string PinGlyph => IsPinned ? "" : "";

		private bool isHovered;
		public bool IsHovered
		{
			get => isHovered;
			set
			{
				if (SetProperty(ref isHovered, value))
					OnPropertyChanged(nameof(PinButtonVisibility));
			}
		}

		public Visibility PinButtonVisibility => IsPinned || IsHovered ? Visibility.Visible : Visibility.Collapsed;

		private string? nameError;
		public string? NameError
		{
			get => nameError;
			private set
			{
				if (SetProperty(ref nameError, value))
					OnPropertyChanged(nameof(NameErrorVisibility));
			}
		}

		public Visibility NameErrorVisibility => NameError is null ? Visibility.Collapsed : Visibility.Visible;

		private bool thumbnailRequested;
		private BitmapImage? thumbnail;
		public BitmapImage? Thumbnail
		{
			get
			{
				if (!thumbnailRequested)
				{
					thumbnailRequested = true;
					_ = LoadThumbnailAsync();
				}

				return thumbnail;
			}
			private set => SetProperty(ref thumbnail, value);
		}

		public PeopleTileViewModel(PeopleEntry entry, string? duplicateLabel = null)
		{
			Entry = entry;
			DuplicateLabel = duplicateLabel;
			isPinned = entry.Pinned;
		}

		// Raised (on the UI thread) when the engine finds this is not a person at all.
		public event Action<PeopleTileViewModel>? Unusable;

		// The engine picks the best face that can actually be cropped, skipping ones it
		// cannot decode. A member the engine rules out (410) is dropped; a tile whose
		// every member is ruled out is not a person and leaves the page. Anything else
		// (engine busy, slow drive) is retried once, then the initials stay.
		private async Task LoadThumbnailAsync()
		{
			await thumbnailGate.WaitAsync();
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
					return;

				var ruledOut = 0;
				foreach (var member in Entry.Members)
				{
					for (var attempt = 0; attempt < 2; attempt++)
					{
						try
						{
							var bytes = await engine.Api.PeopleView.PersonThumbnailAsync(member.LibraryId, member.LocalPersonId, 160);
							if (await bytes.ToBitmapAsync() is { } bitmap)
							{
								await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() => Thumbnail = bitmap);
								return;
							}

							break;
						}
						catch (HttpRequestException ex) when (ex.StatusCode == HttpStatusCode.Gone)
						{
							ruledOut++;
							break;
						}
						catch (Exception)
						{
							if (attempt == 0)
								await Task.Delay(1500);
						}
					}
				}

				if (ruledOut == Entry.Members.Count)
					await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() => Unusable?.Invoke(this));
			}
			finally
			{
				thumbnailGate.Release();
			}
		}

		// Committed from the tile's inline name box (Enter, clicking away, or the check button).
		public async Task<bool> NameAsync(string name)
		{
			name = name.Trim();
			if (string.IsNullOrEmpty(name) || !IsUnnamed)
				return false;

			NameError = null;
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
				{
					NameError = Strings.MediaMind_NameSaveFailed.GetLocalizedResource();
					return false;
				}

				var member = Entry.Members[0];
				await engine.Api.Persons.RenameAsync(member.LibraryId, member.LocalPersonId, name);
				return true;
			}
			// The box stays visible with what was typed so nothing is lost, but silence
			// would read as "saved" when it wasn't.
			catch (Exception)
			{
				NameError = Strings.MediaMind_NameSaveFailed.GetLocalizedResource();
				return false;
			}
		}
	}

	// A folder card or collection card: face-stack preview of the first people found
	// in its subtree, "+N" for the rest. Also stands in for a pin whose target is
	// offline or gone (Node is null), shown dimmed.
	public sealed partial class FolderCardViewModel : ObservableObject
	{
		private const int PreviewCount = 3;

		public PeopleNode? Node { get; }

		public string Key { get; }

		public bool IsCollection { get; }

		public bool Available => Node is not null;

		public double CardOpacity => Available ? 1 : 0.5;

		public string Text { get; }

		public string CountText { get; }

		public PeopleTileViewModel? Person1 { get; }

		public PeopleTileViewModel? Person2 { get; }

		public PeopleTileViewModel? Person3 { get; }

		public int RemainingCount { get; }

		public string RemainingLabel => $"+{RemainingCount}";

		public Visibility CollectionGlyphVisibility => IsCollection ? Visibility.Visible : Visibility.Collapsed;

		private bool isPinned;
		public bool IsPinned
		{
			get => isPinned;
			set
			{
				if (SetProperty(ref isPinned, value))
				{
					OnPropertyChanged(nameof(PinGlyph));
					OnPropertyChanged(nameof(PinButtonVisibility));
				}
			}
		}

		public string PinGlyph => IsPinned ? "" : "";

		private bool isHovered;
		public bool IsHovered
		{
			get => isHovered;
			set
			{
				if (SetProperty(ref isHovered, value))
					OnPropertyChanged(nameof(PinButtonVisibility));
			}
		}

		public Visibility PinButtonVisibility => IsPinned || IsHovered ? Visibility.Visible : Visibility.Collapsed;

		public FolderCardViewModel(PeopleNode node, IReadOnlyDictionary<string, PeopleEntry> entries)
		{
			Node = node;
			IsCollection = node.Kind == "collection";
			Key = IsCollection ? $"c:{node.Id}" : $"f:{node.Path}";
			Text = node.Name;
			CountText = node.TotalPersons.ToString();
			isPinned = node.Pinned;

			var preview = new List<PeopleEntry>(PreviewCount);
			CollectPreview(node, entries, preview);
			Person1 = preview.Count > 0 ? new PeopleTileViewModel(preview[0]) : null;
			Person2 = preview.Count > 1 ? new PeopleTileViewModel(preview[1]) : null;
			Person3 = preview.Count > 2 ? new PeopleTileViewModel(preview[2]) : null;
			RemainingCount = Math.Max(0, node.TotalPersons - preview.Count);
		}

		public FolderCardViewModel(PeoplePin pin)
		{
			Key = pin.Key;
			IsCollection = pin.Kind == "collection";
			Text = pin.Label ?? "MediaMind_PeopleUnavailable".GetLocalizedResource();
			CountText = "MediaMind_PeopleUnavailable".GetLocalizedResource();
			isPinned = true;
		}

		// Depth-first: this level's own people first, then descend, so a folder with
		// direct members previews those.
		private static void CollectPreview(PeopleNode node, IReadOnlyDictionary<string, PeopleEntry> entries, List<PeopleEntry> into)
		{
			foreach (var id in node.PersonIds)
			{
				if (into.Count >= PreviewCount)
					return;

				if (entries.TryGetValue(id, out var entry))
					into.Add(entry);
			}

			foreach (var subgroup in node.Subgroups)
			{
				if (into.Count >= PreviewCount)
					return;

				CollectPreview(subgroup, entries, into);
			}
		}
	}

	// A chip in the Collections bar (also a drop target).
	public sealed class CollectionChipViewModel(PeopleCollection collection, int count)
	{
		public string Id { get; } = collection.Id;

		public string Name { get; } = collection.Name;

		public string Text { get; } = $"{collection.Name}  {count}";
	}

	public sealed class BreadcrumbItemViewModel(string? nodeId, string text)
	{
		public string? NodeId { get; } = nodeId;

		public string Text { get; } = text;

		public Visibility ChevronVisibility => NodeId is null ? Visibility.Collapsed : Visibility.Visible;
	}
}

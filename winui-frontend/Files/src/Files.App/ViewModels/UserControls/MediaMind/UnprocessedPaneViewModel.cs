// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Services.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Files.App.ViewModels.UserControls.MediaMind
{
	// MediaMind: the folder view's "Not scanned" pane. Files the last scan could not
	// read or decode are kept by the engine with the reason; this lists the ones in the
	// folder being viewed so the user can open each one and tag it to a person by hand.
	public sealed partial class UnprocessedPaneViewModel : ObservableObject
	{
		private sealed record LibraryRef(string Id, string Root, string Name);

		private static readonly TimeSpan LibraryCacheLifetime = TimeSpan.FromSeconds(60);

		private List<LibraryRef> libraries = [];
		private DateTimeOffset librariesLoadedAt = DateTimeOffset.MinValue;
		private Dictionary<long, string> personNames = [];
		private string? currentDirectory;
		private int version;

		public ObservableCollection<UnprocessedItemViewModel> Items { get; } = [];

		// The library the listed files belong to (needed to tag them).
		public string? LibraryId { get; private set; }

		public Visibility PaneVisibility => Items.Count > 0 ? Visibility.Visible : Visibility.Collapsed;

		private bool isExpanded = true;
		public bool IsExpanded
		{
			get => isExpanded;
			set
			{
				if (SetProperty(ref isExpanded, value))
				{
					OnPropertyChanged(nameof(BodyVisibility));
					OnPropertyChanged(nameof(ChevronGlyph));
				}
			}
		}

		public Visibility BodyVisibility => IsExpanded ? Visibility.Visible : Visibility.Collapsed;

		public string ChevronGlyph => IsExpanded ? "" : "";

		public string HeaderText => string.Format("MediaMind_UnprocessedHeader".GetLocalizedResource(), Items.Count);

		public UnprocessedPaneViewModel()
		{
			Ioc.Default.GetRequiredService<IMediaMindEngineService>().JobUpdated += (_, job) =>
			{
				// A finished scan changes which files are listed.
				if (job.Type == "faces" && job.State is "succeeded" or "failed" or "cancelled")
					MainWindow.Instance.DispatcherQueue.TryEnqueue(() => _ = ShowForAsync(currentDirectory, forceLibraries: true));
			};
		}

		public async Task ShowForAsync(string? directory, bool forceLibraries = false)
		{
			currentDirectory = directory;
			var mine = Interlocked.Increment(ref version);

			try
			{
				if (!IsFileSystemPath(directory))
				{
					Clear();
					return;
				}

				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is not { } api)
				{
					Clear();
					return;
				}

				if (forceLibraries || DateTimeOffset.UtcNow - librariesLoadedAt > LibraryCacheLifetime || FindLibrary(directory!) is null)
				{
					libraries = (await api.Libraries.ListAsync()).Select(l => new LibraryRef(l.Id, l.Path, l.Name)).ToList();
					librariesLoadedAt = DateTimeOffset.UtcNow;
				}

				var library = FindLibrary(directory!);
				if (library is null)
				{
					Clear();
					return;
				}

				var under = RelativeUnder(library.Root, directory!);
				var files = await api.Unprocessed.ListAsync(library.Id, under);

				if (files.Any(f => f.PersonIds.Count > 0))
					personNames = (await api.Persons.ListAsync(library.Id)).Persons.ToDictionary(p => p.Id, p => p.Name ?? p.AutoLabel);

				if (mine != version)
					return; // the user already moved on to another folder

				await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() =>
				{
					LibraryId = library.Id;
					Items.Clear();
					foreach (var file in files)
						Items.Add(new UnprocessedItemViewModel(file, file.PersonIds.Select(id => personNames.GetValueOrDefault(id)).Where(n => n is not null).Select(n => n!).ToList()));

					RaiseCounts();
				});
			}
			// The pane is a convenience listing: if the engine cannot answer, the folder view is simply shown without it.
			catch (Exception)
			{
				if (mine == version)
					Clear();
			}
		}

		private void Clear()
		{
			_ = MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() =>
			{
				Items.Clear();
				RaiseCounts();
			});
		}

		private void RaiseCounts()
		{
			OnPropertyChanged(nameof(PaneVisibility));
			OnPropertyChanged(nameof(HeaderText));
		}

		private static bool IsFileSystemPath(string? path)
			=> !string.IsNullOrWhiteSpace(path)
				&& (path.StartsWith(@"\\", StringComparison.Ordinal) || (path.Length >= 2 && char.IsLetter(path[0]) && path[1] == ':'));

		private static string Normalize(string path)
			=> Utils.MediaMind.MediaMindPaths.Canonical(path);

		private LibraryRef? FindLibrary(string directory)
		{
			var dir = Normalize(directory);
			return libraries
				.Where(l =>
				{
					var root = Normalize(l.Root);
					return dir.Equals(root, StringComparison.OrdinalIgnoreCase) || dir.StartsWith(root + "\\", StringComparison.OrdinalIgnoreCase);
				})
				.OrderByDescending(l => l.Root.Length)
				.FirstOrDefault();
		}

		private static string? RelativeUnder(string root, string directory)
		{
			var rel = Normalize(directory)[Normalize(root).Length..].Trim('\\');
			return rel.Length == 0 ? null : rel.Replace('\\', '/');
		}

		public async Task<bool> TagAsync(UnprocessedItemViewModel item, long personId)
			=> await RunAsync(api => api.Unprocessed.TagAsync(LibraryId!, item.File.Path, personId));

		public async Task<bool> UntagAsync(UnprocessedItemViewModel item)
			=> await RunAsync(async api =>
			{
				foreach (var id in item.File.PersonIds)
					await api.Unprocessed.UntagAsync(LibraryId!, item.File.Path, id);
			});

		private async Task<bool> RunAsync(Func<MediaMindApiClient, Task> action)
		{
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (LibraryId is null || !await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is not { } api)
					return false;

				await action(api);
				await ShowForAsync(currentDirectory);
				return true;
			}
			catch (Exception)
			{
				return false;
			}
		}

		// The people of the library, for the tag chooser.
		public async Task<List<PersonChoiceViewModel>> LoadPersonChoicesAsync()
		{
			var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
			if (LibraryId is null || !await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is not { } api)
				return [];

			var libraryId = LibraryId;
			var persons = (await api.Persons.ListAsync(libraryId)).Persons;
			return persons
				.OrderBy(p => p.Name is null ? 1 : 0)
				.ThenByDescending(p => p.MediaCount)
				.Select(p => new PersonChoiceViewModel(libraryId, p))
				.ToList();
		}
	}

	// One not-scanned file.
	public sealed class UnprocessedItemViewModel(UnprocessedFile file, IReadOnlyList<string> taggedNames)
	{
		public UnprocessedFile File { get; } = file;

		public string Name => System.IO.Path.GetFileName(File.Path);

		public string AbsPath => File.AbsPath;

		public string Glyph => File.Kind == "video" ? "" : "";

		// "reason · size · tried N times", plus the sub-folder when it is not the one being viewed.
		public string Detail
		{
			get
			{
				var parts = new List<string> { File.Message, SizeText };
				if (File.Attempts > 1)
					parts.Add(string.Format("MediaMind_UnprocessedAttempts".GetLocalizedResource(), File.Attempts));

				return string.Join("  ·  ", parts);
			}
		}

		public string SizeText
		{
			get
			{
				double size = File.Size;
				string[] units = ["B", "KB", "MB", "GB", "TB"];
				var unit = 0;
				while (size >= 1024 && unit < units.Length - 1)
				{
					size /= 1024;
					unit++;
				}

				return $"{size:0.#} {units[unit]}";
			}
		}

		public bool IsTagged => taggedNames.Count > 0;

		public string TaggedText => string.Format("MediaMind_UnprocessedTagged".GetLocalizedResource(), string.Join(", ", taggedNames));

		public Visibility TaggedVisibility => IsTagged ? Visibility.Visible : Visibility.Collapsed;

		public Visibility UntaggedVisibility => IsTagged ? Visibility.Collapsed : Visibility.Visible;
	}

	// One person in the tag chooser; the face loads lazily and through a small gate.
	public sealed partial class PersonChoiceViewModel : ObservableObject
	{
		private static readonly SemaphoreSlim gate = new(4);

		private readonly string libraryId;
		private bool requested;
		private BitmapImage? thumbnail;

		public Person Person { get; }

		public string Text => Person.Name ?? Person.AutoLabel;

		public string CountText => Person.MediaCount.ToString();

		public BitmapImage? Thumbnail
		{
			get
			{
				if (!requested)
				{
					requested = true;
					_ = LoadAsync();
				}

				return thumbnail;
			}
			private set => SetProperty(ref thumbnail, value);
		}

		public PersonChoiceViewModel(string libraryId, Person person)
		{
			this.libraryId = libraryId;
			Person = person;
		}

		private async Task LoadAsync()
		{
			if (Person.SampleFaceIds.Count == 0)
				return;

			await gate.WaitAsync();
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is not { } api)
					return;

				var bytes = await api.Persons.FaceThumbnailAsync(libraryId, Person.SampleFaceIds[0], 96);
				if (await bytes.ToBitmapAsync() is { } bitmap)
					await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() => Thumbnail = bitmap);
			}
			// Best-effort: initials stay.
			catch (Exception)
			{
			}
			finally
			{
				gate.Release();
			}
		}
	}
}

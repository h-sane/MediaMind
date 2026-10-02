// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Services.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Files.App.ViewModels.People
{
	// MediaMind: the in-page person pop-up on the People page — the person's face,
	// an editable name, and every photo they appear in. Opening it never navigates,
	// so the People page underneath (scroll, mode, filters) stays exactly as it was.
	public sealed partial class PersonDetailViewModel : ObservableObject
	{
		public PeopleTileViewModel Tile { get; }

		public ObservableCollection<PersonMediaThumbViewModel> Items { get; } = [];

		public string Path => Tile.Path;

		private string name;
		public string Name
		{
			get => name;
			set => SetProperty(ref name, value);
		}

		private bool isLoading = true;
		public bool IsLoading
		{
			get => isLoading;
			private set
			{
				if (SetProperty(ref isLoading, value))
					OnPropertyChanged(nameof(LoadingVisibility));
			}
		}

		public Visibility LoadingVisibility => IsLoading ? Visibility.Visible : Visibility.Collapsed;

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

		private string countText = string.Empty;
		public string CountText
		{
			get => countText;
			private set => SetProperty(ref countText, value);
		}

		public PersonDetailViewModel(PeopleTileViewModel tile)
		{
			Tile = tile;
			name = tile.Entry.Name ?? string.Empty;
			_ = LoadAsync();
		}

		private async Task LoadAsync()
		{
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
				{
					Fail();
					return;
				}

				// A linked identity spans libraries; show every member's photos, once each.
				var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
				var thumbs = new List<PersonMediaThumbViewModel>();
				foreach (var member in Tile.Entry.Members)
				{
					var media = await engine.Api.Persons.MediaAsync(member.LibraryId, member.LocalPersonId);
					foreach (var item in media)
						if (seen.Add(item.AbsPath))
							thumbs.Add(new PersonMediaThumbViewModel(item, member.LibraryId));
				}

				await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() =>
				{
					foreach (var thumb in thumbs)
						Items.Add(thumb);

					CountText = string.Format("MediaMind_PersonDetailCount".GetLocalizedResource(), thumbs.Count);
					IsLoading = false;
				});
			}
			// Cause and effect: a failed load says so in the pop-up instead of showing an empty grid.
			catch (Exception)
			{
				Fail();
			}
		}

		private void Fail()
			=> _ = MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() =>
			{
				ErrorText = "MediaMind_PeopleActionFailed".GetLocalizedResource();
				IsLoading = false;
			});

		// Commits the header name box (Enter / clicking away). Renames every library's
		// person the identity is made of, so a linked identity stays one name.
		public async Task<bool> RenameAsync(string newName)
		{
			newName = newName.Trim();
			if (string.IsNullOrEmpty(newName) || newName == (Tile.Entry.Name ?? string.Empty))
				return false;

			ErrorText = null;
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
				{
					ErrorText = "MediaMind_NameSaveFailed".GetLocalizedResource();
					return false;
				}

				foreach (var member in Tile.Entry.Members)
					await engine.Api.Persons.RenameAsync(member.LibraryId, member.LocalPersonId, newName);

				Name = newName;
				return true;
			}
			catch (Exception)
			{
				ErrorText = "MediaMind_NameSaveFailed".GetLocalizedResource();
				return false;
			}
		}
	}

	// One photo in the person pop-up. The bitmap is created when the virtualizing
	// grid first binds the tile; videos show the person's face crop instead.
	public sealed partial class PersonMediaThumbViewModel : ObservableObject
	{
		private static readonly SemaphoreSlim faceGate = new(4);

		private readonly PersonMediaItem item;
		private readonly string libraryId;

		public string AbsPath => item.AbsPath;

		public bool IsVideo => item.Kind == "video";

		public Visibility VideoBadgeVisibility => IsVideo ? Visibility.Visible : Visibility.Collapsed;

		// A video the scan could not read (tagged by hand) has no face crop to show.
		public Visibility NoPreviewVisibility => IsVideo && item.FaceId is null ? Visibility.Visible : Visibility.Collapsed;

		private bool requested;
		private BitmapImage? image;
		public BitmapImage? Image
		{
			get
			{
				if (!requested)
				{
					requested = true;
					if (IsVideo)
						_ = LoadFaceAsync();
					else
						image = new BitmapImage { DecodePixelWidth = 240, UriSource = new Uri(item.AbsPath) };
				}

				return image;
			}
			private set => SetProperty(ref image, value);
		}

		public PersonMediaThumbViewModel(PersonMediaItem item, string libraryId)
		{
			this.item = item;
			this.libraryId = libraryId;
		}

		private async Task LoadFaceAsync()
		{
			if (item.FaceId is not { } faceId)
				return;

			await faceGate.WaitAsync();
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
					return;

				var bitmap = await (await engine.Api.Persons.FaceThumbnailAsync(libraryId, faceId, 240)).ToBitmapAsync();
				if (bitmap is not null)
					await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() => Image = bitmap);
			}
			// Best-effort: the tile keeps its empty backdrop.
			catch (Exception)
			{
			}
			finally
			{
				faceGate.Release();
			}
		}
	}
}

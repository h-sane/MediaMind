// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Services.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Files.App.ViewModels.People
{
	// "No faces found": the pictures and videos in which the scan found no face. The counts line
	// said "6 with no faces" with nowhere to see them (2026-09-27). Same one-at-a-time layout as
	// Group pictures: the list, the file itself (zoom, videos play), and what to do with it.
	public sealed partial class TeachPageViewModel
	{
		public ObservableCollection<TeachNoFaceItem> NoFaceFiles { get; } = [];

		public bool IsShowingNoFaces => SelectedFilter?.Kind == TeachFilterKind.NoFaces;

		public Visibility NoFacesVisibility => IsShowingNoFaces ? Visibility.Visible : Visibility.Collapsed;

		private async Task<List<NoFaceFile>> LoadNoFacesAsync(MediaMindApiClient api)
		{
			try
			{
				return await api.Teach.NoFacesAsync(LibraryId, SelectedFolder?.Path);
			}
			// The page works without it: the tab just doesn't show.
			catch (Exception)
			{
				return [];
			}
		}

		private void SetNoFaces(IEnumerable<NoFaceFile> files)
		{
			var index = CurrentNoFace is { } current ? NoFaceFiles.IndexOf(current) : 0;
			var keepId = CurrentNoFace?.File.FileId;
			NoFaceFiles.Clear();
			foreach (var f in files.Where(f => InFolder(f.Path)))
				NoFaceFiles.Add(new TeachNoFaceItem(LibraryId, f));
			CurrentNoFace = NoFaceFiles.FirstOrDefault(f => f.File.FileId == keepId)
				?? (NoFaceFiles.Count > 0 ? NoFaceFiles[Math.Clamp(index, 0, NoFaceFiles.Count - 1)] : null);
		}

		private TeachNoFaceItem? currentNoFace;
		public TeachNoFaceItem? CurrentNoFace
		{
			get => currentNoFace;
			set
			{
				if (!SetProperty(ref currentNoFace, value))
					return;
				noFaceVideoFailed = false;
				OnPropertyChanged(nameof(NoFaceFileName));
				OnPropertyChanged(nameof(NoFaceDetail));
				OnPropertyChanged(nameof(NoFaceAnswerVisibility));
				RaiseNoFaceMedia();
				_ = LoadNoFacePreviewAsync(value);
			}
		}

		public string NoFaceFileName => CurrentNoFace?.FileName ?? string.Empty;

		public string NoFaceDetail => CurrentNoFace?.Detail ?? string.Empty;

		public Visibility NoFaceAnswerVisibility => CurrentNoFace is null ? Visibility.Collapsed : Visibility.Visible;

		public bool NoFaceIsVideo => CurrentNoFace?.IsVideo == true;

		private bool noFaceVideoFailed;

		public Visibility NoFacePlayerVisibility => NoFaceIsVideo && !noFaceVideoFailed ? Visibility.Visible : Visibility.Collapsed;

		public Visibility NoFaceImageVisibility => NoFaceIsVideo && !noFaceVideoFailed ? Visibility.Collapsed : Visibility.Visible;

		private BitmapImage? noFacePreview;
		public BitmapImage? NoFacePreview
		{
			get => noFacePreview;
			private set => SetProperty(ref noFacePreview, value);
		}

		private bool noFacePreviewLoading;
		public bool NoFacePreviewLoading
		{
			get => noFacePreviewLoading;
			private set => SetProperty(ref noFacePreviewLoading, value);
		}

		private void RaiseNoFaceMedia()
		{
			OnPropertyChanged(nameof(NoFaceIsVideo));
			OnPropertyChanged(nameof(NoFacePlayerVisibility));
			OnPropertyChanged(nameof(NoFaceImageVisibility));
		}

		public void ReportNoFaceVideoFailed()
		{
			if (noFaceVideoFailed || CurrentNoFace is not { IsVideo: true } item)
				return;
			noFaceVideoFailed = true;
			RaiseNoFaceMedia();
			_ = LoadNoFacePreviewAsync(item);
		}

		public void ReportNoFaceVideo(bool loading)
			=> NoFacePreviewLoading = loading;

		// A picture is shown whole, from the file; a video's still (when it can't play) and a file
		// Windows can't decode come from the engine's large thumbnail.
		private async Task LoadNoFacePreviewAsync(TeachNoFaceItem? item)
		{
			NoFacePreview = null;
			if (item is null || item.IsVideo && !noFaceVideoFailed)
			{
				NoFacePreviewLoading = item is not null;
				return;
			}
			NoFacePreviewLoading = true;
			BitmapImage? bitmap = null;
			try
			{
				if (!item.IsVideo)
					bitmap = await (await Task.Run(() => SystemIO.File.ReadAllBytesAsync(item.File.AbsPath))).ToBitmapAsync();
			}
			// Offline drive, or a format Windows can't decode: the thumbnail below.
			catch (Exception)
			{
			}
			try
			{
				if (bitmap is null && await ApiAsync() is { } api)
					bitmap = await (await api.Teach.FileThumbnailAsync(LibraryId, item.File.Path, 1024)).ToBitmapAsync();
			}
			catch (Exception)
			{
			}
			if (CurrentNoFace != item)
				return;
			NoFacePreview = bitmap;
			NoFacePreviewLoading = false;
		}

		public void SelectNextNoFace(int step)
		{
			if (NoFaceFiles.Count == 0)
				return;
			var index = CurrentNoFace is { } current ? NoFaceFiles.IndexOf(current) : -1;
			CurrentNoFace = NoFaceFiles[Math.Clamp(index + step, 0, NoFaceFiles.Count - 1)];
		}

		// Into a folder the user picked; the engine moves it copy-then-delete, never overwriting.
		public Task MoveNoFaceAsync(TeachNoFaceItem item, string folder)
			=> RunAsync(string.Format(Strings.MediaMind_NoFaceMoving.GetLocalizedResource(), item.FileName), async api =>
			{
				var report = await api.FsOps.MoveAsync([item.File.AbsPath], folder);
				if (!report.Ok)
					throw new InvalidOperationException(report.Entries.FirstOrDefault(e => !string.IsNullOrEmpty(e.Error))?.Error ?? string.Empty);
				// Its old place drops from this folder's list now; the watcher indexes the new one.
				await api.Teach.ForgetMissingAsync(LibraryId);
				ShowStatus(InfoBarSeverity.Success,
					string.Format(Strings.MediaMind_NoFaceMovedTitle.GetLocalizedResource(), item.FileName), folder);
			});

		// After the page deleted it (Recycle Bin where the drive has one): the counts and list follow.
		public Task AfterNoFaceDeletedAsync(TeachNoFaceItem item)
			=> RunAsync(Strings.MediaMind_ActivityLoading.GetLocalizedResource(), async api =>
			{
				await api.Teach.ForgetMissingAsync(LibraryId);
				ShowStatus(InfoBarSeverity.Success,
					string.Format(Strings.MediaMind_NoFaceDeletedTitle.GetLocalizedResource(), item.FileName), string.Empty);
			});
	}

	public sealed partial class TeachNoFaceItem : ObservableObject
	{
		public NoFaceFile File { get; }

		private readonly string libraryId;

		public string FileName => SystemIO.Path.GetFileName(File.Path);

		public bool IsVideo => File.Kind == "video";

		// Where it is and what it is: "Photos\Old   2.4 MB   video".
		public string Detail
		{
			get
			{
				var folder = SystemIO.Path.GetDirectoryName(File.Path.Replace('/', '\\'));
				var parts = new List<string>();
				if (!string.IsNullOrEmpty(folder))
					parts.Add(folder);
				parts.Add(File.Size.ToSizeString());
				if (IsVideo)
					parts.Add(Strings.MediaMind_NoFaceVideo.GetLocalizedResource());
				return string.Join("\n", parts);
			}
		}

		private BitmapImage? thumbnail;
		public BitmapImage? Thumbnail
		{
			get => thumbnail;
			private set => SetProperty(ref thumbnail, value);
		}

		private bool thumbnailRequested;

		public TeachNoFaceItem(string libraryId, NoFaceFile file)
		{
			this.libraryId = libraryId;
			File = file;
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
					Thumbnail = await (await engine.Api.Teach.FileThumbnailAsync(libraryId, File.Path, 192)).ToBitmapAsync();
			}
			// A file that can't be decoded still gets its row and choices.
			catch (Exception)
			{
			}
		}
	}
}

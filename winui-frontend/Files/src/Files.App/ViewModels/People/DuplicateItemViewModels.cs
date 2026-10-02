// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Services.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Files.App.ViewModels.People
{
	// One set of copies in the Duplicates queue.
	public sealed partial class DuplicateGroupViewModel : ObservableObject
	{
		public DuplicateGroup Group { get; }

		public IReadOnlyList<DuplicateMemberViewModel> Members { get; }

		public bool IsExact => Group.Match == "exact";

		public string Title => string.Format(
			(IsExact ? Strings.MediaMind_DupExactCount : Strings.MediaMind_DupLookAlikeCount).GetLocalizedResource(), Members.Count);

		public string Detail => string.Format(
			Strings.MediaMind_DupFrees.GetLocalizedResource(), Members[0].FileName, Frees.ToSizeString());

		// What removing every copy but the chosen one gives back.
		public long Frees => Members.Where(m => !m.IsKeeper).Sum(m => m.File.Size);

		public DuplicateMemberViewModel Keeper => Members.First(m => m.IsKeeper);

		public BitmapImage? Thumbnail => Members[0].Thumbnail;

		public DuplicateGroupViewModel(string libraryId, string libraryRoot, DuplicateGroup group)
		{
			Group = group;
			Members = group.Files.Select((f, i) => new DuplicateMemberViewModel(libraryId, libraryRoot, f, i + 1)).ToList();
			var keeper = Members.FirstOrDefault(m => m.File.SuggestedKeep) ?? Members[0];
			keeper.IsKeeper = true;
			Members[0].PropertyChanged += (_, e) =>
			{
				if (e.PropertyName == nameof(DuplicateMemberViewModel.Thumbnail))
					OnPropertyChanged(nameof(Thumbnail));
			};
		}

		public void ChooseKeeper(DuplicateMemberViewModel keeper)
		{
			foreach (var m in Members)
				m.IsKeeper = m == keeper;
			OnPropertyChanged(nameof(Detail));
		}

		public void EnsureThumbnail() => Members[0].EnsureThumbnail(128);
	}

	// One copy: its preview and the facts that decide which copy to keep.
	public sealed partial class DuplicateMemberViewModel : ObservableObject
	{
		private readonly string libraryId;

		public DuplicateFile File { get; }

		// Shown on the card and used by the number keys.
		public int Number { get; }

		public string NumberText => Number.ToString();

		public string AbsPath { get; }

		public string FileName => SystemIO.Path.GetFileName(File.Path);

		public string Folder
		{
			get
			{
				var folder = SystemIO.Path.GetDirectoryName(File.Path.Replace('/', '\\'));
				return string.IsNullOrEmpty(folder) ? Strings.MediaMind_DupTopFolder.GetLocalizedResource() : folder;
			}
		}

		public string Facts => File.Width > 0 && File.Height > 0
			? string.Format(Strings.MediaMind_DupFacts.GetLocalizedResource(), File.Width, File.Height, File.Size.ToSizeString())
			: File.Size.ToSizeString();

		public string Modified => string.Format(Strings.MediaMind_DupModified.GetLocalizedResource(),
			DateTimeOffset.FromUnixTimeMilliseconds((long)(File.Mtime * 1000)).LocalDateTime.ToString("d MMM yyyy, HH:mm"));

		public bool IsVideo => File.Kind == "video";

		public Visibility VideoBadgeVisibility => IsVideo ? Visibility.Visible : Visibility.Collapsed;

		private bool isKeeper;
		public bool IsKeeper
		{
			get => isKeeper;
			set
			{
				if (SetProperty(ref isKeeper, value))
				{
					OnPropertyChanged(nameof(KeepVisibility));
					OnPropertyChanged(nameof(RemoveVisibility));
				}
			}
		}

		public Visibility KeepVisibility => IsKeeper ? Visibility.Visible : Visibility.Collapsed;

		public Visibility RemoveVisibility => IsKeeper ? Visibility.Collapsed : Visibility.Visible;

		private BitmapImage? thumbnail;
		public BitmapImage? Thumbnail
		{
			get => thumbnail;
			private set => SetProperty(ref thumbnail, value);
		}

		private int requestedSize;

		public DuplicateMemberViewModel(string libraryId, string libraryRoot, DuplicateFile file, int number)
		{
			this.libraryId = libraryId;
			File = file;
			Number = number;
			AbsPath = SystemIO.Path.Combine(libraryRoot, file.Path.Replace('/', '\\'));
		}

		// Asks once per size; a bigger request replaces a smaller preview.
		public void EnsureThumbnail(int size)
		{
			if (requestedSize >= size)
				return;
			requestedSize = size;
			_ = LoadAsync(size);
		}

		private async Task LoadAsync(int size)
		{
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (engine.Api is null)
					return;
				var bitmap = await (await engine.Api.Duplicates.ThumbnailAsync(libraryId, File.Id, size)).ToBitmapAsync();
				if (bitmap is not null)
					await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() => Thumbnail = bitmap);
			}
			// Best-effort; the card keeps its placeholder.
			catch (Exception)
			{
				requestedSize = 0;
			}
		}
	}
}

// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Services.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.UI;

namespace Files.App.ViewModels.People
{
	// Who's who: one face at a time, full size — the whole photo with the face outlined, or the
	// video playing — so a face can be judged before it is named. Walks the faces the grid shows
	// (No one named yet, a person, All), in the grid's order.
	public sealed partial class TeachViewerViewModel : ObservableObject
	{
		private readonly string libraryId;
		private readonly Func<TeachFaceTileViewModel, string, Task<bool>> name;
		private IReadOnlyList<TeachFaceTileViewModel> faces = [];
		private long previewFaceId;
		private bool videoFailed;

		public TeachViewerViewModel(string libraryId, Func<TeachFaceTileViewModel, string, Task<bool>> name)
		{
			this.libraryId = libraryId;
			this.name = name;
		}

		public ObservableCollection<TeachViewerPerson> People { get; } = [];

		private TeachFaceTileViewModel? current;
		public TeachFaceTileViewModel? Current
		{
			get => current;
			private set
			{
				if (!SetProperty(ref current, value))
					return;
				videoFailed = false;
				OnPropertyChanged(nameof(Visibility));
				OnPropertyChanged(nameof(IsOpen));
				OnPropertyChanged(nameof(FileName));
				OnPropertyChanged(nameof(NowText));
				OnPropertyChanged(nameof(PositionText));
				OnPropertyChanged(nameof(IsVideo));
				OnPropertyChanged(nameof(ImageVisibility));
				OnPropertyChanged(nameof(PlayerVisibility));
				OnPropertyChanged(nameof(VideoNoteVisibility));
				OnPropertyChanged(nameof(CanGoBack));
				OnPropertyChanged(nameof(CanGoForward));
				_ = LoadPreviewAsync(value, false);
			}
		}

		public bool IsOpen => Current is not null;

		public Visibility Visibility => IsOpen ? Visibility.Visible : Visibility.Collapsed;

		public bool IsVideo => Current?.Face.Kind == "video";

		public string FileName => Current?.FileName ?? string.Empty;

		// Who this face is now, so a named face can be checked or renamed.
		public string NowText => Current is null ? string.Empty
			: string.IsNullOrEmpty(Current.Face.PersonName)
				? Strings.MediaMind_ViewerNoName.GetLocalizedResource()
				: string.Format(Strings.MediaMind_ViewerNamed.GetLocalizedResource(), Current.Face.PersonName);

		private int Index => Current is null ? -1 : IndexOf(Current);

		private int IndexOf(TeachFaceTileViewModel tile)
		{
			for (var i = 0; i < faces.Count; i++)
				if (faces[i] == tile)
					return i;
			return -1;
		}

		public string PositionText => Current is null ? string.Empty
			: string.Format(Strings.MediaMind_ViewerPosition.GetLocalizedResource(), Index + 1, faces.Count);

		public bool CanGoBack => Index > 0;

		public bool CanGoForward => Index >= 0 && Index < faces.Count - 1;

		// The player shows videos; the picture shows photos, and a video's frame when it can't play.
		public Visibility PlayerVisibility => IsVideo && !videoFailed ? Visibility.Visible : Visibility.Collapsed;

		public Visibility ImageVisibility => IsVideo && !videoFailed ? Visibility.Collapsed : Visibility.Visible;

		public Visibility VideoNoteVisibility => IsVideo && videoFailed ? Visibility.Visible : Visibility.Collapsed;

		private BitmapImage? preview;
		public BitmapImage? Preview
		{
			get => preview;
			private set => SetProperty(ref preview, value);
		}

		private bool isLoading;
		public bool IsLoading
		{
			get => isLoading;
			private set => SetProperty(ref isLoading, value);
		}

		private string error = string.Empty;
		public string Error
		{
			get => error;
			private set
			{
				if (SetProperty(ref error, value))
					OnPropertyChanged(nameof(ErrorVisibility));
			}
		}

		public Visibility ErrorVisibility => Error.Length > 0 ? Visibility.Visible : Visibility.Collapsed;

		private bool isBusy;
		public bool IsBusy
		{
			get => isBusy;
			private set
			{
				if (SetProperty(ref isBusy, value))
					OnPropertyChanged(nameof(CanName));
			}
		}

		public bool CanName => !IsBusy;

		public void Open(TeachFaceTileViewModel tile, IReadOnlyList<TeachFaceTileViewModel> list)
		{
			faces = list;
			Current = tile;
		}

		public void Close() => Current = null;

		public void Next()
		{
			if (CanGoForward)
				Current = faces[Index + 1];
		}

		public void Previous()
		{
			if (CanGoBack)
				Current = faces[Index - 1];
		}

		// The grid's list changed (a face was named, the folder changed, the page reloaded). A face
		// that left the list (named from No one named yet) gives way to the one now in its place.
		public void SetList(IReadOnlyList<TeachFaceTileViewModel> list)
		{
			if (Current is null)
				return;
			var at = Math.Max(0, Index);
			faces = list;
			if (IndexOf(Current) < 0)
				Current = list.Count == 0 ? null : list[Math.Min(at, list.Count - 1)];
			OnPropertyChanged(nameof(NowText));
			OnPropertyChanged(nameof(PositionText));
			OnPropertyChanged(nameof(CanGoBack));
			OnPropertyChanged(nameof(CanGoForward));
		}

		public void SetPeople(IEnumerable<TeachViewerPerson> people)
		{
			People.Clear();
			foreach (var p in people)
				People.Add(p);
		}

		// Names the face and moves on: the face after it, or the one that took its place.
		public async Task NameAsync(string person)
		{
			if (Current is not { } tile || IsBusy || string.IsNullOrWhiteSpace(person))
				return;
			IsBusy = true;
			try
			{
				if (await name(tile, person) && Current == tile)
					Next();
			}
			finally
			{
				IsBusy = false;
			}
		}

		// The page's player could not decode the video: show the frame the face was found in.
		public void ReportVideoFailed()
		{
			if (Current is not { } tile || !IsVideo || videoFailed)
				return;
			videoFailed = true;
			OnPropertyChanged(nameof(ImageVisibility));
			OnPropertyChanged(nameof(PlayerVisibility));
			OnPropertyChanged(nameof(VideoNoteVisibility));
			_ = LoadPreviewAsync(tile, true);
		}

		public void ReportVideo(bool loading)
			=> IsLoading = loading;

		private async Task LoadPreviewAsync(TeachFaceTileViewModel? tile, bool videoFrame)
		{
			Preview = null;
			Error = string.Empty;
			if (tile is null || tile.Face.Kind == "video" && !videoFrame)
				return;
			var faceId = previewFaceId = tile.Face.FaceId;
			IsLoading = true;
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (engine.Api is null)
					return;
				var bitmap = await (await engine.Api.Teach.FrameAsync(libraryId, faceId)).ToBitmapAsync();
				if (previewFaceId == faceId)
					Preview = bitmap;
			}
			catch (MediaMindApiException ex)
			{
				if (previewFaceId == faceId)
					Error = ex.Message;
			}
			catch (Exception)
			{
				if (previewFaceId == faceId)
					Error = Strings.MediaMind_ReviewPreviewFailed.GetLocalizedResource();
			}
			finally
			{
				if (previewFaceId == faceId)
					IsLoading = false;
			}
		}
	}

	// A named person as a button in the viewer: their review colour, and the digit that picks them.
	public sealed record TeachViewerPerson(string Name, string Key, Color TintColor)
	{
		public SolidColorBrush Background { get; } = new(Color.FromArgb(0x2E, TintColor.R, TintColor.G, TintColor.B));

		public SolidColorBrush Border { get; } = new(Color.FromArgb(0x80, TintColor.R, TintColor.G, TintColor.B));

		public string Label => Key.Length > 0 ? $"{Name}  ({Key})" : Name;
	}
}

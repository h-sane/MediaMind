// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Services.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.UI;

namespace Files.App.ViewModels.People
{
	// MediaMind: the "Needs your check" tab of Who's who — faces the sort was not sure
	// about (pending_matches). Each is decided against the whole original picture, not a
	// small crop: Yes (it becomes one more example), No, or It's someone else.
	public sealed partial class TeachReviewViewModel : ObservableObject
	{
		private readonly string libraryId;
		private readonly Func<long?, IEnumerable<TeachFaceTileViewModel>> examplesOf;
		private readonly Action<long, long?, string?> onDecided;
		private readonly Action<string> onFileDeleted;
		private readonly Action<long> onFaceIgnored;
		private long previewFaceId;

		public ObservableCollection<TeachReviewItemViewModel> Items { get; } = [];

		public ObservableCollection<TeachFaceTileViewModel> CandidateExamples { get; } = [];

		private TeachReviewItemViewModel? current;
		public TeachReviewItemViewModel? Current
		{
			get => current;
			private set
			{
				if (SetProperty(ref current, value))
				{
					videoFailed = false;
					OnPropertyChanged(nameof(VideoNote));
					OnPropertyChanged(nameof(VideoNoteVisibility));
					OnPropertyChanged(nameof(CanDecide));
					OnPropertyChanged(nameof(QuestionText));
					OnPropertyChanged(nameof(YesText));
					OnPropertyChanged(nameof(DeleteText));
					OnPropertyChanged(nameof(DetailText));
					OnPropertyChanged(nameof(ExamplesHeader));
					OnPropertyChanged(nameof(PreviewVisibility));
					OnPropertyChanged(nameof(ImageVisibility));
					OnPropertyChanged(nameof(PlayerVisibility));
					OnPropertyChanged(nameof(DoneVisibility));
				}
			}
		}

		private IReadOnlyList<TeachReviewItemViewModel> selection = [];

		private BitmapImage? preview;
		public BitmapImage? Preview
		{
			get => preview;
			private set => SetProperty(ref preview, value);
		}

		private bool isPreviewLoading;
		public bool IsPreviewLoading
		{
			get => isPreviewLoading;
			private set => SetProperty(ref isPreviewLoading, value);
		}

		private string previewError = string.Empty;
		public string PreviewError
		{
			get => previewError;
			private set
			{
				if (SetProperty(ref previewError, value))
					OnPropertyChanged(nameof(PreviewErrorVisibility));
			}
		}

		public Visibility PreviewErrorVisibility => PreviewError.Length > 0 ? Visibility.Visible : Visibility.Collapsed;

		// Videos play in the preview (the page owns the player); photos show the outlined picture,
		// and so does a video Windows can't decode (e.g. 10-bit H.264): the frame the face came from.
		private bool videoFailed;

		public Visibility ImageVisibility => Current?.IsVideo == true && !videoFailed ? Visibility.Collapsed : Visibility.Visible;

		public Visibility PlayerVisibility => Current?.IsVideo == true && !videoFailed ? Visibility.Visible : Visibility.Collapsed;

		public string VideoNote => videoFailed ? Strings.MediaMind_ReviewVideoFallback.GetLocalizedResource() : string.Empty;

		public Visibility VideoNoteVisibility => videoFailed ? Visibility.Visible : Visibility.Collapsed;

		public Visibility PreviewVisibility => Current is null ? Visibility.Collapsed : Visibility.Visible;

		public Visibility DoneVisibility => Current is null ? Visibility.Visible : Visibility.Collapsed;

		private bool isBusy;
		public bool IsBusy
		{
			get => isBusy;
			private set
			{
				if (SetProperty(ref isBusy, value))
					OnPropertyChanged(nameof(CanDecide));
			}
		}

		public bool CanDecide => !IsBusy && Current is not null;

		public string QuestionText => Current is null
			? string.Empty
			: string.Format(Strings.MediaMind_ReviewQuestion.GetLocalizedResource(), Current.Match.PersonName);

		public string YesText => selection.Count > 1
			? string.Format(Strings.MediaMind_ReviewYesMany.GetLocalizedResource(), selection.Count)
			: Strings.MediaMind_ReviewYes.GetLocalizedResource();

		public string DeleteText
		{
			get
			{
				var files = SelectedFiles().Count;
				return files > 1
					? string.Format(Strings.MediaMind_ReviewDeleteMany.GetLocalizedResource(), files)
					: Strings.MediaMind_ReviewDelete.GetLocalizedResource();
			}
		}

		// Distinct files behind the selected faces (one photo can hold several faces).
		public IReadOnlyList<string> SelectedFiles()
		{
			var targets = selection.Count > 0 ? selection : Current is null ? [] : [Current];
			return targets.Select(t => t.Match.AbsPath).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
		}

		public string DetailText => Current is null
			? string.Empty
			: !Current.IsVideo
				? Current.FileName
				: Current.ExtraFrames > 0
					? string.Format(Strings.MediaMind_ReviewFromVideoFrames.GetLocalizedResource(), Current.FileName, Current.ExtraFrames + 1)
					: string.Format(Strings.MediaMind_ReviewFromVideo.GetLocalizedResource(), Current.FileName);

		public string ExamplesHeader => Current is null
			? string.Empty
			: string.Format(Strings.MediaMind_ReviewExamplesOf.GetLocalizedResource(), Current.Match.PersonName);

		public string CountText => string.Format(Strings.MediaMind_ReviewRemaining.GetLocalizedResource(), Items.Count);

		private string errorText = string.Empty;
		public string ErrorText
		{
			get => errorText;
			private set
			{
				if (SetProperty(ref errorText, value))
					OnPropertyChanged(nameof(ErrorVisibility));
			}
		}

		public Visibility ErrorVisibility => ErrorText.Length > 0 ? Visibility.Visible : Visibility.Collapsed;

		public TeachReviewViewModel(string libraryId, Func<long?, IEnumerable<TeachFaceTileViewModel>> examplesOf, Action<long, long?, string?> onDecided, Action<string> onFileDeleted, Action<long> onFaceIgnored)
		{
			this.onFaceIgnored = onFaceIgnored;
			this.libraryId = libraryId;
			this.examplesOf = examplesOf;
			this.onDecided = onDecided;
			this.onFileDeleted = onFileDeleted;
		}

		// One soft colour per person, so a run of the same name reads at a glance and the switch
		// to the next person is noticed without reading. Muted mid-tones that sit on both themes.
		private static readonly Color[] PersonTints =
		[
			Color.FromArgb(255, 0xF0, 0x62, 0x92), // rose
			Color.FromArgb(255, 0x4D, 0xB6, 0xAC), // teal
			Color.FromArgb(255, 0xFF, 0xB7, 0x4D), // amber
			Color.FromArgb(255, 0x95, 0x75, 0xCD), // violet
			Color.FromArgb(255, 0x4F, 0xC3, 0xF7), // sky
			Color.FromArgb(255, 0xAE, 0xD5, 0x81), // lime
			Color.FromArgb(255, 0xFF, 0x8A, 0x65), // coral
			Color.FromArgb(255, 0x79, 0x86, 0xCB), // indigo
		];

		// A person's colour, by their place among the library's people (ordered by id), so the
		// queue and the viewer's name buttons agree.
		public static Color TintOf(long personId, IReadOnlyList<long> people)
		{
			var i = 0;
			while (i < people.Count && people[i] != personId)
				i++;
			return PersonTints[i % PersonTints.Length];
		}

		// Grouped by person, the person with the most questions first, so answers come in long
		// runs of one name; within a person the likeliest match comes first (the server's order).
		public void Load(IEnumerable<PendingMatch> matches, IReadOnlyList<long> people)
		{
			Items.Clear();
			var list = matches.ToList();
			var counts = list.GroupBy(m => m.PersonId).ToDictionary(g => g.Key, g => g.Count());
			foreach (var m in list.OrderByDescending(m => counts[m.PersonId]).ThenBy(m => m.PersonId))
				Items.Add(new TeachReviewItemViewModel(libraryId, m, TintOf(m.PersonId, people)));
			OnPropertyChanged(nameof(CountText));
			Select(Items.Count > 0 ? [Items[0]] : []);
		}

		// The page mirrors the queue list's selection here; the first selected item is previewed.
		public void Select(IReadOnlyList<TeachReviewItemViewModel> items)
		{
			selection = items;
			OnPropertyChanged(nameof(YesText));
			OnPropertyChanged(nameof(DeleteText));
			var next = items.Count > 0 ? items[0] : null;
			if (next == Current)
				return;
			Current = next;
			CandidateExamples.Clear();
			if (next is not null)
			{
				foreach (var e in examplesOf(next.Match.PersonId).Take(6))
				{
					e.EnsureThumbnail();
					CandidateExamples.Add(e);
				}
			}
			_ = LoadPreviewAsync(next, false);
		}

		private async Task LoadPreviewAsync(TeachReviewItemViewModel? item, bool videoFrame)
		{
			Preview = null;
			PreviewError = string.Empty;
			if (item is null || item.IsVideo && !videoFrame)
				return;
			var faceId = previewFaceId = item.Match.FaceId;
			IsPreviewLoading = true;
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (engine.Api is null)
					return;
				var bytes = await engine.Api.Teach.FrameAsync(libraryId, faceId);
				var bitmap = await bytes.ToBitmapAsync();
				if (previewFaceId == faceId)
					Preview = bitmap;
			}
			catch (MediaMindApiException ex)
			{
				if (previewFaceId == faceId)
					PreviewError = ex.Message;
			}
			catch (Exception)
			{
				if (previewFaceId == faceId)
					PreviewError = Strings.MediaMind_ReviewPreviewFailed.GetLocalizedResource();
			}
			finally
			{
				if (previewFaceId == faceId)
					IsPreviewLoading = false;
			}
		}

		// The page's video player reports buffering here, so it shows on screen.
		public void ReportVideo(bool loading)
			=> IsPreviewLoading = loading;

		// The player could not decode the current video: show its detected frame instead.
		public void ReportVideoFailed()
		{
			if (Current is not { IsVideo: true } item || videoFailed)
				return;
			videoFailed = true;
			OnPropertyChanged(nameof(ImageVisibility));
			OnPropertyChanged(nameof(PlayerVisibility));
			OnPropertyChanged(nameof(VideoNote));
			OnPropertyChanged(nameof(VideoNoteVisibility));
			_ = LoadPreviewAsync(item, true);
		}

		public Task YesAsync() => DecideAsync("confirmed", null, null);

		public Task NoAsync() => DecideAsync("rejected", null, null);

		public Task SomeoneElseAsync(long personId, string name) => DecideAsync("confirmed", personId, name);

		// Someone not among this folder's people (another group, say): naming them makes them a
		// person here, and the name is recognised in every other folder that gets scanned.
		public Task SomeoneNewAsync(string name)
			=> string.IsNullOrWhiteSpace(name) ? Task.CompletedTask : DecideAsync("confirmed", null, name.Trim(), async (api, targets) =>
				(await api.Teach.AddExamplesAsync(libraryId, targets.SelectMany(t => t.FaceIds).Distinct().ToList(), null, name.Trim())).PersonId);

		// Once `confirm` says yes, the cards go and the next face shows at once; `delete` (the app's
		// own delete, Recycle Bin where there is one) finishes in the background and returns true
		// only when the files are really gone. If it fails, the cards come back with the reason.
		public async Task DeleteSelectedFilesAsync(Func<IReadOnlyList<string>, Task<bool>> confirm, Func<IReadOnlyList<string>, Task<bool>> delete)
		{
			var files = SelectedFiles();
			if (files.Count == 0 || IsBusy || !await confirm(files))
				return;
			ErrorText = string.Empty;

			var gone = Items.Where(i => files.Contains(i.Match.AbsPath, StringComparer.OrdinalIgnoreCase)).ToList();
			if (gone.Count == 0)
				return;
			var positions = gone.Select(Items.IndexOf).ToList();
			var next = Items.Skip(positions[^1] + 1).FirstOrDefault(i => !gone.Contains(i))
				?? Items.FirstOrDefault(i => !gone.Contains(i));
			foreach (var g in gone)
				Items.Remove(g);
			OnPropertyChanged(nameof(CountText));
			Select(next is null ? [] : [next]);

			try
			{
				if (!await delete(files))
					throw new SystemIO.IOException(Strings.MediaMind_ReviewDeleteStillThere.GetLocalizedResource());
				foreach (var f in files)
					onFileDeleted(f);
				// The files are gone: close their questions so they never come back.
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (engine.Api is not null)
					await engine.Api.Pending.DecideAsync(libraryId, gone.Select(g => new PendingDecisionItem(g.Match.Id, "rejected")).ToList());
			}
			catch (Exception ex)
			{
				if (gone.Any(g => SystemIO.File.Exists(g.Match.AbsPath)))
				{
					for (var i = 0; i < gone.Count; i++)
						if (!Items.Contains(gone[i]))
							Items.Insert(Math.Min(positions[i], Items.Count), gone[i]);
					OnPropertyChanged(nameof(CountText));
					ErrorText = string.Format(Strings.MediaMind_ReviewDeleteFailed.GetLocalizedResource(), SystemIO.Path.GetFileName(files[0]), ex.Message);
				}
				else
					ErrorText = string.Format(Strings.MediaMind_ReviewDecideFailed.GetLocalizedResource(), ex.Message);
			}
		}

		// "Ignore face": only this face in this file (and its folded frames) stops counting, also
		// after rescans; the person and their other files are unaffected, and the file is untouched. Like delete, the card goes at once
		// and the server call follows; on failure the card comes back with the reason.
		public async Task IgnoreAsync()
		{
			var targets = selection.Count > 0 ? selection.ToList() : Current is null ? [] : [Current];
			if (targets.Count == 0 || IsBusy)
				return;
			ErrorText = string.Empty;
			var positions = targets.Select(Items.IndexOf).ToList();
			var next = Items.Skip(positions.Max() + 1).FirstOrDefault(i => !targets.Contains(i))
				?? Items.FirstOrDefault(i => !targets.Contains(i));
			foreach (var t in targets)
				Items.Remove(t);
			OnPropertyChanged(nameof(CountText));
			Select(next is null ? [] : [next]);

			var failed = new List<int>();
			var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
			for (var i = 0; i < targets.Count; i++)
			{
				try
				{
					if (engine.Api is null)
						throw new InvalidOperationException(Strings.MediaMind_ReviewEngineDown.GetLocalizedResource());
					var ignored = new HashSet<long>();
					foreach (var faceId in targets[i].FaceIds.Where(id => !ignored.Contains(id)))
					{
						foreach (var id in (await engine.Api.Persons.RejectFaceAsync(libraryId, faceId)).FaceIds)
							if (ignored.Add(id))
								onFaceIgnored(id);
					}
				}
				catch (Exception ex)
				{
					failed.Add(i);
					ErrorText = string.Format(Strings.MediaMind_ReviewIgnoreFailed.GetLocalizedResource(), ex.Message);
				}
			}
			foreach (var i in failed)
				Items.Insert(Math.Min(positions[i], Items.Count), targets[i]);
			if (failed.Count > 0)
				OnPropertyChanged(nameof(CountText));
		}

		public void Skip()
		{
			if (Current is null || Items.Count < 2)
				return;
			var i = Items.IndexOf(Current);
			Select([Items[(i + 1) % Items.Count]]);
		}

		// `send` replaces the pending decision call and returns the person the faces went to.
		private async Task DecideAsync(string decision, long? reassignTo, string? reassignName,
			Func<MediaMindApiClient, List<TeachReviewItemViewModel>, Task<long>>? send = null)
		{
			var targets = selection.Count > 0 ? selection.ToList() : Current is null ? [] : [Current];
			if (targets.Count == 0 || IsBusy)
				return;
			IsBusy = true;
			ErrorText = string.Empty;
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (engine.Api is null)
					return;
				if (send is not null)
					reassignTo = await send(engine.Api, targets);
				else
					await engine.Api.Pending.DecideAsync(libraryId,
						targets.Select(t => new PendingDecisionItem(t.Match.Id, decision, reassignTo)).ToList());

				var nextIndex = Items.IndexOf(targets[^1]) + 1;
				var next = Items.Skip(nextIndex).FirstOrDefault(i => !targets.Contains(i))
					?? Items.FirstOrDefault(i => !targets.Contains(i));
				foreach (var t in targets)
				{
					Items.Remove(t);
					// The server decided the folded frames too; mirror them in the face grid.
					foreach (var faceId in t.FaceIds)
					{
						if (decision == "confirmed")
							onDecided(faceId, reassignTo ?? t.Match.PersonId, reassignName ?? t.Match.PersonName);
						else
							onDecided(faceId, null, null);
					}
				}
				OnPropertyChanged(nameof(CountText));
				Select(next is null ? [] : [next]);
			}
			catch (Exception ex)
			{
				ErrorText = string.Format(Strings.MediaMind_ReviewDecideFailed.GetLocalizedResource(), ex.Message);
			}
			finally
			{
				IsBusy = false;
			}
		}
	}

	public sealed partial class TeachReviewItemViewModel : ObservableObject
	{
		public PendingMatch Match { get; }

		public string FileName => SystemIO.Path.GetFileName(Match.Path);

		public bool IsVideo => Match.Kind == "video";

		public Visibility VideoBadgeVisibility => IsVideo ? Visibility.Visible : Visibility.Collapsed;

		public string Question => string.Format(Strings.MediaMind_ReviewRowQuestion.GetLocalizedResource(), Match.PersonName);

		private BitmapImage? thumbnail;
		public BitmapImage? Thumbnail
		{
			get => thumbnail;
			private set => SetProperty(ref thumbnail, value);
		}

		private readonly string libraryId;
		private bool requested;

		// This face plus the same person's face in other frames of the file, which the server folded in.
		public IReadOnlyList<long> FaceIds => [Match.FaceId, .. Match.FoldedFaceIds ?? []];

		public int ExtraFrames => Match.FoldedFaceIds?.Count ?? 0;

		public Color TintColor { get; }

		public SolidColorBrush Tint { get; }

		public TeachReviewItemViewModel(string libraryId, PendingMatch match, Color tint)
		{
			this.libraryId = libraryId;
			Match = match;
			TintColor = tint;
			Tint = new SolidColorBrush(tint);
		}

		public void EnsureThumbnail()
		{
			if (requested)
				return;
			requested = true;
			_ = LoadAsync();
		}

		private async Task LoadAsync()
		{
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (engine.Api is null)
					return;
				var bitmap = await (await engine.Api.Persons.FaceThumbnailAsync(libraryId, Match.FaceId, 128)).ToBitmapAsync();
				if (bitmap is not null)
					await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() => Thumbnail = bitmap);
			}
			// Best-effort; the row keeps its placeholder.
			catch (Exception)
			{
				requested = false;
			}
		}
	}
}

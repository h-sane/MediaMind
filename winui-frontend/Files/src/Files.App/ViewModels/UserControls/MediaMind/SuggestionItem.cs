// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Services.MediaMind;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Files.App.ViewModels.UserControls.MediaMind
{
	public enum SuggestionKind
	{
		Duplicate,
		PendingMatch,
		Consistency,
	}

	// A single row in the Suggestions inbox (Block 5 Phase 3). The action buttons
	// in SuggestionsPane call back into SuggestionsViewModel with the ids carried
	// here (mirrors PeopleViewModel's plain-method-not-RelayCommand idiom).
	// ObservableObject only for the two lazily-loaded PendingMatch thumbnails —
	// every other field is set once at construction and never changes.
	public sealed partial class SuggestionItem(SuggestionKind kind, string libraryId, string header, string subText, long duplicateFlagId = 0, long personId = 0, long bindingId = 0, long fileId = 0) : ObservableObject
	{
		public SuggestionKind Kind { get; } = kind;

		public string LibraryId { get; } = libraryId;

		public string Header { get; } = header;

		public string SubText { get; } = subText;

		public long DuplicateFlagId { get; } = duplicateFlagId;

		public long PersonId { get; } = personId;

		public long BindingId { get; } = bindingId;

		public long FileId { get; } = fileId;

		// Consistency cards only (ADR-0010 ranking): true when this outlier's folder
		// contains a different named person's face, so it's likely misfiled rather
		// than just an unrecognized/ambiguous face.
		public bool HasLikelyPerson { get; private init; }

		// PendingMatch (grouped-by-person) only: every pending_matches row folded
		// into this one card, for the bulk confirm/reject on PendingReviewPage.
		public IReadOnlyList<long> PendingMatchIds { get; private init; } = [];

		// The "is this the same person?" comparison pair: one face already in the
		// person's cluster (null if that person has no sample face yet), one
		// representative face from the uncertain candidates.
		private BitmapImage? personThumbnail;
		public BitmapImage? PersonThumbnail
		{
			get => personThumbnail;
			private set => SetProperty(ref personThumbnail, value);
		}

		private BitmapImage? candidateThumbnail;
		public BitmapImage? CandidateThumbnail
		{
			get => candidateThumbnail;
			private set => SetProperty(ref candidateThumbnail, value);
		}

		public static SuggestionItem ForDuplicate(string libraryId, DuplicateFlag flag) =>
			new(
				SuggestionKind.Duplicate,
				libraryId,
				header: SystemIO.Path.GetFileName(flag.Path),
				subText: string.Format(Strings.MediaMind_DuplicateOf.GetLocalizedResource(), SystemIO.Path.GetFileName(flag.MatchPath)),
				duplicateFlagId: flag.Id);

		// One card per person with unresolved candidates — not one per pending_matches
		// row — so the reviewer sees "38 more photos or videos for Priya", not 38
		// separate rows. personSampleFaceId is that person's own reference face
		// (null if they don't have one yet); matches is every pending row for them.
		// The folder is named: the same person can be asked about in several folders.
		public static SuggestionItem ForPendingMatchGroup(string libraryId, string libraryName, string personName, long personId, long? personSampleFaceId, IReadOnlyList<PendingMatch> matches)
		{
			var item = new SuggestionItem(
				SuggestionKind.PendingMatch,
				libraryId,
				header: personName,
				subText: string.Format(Strings.MediaMind_PendingMatchCountIn.GetLocalizedResource(), matches.Count, libraryName),
				personId: personId)
			{
				PendingMatchIds = matches.Select(m => m.Id).ToList(),
			};

			var candidateFaceId = matches.OrderByDescending(m => m.Confidence).First().FaceId;
			_ = item.LoadThumbnailsAsync(candidateFaceId, personSampleFaceId);
			return item;
		}

		private async Task LoadThumbnailsAsync(long candidateFaceId, long? personSampleFaceId)
		{
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
					return;

				var candidateBytes = await engine.Api.Persons.FaceThumbnailAsync(LibraryId, candidateFaceId, 128);
				var candidateBitmap = await candidateBytes.ToBitmapAsync();
				if (candidateBitmap is not null)
					await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() => CandidateThumbnail = candidateBitmap);

				if (personSampleFaceId is long sampleFaceId)
				{
					var personBytes = await engine.Api.Persons.FaceThumbnailAsync(LibraryId, sampleFaceId, 128);
					var personBitmap = await personBytes.ToBitmapAsync();
					if (personBitmap is not null)
						await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() => PersonThumbnail = personBitmap);
				}
			}
			// Thumbnail loading is best-effort; the card just shows its fallback glyph.
			catch (Exception)
			{
			}
		}

		public static SuggestionItem ForConsistencyOutlier(string libraryId, long personId, FolderBinding binding, OutlierFile file) =>
			new(
				SuggestionKind.Consistency,
				libraryId,
				header: SystemIO.Path.GetFileName(file.Path),
				subText: string.IsNullOrEmpty(file.LikelyPersonName)
					? string.Format(Strings.MediaMind_OutlierInFolder.GetLocalizedResource(), binding.FolderRel)
					: string.Format(Strings.MediaMind_OutlierLooksLike.GetLocalizedResource(), file.LikelyPersonName),
				personId: personId,
				bindingId: binding.Id,
				fileId: file.FileId)
			{
				HasLikelyPerson = !string.IsNullOrEmpty(file.LikelyPersonName),
			};
	}
}

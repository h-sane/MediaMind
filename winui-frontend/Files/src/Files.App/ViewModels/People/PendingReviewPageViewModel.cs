// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Services.MediaMind;
using Files.App.ViewModels.UserControls.MediaMind;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Files.App.ViewModels.People
{
	// MediaMind: the main-content-frame bulk-review gallery for one person's
	// pending (below-AUTO_MATCH_THRESHOLD) candidate faces — the "is this the
	// same person?" call needs to see every uncertain photo, not decide blind
	// from one thumbnail on a Suggestions card. Navigated via "pending:{libraryId}:{personId}".
	public sealed partial class PendingReviewPageViewModel : ObservableObject
	{
		public string LibraryId { get; }

		public long PersonId { get; }

		private string personName = string.Empty;
		public string PersonName
		{
			get => personName;
			private set => SetProperty(ref personName, value);
		}

		public ObservableCollection<PendingMatchTileViewModel> Items { get; } = [];

		public PendingReviewPageViewModel(string libraryId, long personId)
		{
			LibraryId = libraryId;
			PersonId = personId;
			_ = LoadAsync();
		}

		private async Task LoadAsync()
		{
			var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
			if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
				return;

			try
			{
				var pending = await engine.Api.Pending.ListAsync(LibraryId);
				var mine = pending.Where(m => m.PersonId == PersonId).ToList();

				await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() =>
				{
					if (mine.Count > 0)
						PersonName = mine[0].PersonName;
					foreach (var match in mine)
						Items.Add(new PendingMatchTileViewModel(LibraryId, match));
				});
			}
			// Best-effort; an empty gallery reads as "nothing left to review", which is
			// harmless even if the real cause was a transient fetch failure.
			catch (Exception)
			{
			}
		}

		public void SelectAll(bool selected)
		{
			foreach (var item in Items)
				item.IsSelected = selected;
		}

		// Returns how many were recorded, so the page can report it. Confirmed
		// items join the person's cluster immediately (store/persons.py's
		// decide_pending); rejected ones just clear the suggestion.
		public async Task<int> CommitSelectedAsync(string decision)
		{
			var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
			if (engine.Api is null)
				return 0;

			var selected = Items.Where(i => i.IsSelected).ToList();
			if (selected.Count == 0)
				return 0;

			try
			{
				var decisions = selected.Select(i => new PendingDecisionItem(i.Match.Id, decision)).ToList();
				await engine.Api.Pending.DecideAsync(LibraryId, decisions);
			}
			// The batch didn't go through; leave the tiles as-is so the user can retry.
			catch (Exception)
			{
				return 0;
			}

			await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() =>
			{
				foreach (var item in selected)
					Items.Remove(item);
			});

			// Refresh both surfaces a decision affects: the person's tile in the People
			// view (bigger media count once confirmed) and the Suggestions panel (this
			// group shrinks or clears).
			_ = App.PeopleManager.RefreshAsync();
			_ = Ioc.Default.GetRequiredService<SuggestionsViewModel>().RefreshAsync();

			return selected.Count;
		}
	}

	// Loads its own face thumbnail lazily, same shape as PersonTileViewModel.
	public sealed partial class PendingMatchTileViewModel : ObservableObject
	{
		public PendingMatch Match { get; }

		public string FileName => SystemIO.Path.GetFileName(Match.Path);

		// Selected by default: "select them all, then uncheck the ones that aren't
		// this person" is the common case the user described, not the reverse.
		private bool isSelected = true;
		public bool IsSelected
		{
			get => isSelected;
			set => SetProperty(ref isSelected, value);
		}

		private BitmapImage? thumbnail;
		public BitmapImage? Thumbnail
		{
			get => thumbnail;
			private set => SetProperty(ref thumbnail, value);
		}

		public PendingMatchTileViewModel(string libraryId, PendingMatch match)
		{
			Match = match;
			_ = LoadThumbnailAsync(libraryId);
		}

		private async Task LoadThumbnailAsync(string libraryId)
		{
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
					return;

				var bytes = await engine.Api.Persons.FaceThumbnailAsync(libraryId, Match.FaceId, 192);
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
	}
}

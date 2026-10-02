// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Services.MediaMind;
using Microsoft.Extensions.Logging;
using System.Collections.Specialized;

namespace Files.App.ViewModels.UserControls.MediaMind
{
	// MediaMind: Suggestions inbox (Block 5 Phase 3, BLOCK5_UI_BLUEPRINT.md §4).
	// Deviates from the blueprint's suggested precedent ("modeled on the Info/
	// Preview pane") — InfoPaneViewModel's whole shape (SelectedItem, drive
	// details, tags) is built around the current file selection, which
	// Suggestions has nothing to do with (it's a library-wide inbox, not a
	// per-selection view). StatusCenterViewModel's shape — a button with a badge
	// that opens a flyout listing dismissable cards — is the closer functional
	// fit and is reused directly (same Items/HasAnyItem/badge pattern, same
	// button-in-NavigationToolbar-with-Flyout hosting).
	//
	// Phase 3 slice: duplicates (top, per ADR-0003) + uncertain face matches.
	// A confidently-clustered person (named or not) is never a "suggestion" —
	// that's a real Person, shown directly in the People view with inline
	// naming. This inbox is only for genuine "is this the same person?" calls:
	// a face that's somewhat similar to an existing person's cluster but not
	// confident enough to auto-attach (pending_matches, grouped by person).
	// Low-confidence video cards (also named in the blueprint's Phase 3) are
	// deferred — they need their own review-card shape (a scrubber preview)
	// beyond what this list-of-cards flyout does.
	public sealed partial class SuggestionsViewModel : ObservableObject
	{
		private readonly ILogger logger = Ioc.Default.GetRequiredService<ILogger<App>>();
		private readonly IMediaMindEngineService engine;

		public ObservableCollection<SuggestionItem> Items { get; } = [];

		// Docked ~40%-width panel in MainPage (a GridSplitter'd column, same
		// mechanism as the Preview Pane), not a Flyout — a real "same person?"
		// comparison needs room, not a 360px dropdown.
		private bool isPanelOpen;
		public bool IsPanelOpen
		{
			get => isPanelOpen;
			set
			{
				if (SetProperty(ref isPanelOpen, value) && value)
					_ = RefreshAsync();
			}
		}

		public bool HasAnyItem => Items.Count > 0;

		public int BadgeValue => Items.Count;

		public SuggestionsViewModel(IMediaMindEngineService engine)
		{
			this.engine = engine;
			Items.CollectionChanged += Items_CollectionChanged;
			engine.JobUpdated += Engine_JobUpdated;
		}

		private void Items_CollectionChanged(object? sender, NotifyCollectionChangedEventArgs e)
		{
			OnPropertyChanged(nameof(HasAnyItem));
			OnPropertyChanged(nameof(BadgeValue));
		}

		private void Engine_JobUpdated(object? _, JobSnapshot job)
		{
			if (job.Type is not ("dedupe" or "faces" or "organize-execute") || job.State is not ("succeeded" or "failed" or "cancelled"))
				return;

			_ = RefreshAsync();
		}

		public async Task RefreshAsync()
		{
			// Safe to call more than once; guarantees Api is populated even if this
			// runs before AppLifecycleHelper's own EnsureStartedAsync call finishes.
			if (!await engine.EnsureStartedAsync(CancellationToken.None))
				return;

			var api = engine.Api;
			if (api is null)
				return;

			List<SuggestionItem> built = [];
			try
			{
				var libraries = await api.Libraries.ListAsync();

				foreach (var library in libraries)
				{
					// Duplicates first (ADR-0003: top of Suggestions).
					try
					{
						var flags = await api.DuplicateFlags.ListAsync(library.Id);
						foreach (var flag in flags)
							built.Add(SuggestionItem.ForDuplicate(library.Id, flag));
					}
					catch (Exception ex)
					{
						logger.LogDebug(ex, "Skipping duplicate flags for library {LibraryId} in Suggestions.", library.Id);
					}

						// Grouped by person, not one card per pending_matches row: a reviewer
						// needs "38 more for Priya", not 38 separate identical-looking cards.
						// Tier-1 (confidently-clustered, possibly still unnamed) people no
						// longer come through here at all — they show directly in the People
						// view now (store/people_tree.py no longer hides unnamed persons).
						try
						{
							// Suggestions is for what the watched folders just picked up (2026-09-27): a
							// scan the user ran is answered in that folder's Who's who, never mixed in here.
							var pending = await api.Pending.ListArrivedAsync(library.Id);
							if (pending.Count > 0)
							{
								var sampleFaceByPerson = new Dictionary<long, long?>();
								try
								{
									var persons = await api.Persons.ListAsync(library.Id);
									foreach (var person in persons.Persons)
										sampleFaceByPerson[person.Id] = person.SampleFaceIds.Count > 0 ? person.SampleFaceIds[0] : null;
								}
								catch (Exception ex)
								{
									logger.LogDebug(ex, "Could not load person sample faces for Suggestions thumbnails in library {LibraryId}.", library.Id);
								}

								foreach (var group in pending.GroupBy(m => m.PersonId))
								{
									sampleFaceByPerson.TryGetValue(group.Key, out var sampleFaceId);
									built.Add(SuggestionItem.ForPendingMatchGroup(library.Id, library.Name, group.First().PersonName, group.Key, sampleFaceId, group.ToList()));
								}
							}
						}
						catch (Exception ex)
						{
							logger.LogDebug(ex, "Skipping pending matches for library {LibraryId} in Suggestions.", library.Id);
						}
				}
			}
			catch (Exception ex)
			{
				logger.LogWarning(ex, "Error loading Suggestions.");
				return;
			}

			await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() =>
			{
				// Consistency cards are on-demand (per-person check), not part of the
				// library-wide auto-refresh — carry them across the rebuild.
				var carried = Items.Where(i => i.Kind == SuggestionKind.Consistency).ToList();
				Items.Clear();
				foreach (var item in carried)
					Items.Add(item);
				foreach (var item in built)
					Items.Add(item);
			});
		}

		// On-demand consistency check (BLOCK5_UI_BLUEPRINT.md §3 feature 6, ADR-0010):
		// surfaces files in this person's respected folders that the face model thinks
		// don't belong (still-frozen outliers), ranked so ones that look like a named
		// other-person come first. Returns how many were found. Advisory only — the
		// engine never moves anything without the user acting on a card.
		public async Task<int> CheckPersonConsistencyAsync(long personId, string libraryId)
		{
			var api = engine.Api;
			if (api is null)
				return 0;

			List<SuggestionItem> found = [];
			try
			{
				var result = await api.Bindings.ListAsync(libraryId);
				foreach (var binding in result.Bindings.Where(b => b.PersonIds.Contains(personId)))
					foreach (var file in binding.Outliers.Where(o => !o.Accepted))
						found.Add(SuggestionItem.ForConsistencyOutlier(libraryId, personId, binding, file));
			}
			catch (Exception ex)
			{
				logger.LogWarning(ex, "Failed consistency check for person {PersonId}.", personId);
				return 0;
			}

			// Named-other-person outliers first (ADR-0010 ranking), then by filename.
			found = found
				.OrderByDescending(i => i.HasLikelyPerson)
				.ThenBy(i => i.Header, StringComparer.OrdinalIgnoreCase)
				.ToList();

			await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() =>
			{
				// Replace any prior consistency cards for this person (re-running the
				// check shouldn't stack duplicates).
				foreach (var stale in Items.Where(i => i.Kind == SuggestionKind.Consistency && i.PersonId == personId).ToList())
					Items.Remove(stale);
				foreach (var item in found)
					Items.Add(item);
			});

			if (found.Count > 0)
				IsPanelOpen = true;

			return found.Count;
		}

		// "Move out" on a consistency card: the model was right, this file is misfiled.
		// Approve it into the binding's accepted-outlier set so the next organize sweep
		// routes it out. Re-reads the binding first so concurrent approvals on the same
		// folder don't clobber each other.
		public async Task MoveOutlierAsync(SuggestionItem item)
		{
			var api = engine.Api;
			if (api is null)
				return;

			try
			{
				var result = await api.Bindings.ListAsync(item.LibraryId);
				var binding = result.Bindings.FirstOrDefault(b => b.Id == item.BindingId);
				if (binding is null)
					return;

				var accepted = new HashSet<long>(binding.AcceptedOutlierFileIds) { item.FileId };
				await api.Bindings.SetOutliersAsync(item.LibraryId, item.BindingId, accepted.ToList());
			}
			catch (Exception ex)
			{
				logger.LogWarning(ex, "Failed to approve outlier {FileId} on binding {BindingId}.", item.FileId, item.BindingId);
				return;
			}

			await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() => Items.Remove(item));
		}

		// "Keep here": the model was wrong — this file belongs in the folder. It stays
		// frozen (the default), so there's no backend call; just clear the advisory card.
		public void KeepOutlier(SuggestionItem item) => Items.Remove(item);

		public async Task DismissDuplicateAsync(SuggestionItem item)
		{
			var api = engine.Api;
			if (api is null)
				return;

			try
			{
				await api.DuplicateFlags.DismissAsync(item.LibraryId, item.DuplicateFlagId);
			}
			catch (Exception ex)
			{
				logger.LogWarning(ex, "Failed to dismiss duplicate flag {FlagId}.", item.DuplicateFlagId);
				return;
			}

			await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() => Items.Remove(item));
		}

	}
}

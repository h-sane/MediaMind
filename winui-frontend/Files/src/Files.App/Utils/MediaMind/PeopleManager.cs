// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Data.Items.MediaMind;
using Files.App.Services.MediaMind;
using Microsoft.Extensions.Logging;
using System.Collections.Specialized;

namespace Files.App.Utils.MediaMind
{
	// MediaMind: sources the People sidebar section (ADR-0007/0008) — one root
	// PeopleGroupItem per registered library that has a people-tree. Modeled on
	// FileTagsManager, but data comes from the engine's /people-tree instead of a
	// local settings list, and refreshes are driven by IMediaMindEngineService's
	// JobUpdated (a completed "faces" scan), not polling.
	public sealed class PeopleManager
	{
		private readonly ILogger logger = Ioc.Default.GetRequiredService<ILogger<App>>();
		private readonly IMediaMindEngineService engine;

		public EventHandler<NotifyCollectionChangedEventArgs>? DataChanged;

		private readonly List<PeopleGroupItem> groups = [];
		public IReadOnlyList<PeopleGroupItem> Groups
		{
			get
			{
				lock (groups)
				{
					return groups.ToList().AsReadOnly();
				}
			}
		}

		public PeopleManager(IMediaMindEngineService engine)
		{
			this.engine = engine;
			engine.JobUpdated += Engine_JobUpdated;
		}

		private void Engine_JobUpdated(object? _, JobSnapshot job)
		{
			if (job.Type != "faces" || job.State is not ("succeeded" or "failed" or "cancelled"))
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

			List<PeopleGroupItem> built;
			try
			{
				var libraries = await api.Libraries.ListAsync();
				built = new List<PeopleGroupItem>(libraries.Count);

				foreach (var library in libraries)
				{
					try
					{
						var tree = await api.Persons.TreeAsync(library.Id);
						built.Add(new PeopleGroupItem(library.Id, tree.Root, displayNameOverride: library.Name));
					}
					// A library with no scan yet (or a transient fetch error) must not blank
					// the whole People section — skip it, keep the others (per-file try/except
					// discipline applied to per-library fetches here).
					catch (Exception ex)
					{
						logger.LogDebug(ex, "Skipping library {LibraryId} in People section — no people-tree available.", library.Id);
					}
				}
			}
			catch (Exception ex)
			{
				logger.LogWarning(ex, "Error loading People section.");
				return;
			}

			lock (groups)
			{
				groups.Clear();
				groups.AddRange(built);
			}

			DataChanged?.Invoke(SectionType.People, new NotifyCollectionChangedEventArgs(NotifyCollectionChangedAction.Reset));
		}

		// Looks up an already-loaded Group by libraryId+path (the "group:" virtual
		// path's identity) — the whole tree is in memory from one TreeAsync call, so
		// PeopleGroupPage doesn't need its own fetch, just a walk over Groups.
		public PeopleGroupItem? FindGroup(string libraryId, string groupPath)
		{
			foreach (var root in Groups)
			{
				if (root.LibraryId != libraryId)
					continue;

				var match = FindGroupRecursive(root, groupPath);
				if (match is not null)
					return match;
			}

			return null;
		}

		private static PeopleGroupItem? FindGroupRecursive(PeopleGroupItem candidate, string groupPath)
		{
			if (candidate.Group.Path == groupPath)
				return candidate;

			foreach (var subgroup in candidate.Subgroups)
			{
				var match = FindGroupRecursive(subgroup, groupPath);
				if (match is not null)
					return match;
			}

			return null;
		}
	}
}

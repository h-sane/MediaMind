// Copyright (c) Files Community
// Licensed under the MIT License.

namespace Files.App.Utils.MediaMind
{
	// MediaMind: the scanned library that holds a folder, and where the folder sits inside it.
	// Shared by the toolbar commands that open a page for "this folder" (Who's who, Duplicates).
	internal static class MediaMindLibraryLookup
	{
		// The library holding the folder; failing that, one inside it (the user is standing in a
		// parent of a scanned folder). Empty strings when nothing here is scanned or the engine is down.
		public static async Task<(string LibraryId, string Under)> FindAsync(IMediaMindEngineService engine, string folderPath)
		{
			try
			{
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
					return (string.Empty, string.Empty);
				var dir = MediaMindPaths.Canonical(folderPath);
				var libraries = await engine.Api.Libraries.ListAsync();
				var holder = libraries
					.Where(l => MediaMindPaths.IsUnder(dir, MediaMindPaths.Canonical(l.Path)))
					.OrderByDescending(l => l.Path.Length)
					.FirstOrDefault()
					?? libraries
						.Where(l => MediaMindPaths.IsUnder(MediaMindPaths.Canonical(l.Path), dir))
						.OrderBy(l => l.Path.Length)
						.FirstOrDefault();
				if (holder is null)
					return (string.Empty, string.Empty);
				var root = MediaMindPaths.Canonical(holder.Path);
				var under = dir.Length > root.Length ? dir[root.Length..].Trim('\\').Replace('\\', '/') : string.Empty;
				return (holder.Id, under);
			}
			// An unreachable engine still opens the page, which then explains what to do.
			catch (Exception)
			{
				return (string.Empty, string.Empty);
			}
		}
	}
}

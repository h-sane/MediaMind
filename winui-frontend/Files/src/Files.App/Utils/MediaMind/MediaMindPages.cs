// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Views.People;
using System.Collections.Concurrent;

namespace Files.App.Utils.MediaMind
{
	// MediaMind's own pages are opened by an address, not a folder: "teach:{library}:{under}"
	// (Who's who), "duplicates:{library}:{group}:{under}", "group:…" and "People". The shell
	// treated those as folders wherever it only had the address: a restored tab opened
	// "teach:…" as a drive ("Drive unplugged"), the tab showed the address itself, and Home did
	// nothing because these pages share the Home working directory (2026-09-27).
	internal static class MediaMindPages
	{
		private static readonly ConcurrentDictionary<string, string> LibraryNames = new();
		private static readonly ConcurrentDictionary<string, string> LibraryPaths = new();

		public static bool IsTeach(string? path)
			=> path?.StartsWith("teach:", StringComparison.Ordinal) == true;

		public static bool IsDuplicates(string? path)
			=> path?.StartsWith("duplicates:", StringComparison.Ordinal) == true;

		// The address of the page the tab shows now (teach:…, a folder path, Home).
		public static string? CurrentAddress(IShellPage? shell)
			=> (shell as Views.Shells.BaseShellPage)?.TabBarItemParameter?.NavigationParameter as string;

		// teach:{id}:{under} | teach::{folder} | duplicates:{id}:{group}:{under} | duplicates:::{folder}
		private static (string LibraryId, string Under, string Folder) Parse(string path)
		{
			var teach = IsTeach(path);
			var parts = path.Split(':', teach ? 3 : 4);
			var libraryId = parts.Length > 1 ? parts[1] : string.Empty;
			var last = parts.Length > 0 ? parts[^1] : string.Empty;
			return libraryId.Length > 0 ? (libraryId, last, string.Empty) : (string.Empty, string.Empty, last);
		}

		// The folder the page is about, on disk: where Up, and the page's button pressed again, go back to.
		public static async Task<string?> BaseFolderAsync(string path)
		{
			var (libraryId, under, folder) = Parse(path);
			if (libraryId.Length == 0)
				return folder.Length > 0 ? folder : null;
			await LibraryNameAsync(libraryId);
			if (!LibraryPaths.TryGetValue(libraryId, out var root))
				return null;
			return under.Length == 0 ? root : SystemIO.Path.Combine(root, under.Replace('/', '\\'));
		}

		// The same folder in the other page: Who's who <-> Duplicates.
		public static string SwitchAddress(string path, bool toTeach)
		{
			var (libraryId, under, folder) = Parse(path);
			if (toTeach)
				return libraryId.Length > 0 ? $"teach:{libraryId}:{under}" : $"teach::{folder}";
			return libraryId.Length > 0 ? $"duplicates:{libraryId}::{under}" : $"duplicates:::{folder}";
		}

		public static bool IsPage(string? path)
			=> PageTypeFor(path) is not null;

		public static Type? PageTypeFor(string? path)
		{
			if (path is null)
				return null;
			if (path.StartsWith("teach:", StringComparison.Ordinal))
				return typeof(TeachPage);
			if (path.StartsWith("duplicates:", StringComparison.Ordinal))
				return typeof(DuplicatesPage);
			if (path.StartsWith("group:", StringComparison.Ordinal))
				return typeof(PeopleGroupPage);
			if (path == "People")
				return typeof(PeopleHomePage);
			return null;
		}

		// The tab's name, as the page's own title says it: "Who's who in Holiday 2024".
		public static async Task<string?> TitleForAsync(string path)
		{
			if (path == "People")
				return Strings.People.GetLocalizedResource();
			var isTeach = path.StartsWith("teach:", StringComparison.Ordinal);
			if (!isTeach && !path.StartsWith("duplicates:", StringComparison.Ordinal))
				return null;

			// teach:{id}:{under} | teach::{folder} | duplicates:{id}:{group}:{under} | duplicates:::{folder}
			var parts = path.Split(':', isTeach ? 3 : 4);
			var libraryId = parts.Length > 1 ? parts[1] : string.Empty;
			var name = libraryId.Length > 0
				? await LibraryNameAsync(libraryId)
				: SystemIO.Path.GetFileName((parts.Length > 0 ? parts[^1] : string.Empty).TrimEnd('\\', '/'));
			var key = isTeach ? Strings.MediaMind_TeachTitleFor : Strings.MediaMind_DupTitleFor;
			return string.IsNullOrEmpty(name)
				? (isTeach ? Strings.MediaMind_TeachTitle : Strings.MediaMind_DupTitle).GetLocalizedResource()
				: string.Format(key.GetLocalizedResource(), name);
		}

		public static string GlyphFor(string path)
			=> path.StartsWith("duplicates:", StringComparison.Ordinal) ? "" : "";

		private static async Task<string?> LibraryNameAsync(string libraryId)
		{
			if (LibraryNames.TryGetValue(libraryId, out var name) && LibraryPaths.ContainsKey(libraryId))
				return name;
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (await engine.EnsureStartedAsync(CancellationToken.None) && engine.Api is not null)
					foreach (var library in await engine.Api.Libraries.ListAsync())
					{
						LibraryNames[library.Id] = library.Name;
						LibraryPaths[library.Id] = library.Path;
					}
			}
			// The engine is down: the tab says "Who's who" without the folder's name.
			catch (Exception)
			{
			}
			return LibraryNames.TryGetValue(libraryId, out name) ? name : null;
		}
	}
}

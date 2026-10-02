// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Services.MediaMind;
using Microsoft.Extensions.Logging;

namespace Files.App.ViewModels.Settings
{
	// MediaMind Phase 5 (BLOCK5_UI_BLUEPRINT.md §4, ADR-0009): the watched-root set.
	// The engine already runs the always-on watcher over registered libraries; this
	// page is the user-visible list of those roots (add/stop) plus one-tap add of
	// auto-detected inbox folders (/fs/discovery/*). The bootstrap-from-folders
	// onboarding wizard is launched from here (BootstrapWizardDialog).
	public sealed partial class WatchedFoldersViewModel : ObservableObject
	{
		private readonly IMediaMindEngineService engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
		private readonly ILogger logger = Ioc.Default.GetRequiredService<ILogger<App>>();

		public ObservableCollection<WatchedFolderItem> WatchedFolders { get; } = [];

		public ObservableCollection<DiscoverySuggestionItem> Suggestions { get; } = [];

		private string watchingSummary = string.Empty;
		public string WatchingSummary
		{
			get => watchingSummary;
			private set => SetProperty(ref watchingSummary, value);
		}

		private bool hasSuggestions;
		public bool HasSuggestions
		{
			get => hasSuggestions;
			private set => SetProperty(ref hasSuggestions, value);
		}

		private bool hasWatchedFolders;
		public bool HasWatchedFolders
		{
			get => hasWatchedFolders;
			private set => SetProperty(ref hasWatchedFolders, value);
		}

		public WatchedFoldersViewModel()
		{
			_ = LoadAsync();
		}

		public async Task LoadAsync()
		{
			var api = await GetApiAsync();
			if (api is null)
				return;

			try
			{
				var libraries = await api.Libraries.ListAsync();
				var autoFile = (await api.Teach.AutoFileLibrariesAsync()).LibraryIds.ToHashSet();
				WatchedFolders.Clear();
				foreach (var library in libraries)
					WatchedFolders.Add(new WatchedFolderItem(library.Id, library.Name, library.Path, autoFile.Contains(library.Id)));
			}
			catch (Exception ex)
			{
				logger.LogWarning(ex, "Failed to list watched folders.");
			}

			try
			{
				var suggestions = await api.Fs.Discovery.SuggestionsAsync();
				Suggestions.Clear();
				foreach (var suggestion in suggestions)
					Suggestions.Add(new DiscoverySuggestionItem(suggestion.Folder, suggestion.MediaCount));
			}
			catch (Exception ex)
			{
				logger.LogWarning(ex, "Failed to load folder discovery suggestions.");
			}

			UpdateDerived();
		}

		public async Task AddFolderAsync()
		{
			var api = await GetApiAsync();
			if (api is null)
				return;

			if (!Utils.MediaMind.FolderPicker.Pick(out var folderPath))
				return;

			try
			{
				var library = await api.Libraries.AddAsync(Utils.MediaMind.MediaMindPaths.Canonical(folderPath));
				if (!WatchedFolders.Any(f => f.LibraryId == library.Id))
					WatchedFolders.Add(new WatchedFolderItem(library.Id, library.Name, library.Path));
				UpdateDerived();
			}
			catch (Exception ex)
			{
				logger.LogWarning(ex, "Failed to add watched folder {FolderPath}.", folderPath);
			}
		}

		public async Task StopWatchingAsync(WatchedFolderItem item)
		{
			var api = await GetApiAsync();
			if (api is null)
				return;

			try
			{
				await api.Libraries.RemoveAsync(item.LibraryId);
				WatchedFolders.Remove(item);
				UpdateDerived();
				_ = App.PeopleManager.RefreshAsync();
			}
			catch (Exception ex)
			{
				logger.LogWarning(ex, "Failed to stop watching folder {LibraryId}.", item.LibraryId);
			}
		}

		public async Task WatchSuggestionAsync(DiscoverySuggestionItem item)
		{
			var api = await GetApiAsync();
			if (api is null)
				return;

			try
			{
				var library = await api.Fs.Discovery.RegisterAsync(item.Folder);
				Suggestions.Remove(item);
				if (!WatchedFolders.Any(f => f.LibraryId == library.Id))
					WatchedFolders.Add(new WatchedFolderItem(library.Id, library.Name, library.Path));
				UpdateDerived();
			}
			catch (Exception ex)
			{
				logger.LogWarning(ex, "Failed to watch suggested folder {Folder}.", item.Folder);
			}
		}

		public async Task DismissSuggestionAsync(DiscoverySuggestionItem item)
		{
			var api = await GetApiAsync();
			if (api is null)
				return;

			try
			{
				await api.Fs.Discovery.DismissAsync(item.Folder);
				Suggestions.Remove(item);
				UpdateDerived();
			}
			catch (Exception ex)
			{
				logger.LogWarning(ex, "Failed to dismiss suggested folder {Folder}.", item.Folder);
			}
		}

		private void UpdateDerived()
		{
			HasWatchedFolders = WatchedFolders.Count > 0;
			HasSuggestions = Suggestions.Count > 0;
			WatchingSummary = WatchedFolders.Count == 1
				? Strings.MediaMind_WatchingOne.GetLocalizedResource()
				: string.Format(Strings.MediaMind_WatchingMany.GetLocalizedResource(), WatchedFolders.Count);
		}

		private async Task<MediaMindApiClient?> GetApiAsync()
			=> await engine.EnsureStartedAsync(CancellationToken.None) ? engine.Api : null;
	}

	public sealed partial class WatchedFolderItem(string libraryId, string name, string path, bool autoFile = false) : ObservableObject
	{
		public string LibraryId { get; } = libraryId;

		public string Name { get; } = name;

		public string Path { get; } = path;

		// New pictures of named people move into their folders by themselves (the engine's
		// placement rules; group pictures wait in Who's who). Flips back if the engine refuses.
		private bool autoFile = autoFile;
		public bool AutoFile
		{
			get => autoFile;
			set
			{
				if (SetProperty(ref autoFile, value))
					_ = SaveAutoFileAsync(value);
			}
		}

		private async Task SaveAutoFileAsync(bool on)
		{
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (engine.Api is null)
					throw new InvalidOperationException();
				await engine.Api.Teach.SetAutoFileAsync(LibraryId, on);
			}
			catch (Exception)
			{
				autoFile = !on;
				MainWindow.Instance.DispatcherQueue.TryEnqueue(() => OnPropertyChanged(nameof(AutoFile)));
			}
		}
	}

	public sealed partial class DiscoverySuggestionItem(string folder, int mediaCount) : ObservableObject
	{
		public string Folder { get; } = folder;

		public string LeafName { get; } = System.IO.Path.GetFileName(folder.TrimEnd('\\', '/')) is { Length: > 0 } leaf ? leaf : folder;

		public string MediaCountText { get; } = string.Format(Strings.MediaMind_MediaFilesCount.GetLocalizedResource(), mediaCount);
	}
}

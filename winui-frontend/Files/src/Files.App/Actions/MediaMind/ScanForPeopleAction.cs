// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Utils.StatusCenter;
using Files.App.ViewModels.UserControls;
using Microsoft.Extensions.Logging;

namespace Files.App.Actions
{
	// MediaMind: the only way a folder becomes a registered MediaMind library from
	// the WinUI shell (Phase 1 only proved Libraries.AddAsync/Scans.StartAsync via a
	// temporary trigger, since removed). Progress is already solved — Phase 1's
	// MediaMindJobStatusBridge renders the started scan in StatusCenter automatically.
	[GeneratedRichCommand]
	sealed partial class ScanForPeopleAction : ObservableObject, IAction
	{
		private readonly IContentPageContext _context;
		private readonly IMediaMindEngineService _engine;
		private readonly StatusCenterViewModel _statusCenter = Ioc.Default.GetRequiredService<StatusCenterViewModel>();
		private readonly ILogger _logger = Ioc.Default.GetRequiredService<ILogger<App>>();

		public string Label
			=> Strings.MediaMind_ScanForPeople.GetLocalizedResource();

		public string Description
			=> Strings.MediaMind_ScanForPeopleDescription.GetLocalizedResource();

		public bool IsExecutable
			=> _context.Folder is not null;

		public ScanForPeopleAction()
		{
			_context = Ioc.Default.GetRequiredService<IContentPageContext>();
			_engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();

			_context.PropertyChanged += Context_PropertyChanged;
		}

		public async Task ExecuteAsync(object? parameter = null)
		{
			// Scan the selected subfolders when any folders are selected; otherwise the
			// whole current folder. Selecting three of ten subfolders scans exactly those
			// three. Selected files (non-folders) are ignored — a selection with no folders
			// falls back to scanning the current folder.
			var paths = new List<string>();
			var names = new List<string>();
			foreach (var item in _context.SelectedItems)
			{
				if (item.IsFolder && !string.IsNullOrWhiteSpace(item.ItemPath))
				{
					paths.Add(Utils.MediaMind.MediaMindPaths.Canonical(item.ItemPath));
					names.Add(string.IsNullOrEmpty(item.Name) ? item.ItemPath : item.Name);
				}
			}

			if (paths.Count == 0)
			{
				var folder = _context.Folder;
				if (folder is null || string.IsNullOrWhiteSpace(folder.ItemPath))
					return;
				paths.Add(Utils.MediaMind.MediaMindPaths.Canonical(folder.ItemPath));
				names.Add(string.IsNullOrEmpty(folder.Name) ? folder.ItemPath : folder.Name);
			}

			if (!await _engine.EnsureStartedAsync(CancellationToken.None) || _engine.Api is null)
			{
				// Engine unavailable: one visible error card so the click is never silent.
				ShowFailedCard(names[0]);
				return;
			}

			for (var i = 0; i < paths.Count; i++)
				await ScanOneAsync(paths[i], names[i]);
		}

		private async Task ScanOneAsync(string folderPath, string folderName)
		{
			// Cause & effect: show an immediate "preparing" card so the click is never silent.
			// On success the JobStatusBridge takes over with live scan progress; on failure
			// this becomes a visible error card instead of a swallowed log line.
			var preparing = _statusCenter.AddItem(
				string.Empty, string.Empty,
				ReturnResult.InProgress, FileOperationType.MediaMindScan,
				source: null, destination: null, canProvideProgress: false);
			preparing.Header = string.Format(Strings.MediaMind_ScanPreparing.GetLocalizedResource(), folderName);

			try
			{
				// Registration probes the folder (backend caps that at 10s). Bound the whole
				// call so a wedged mount surfaces a visible error in ~25s instead of the .NET
				// HttpClient default of 100s of dead UI. See BLOCK5_UX_CORRECTION_PLAN Phase D.
				using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(25));
				var library = await _engine.Api!.Libraries.AddAsync(folderPath, cts.Token);
				// Duplicates are found first in the same job: one wait, and copies show up for review.
				await _engine.Api.Scans.StartAsync(library.Id, "faces", ct: cts.Token, withDuplicates: true);

				_statusCenter.RemoveItem(preparing);
			}
			catch (Exception ex)
			{
				_logger.LogWarning(ex, "Scan for People failed to start for {FolderPath}", folderPath);

				_statusCenter.RemoveItem(preparing);
				ShowFailedCard(folderName);
			}
		}

		private void ShowFailedCard(string folderName)
		{
			var failed = _statusCenter.AddItem(
				string.Empty, string.Empty,
				ReturnResult.Failed, FileOperationType.MediaMindScan,
				source: null, destination: null, canProvideProgress: false);
			failed.Header = string.Format(Strings.MediaMind_ScanFailed.GetLocalizedResource(), folderName);
		}

		private void Context_PropertyChanged(object? sender, PropertyChangedEventArgs e)
		{
			if (e.PropertyName == nameof(IContentPageContext.Folder))
				OnPropertyChanged(nameof(IsExecutable));
		}
	}
}

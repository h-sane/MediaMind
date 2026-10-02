// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Views.People;

namespace Files.App.Actions
{
	// MediaMind: opens "Duplicates" (DuplicatesPage) for the scanned library that holds the
	// current folder, limited to sets with a copy in that folder. Sits next to Who's who: every
	// Scan for People finds duplicates first, and this is where they are reviewed.
	[GeneratedRichCommand]
	sealed partial class FindDuplicatesAction : ObservableObject, IToggleAction
	{
		private readonly IContentPageContext _context;
		private readonly IMediaMindEngineService _engine;

		public string Label
			=> Strings.MediaMind_DupCommand.GetLocalizedResource();

		public string Description
			=> Strings.MediaMind_DupCommandDescription.GetLocalizedResource();

		// On its page the button is lit; pressing it again goes back to the folder.
		public bool IsOn
			=> Utils.MediaMind.MediaMindPages.IsDuplicates(Utils.MediaMind.MediaMindPages.CurrentAddress(_context.ShellPage));

		// Also on Who's who and Duplicates, which have no folder view of their own.
		public bool IsExecutable
			=> _context.Folder is not null || Utils.MediaMind.MediaMindPages.IsTeach(Utils.MediaMind.MediaMindPages.CurrentAddress(_context.ShellPage))
				|| Utils.MediaMind.MediaMindPages.IsDuplicates(Utils.MediaMind.MediaMindPages.CurrentAddress(_context.ShellPage));

		public FindDuplicatesAction()
		{
			_context = Ioc.Default.GetRequiredService<IContentPageContext>();
			_engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();

			_context.PropertyChanged += Context_PropertyChanged;
		}

		public async Task ExecuteAsync(object? parameter = null)
		{
			var current = Utils.MediaMind.MediaMindPages.CurrentAddress(_context.ShellPage);
			if (Utils.MediaMind.MediaMindPages.IsDuplicates(current) && _context.ShellPage is { } here)
			{
				if (await Utils.MediaMind.MediaMindPages.BaseFolderAsync(current!) is { } baseFolder)
					here.NavigateToPath(baseFolder, null);
				else
					here.NavigateHome();
				return;
			}
			if (Utils.MediaMind.MediaMindPages.IsTeach(current) && _context.ShellPage is { } there)
			{
				there.NavigateToPath(Utils.MediaMind.MediaMindPages.SwitchAddress(current!, false), typeof(DuplicatesPage));
				return;
			}

			var folderPath = _context.Folder?.ItemPath;
			var shell = _context.ShellPage;
			if (string.IsNullOrWhiteSpace(folderPath) || shell is null)
				return;

			var (libraryId, under) = await Utils.MediaMind.MediaMindLibraryLookup.FindAsync(_engine, folderPath);

			// "duplicates:{libraryId}::{under}" — or "duplicates:::{folderPath}" when nothing here is scanned yet.
			var navPath = libraryId.Length > 0 ? $"duplicates:{libraryId}::{under}" : $"duplicates:::{folderPath}";
			shell.NavigateToPath(navPath, typeof(DuplicatesPage));
		}

		private void Context_PropertyChanged(object? sender, PropertyChangedEventArgs e)
		{
			// Any change of page or folder: both can change.
			OnPropertyChanged(nameof(IsExecutable));
			OnPropertyChanged(nameof(IsOn));
		}
	}
}

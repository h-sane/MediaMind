// Copyright (c) Files Community
// Licensed under the MIT License.

namespace Files.App.Actions
{
	// MediaMind is media-first: folder views show only images/videos by default. This toggle
	// reveals every file (plain-explorer behaviour) and back. IsOn == "showing all files".
	[GeneratedRichCommand]
	internal sealed partial class ToggleShowAllFilesAction : ObservableObject, IToggleAction
	{
		private readonly IFoldersSettingsService settings;

		public string Label
			=> "Show all files";

		public string Description
			=> "Show all files, not just images and videos.";

		public ActionCategory Category
			=> ActionCategory.Show;

		public HotKey HotKey
			=> new(Keys.M, KeyModifiers.Ctrl);

		public bool IsOn
			=> settings.ShowAllFiles;

		public ToggleShowAllFilesAction()
		{
			settings = Ioc.Default.GetRequiredService<IFoldersSettingsService>();

			settings.PropertyChanged += Settings_PropertyChanged;
		}

		public Task ExecuteAsync(object? parameter = null)
		{
			settings.ShowAllFiles = !settings.ShowAllFiles;

			return Task.CompletedTask;
		}

		private void Settings_PropertyChanged(object? sender, PropertyChangedEventArgs e)
		{
			if (e.PropertyName is nameof(IFoldersSettingsService.ShowAllFiles))
				OnPropertyChanged(nameof(IsOn));
		}
	}
}

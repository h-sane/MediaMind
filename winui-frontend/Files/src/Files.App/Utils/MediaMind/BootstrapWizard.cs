// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Dialogs;

namespace Files.App.Utils.MediaMind
{
	// MediaMind Phase 5: launches the bootstrap-from-folders wizard. Kept as a static
	// helper alongside the other Person* MediaMind helpers so callers (WatchedFoldersPage)
	// don't duplicate the ContentDialog XamlRoot plumbing.
	internal static class BootstrapWizard
	{
		public static Task RunAsync()
		{
			var dialog = new BootstrapWizardDialog
			{
				XamlRoot = MainWindow.Instance.Content.XamlRoot,
			};
			return dialog.ShowAsync().AsTask();
		}
	}
}

// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Utils.MediaMind;
using Files.App.ViewModels.Settings;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Files.App.Views.Settings
{
	// MediaMind Phase 5: watched-root management + bootstrap wizard entry.
	// Click+Tag handlers mirror the PeoplePage settings idiom (Tag carries the row's
	// item VM); each just forwards to a WatchedFoldersViewModel method.
	public sealed partial class WatchedFoldersPage : Page
	{
		public WatchedFoldersPage()
		{
			InitializeComponent();
		}

		private async void SetUpFromFolders_Click(object sender, RoutedEventArgs e)
		{
			await BootstrapWizard.RunAsync();
			await ViewModel.LoadAsync();
		}

		private async void AddFolder_Click(object sender, RoutedEventArgs e)
			=> await ViewModel.AddFolderAsync();

		private async void StopWatching_Click(object sender, RoutedEventArgs e)
		{
			if ((sender as FrameworkElement)?.Tag is WatchedFolderItem item)
				await ViewModel.StopWatchingAsync(item);
		}

		private async void WatchSuggestion_Click(object sender, RoutedEventArgs e)
		{
			if ((sender as FrameworkElement)?.Tag is DiscoverySuggestionItem item)
				await ViewModel.WatchSuggestionAsync(item);
		}

		private async void DismissSuggestion_Click(object sender, RoutedEventArgs e)
		{
			if ((sender as FrameworkElement)?.Tag is DiscoverySuggestionItem item)
				await ViewModel.DismissSuggestionAsync(item);
		}
	}
}

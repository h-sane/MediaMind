// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.ViewModels.UserControls.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Windows.System;

namespace Files.App.UserControls.MediaMind
{
	// MediaMind: the "Not scanned" pane under a folder view (see UnprocessedPaneViewModel).
	public sealed partial class UnprocessedPane : UserControl
	{
		public UnprocessedPaneViewModel ViewModel { get; } = new();

		public UnprocessedPane()
		{
			InitializeComponent();
		}

		// Called by the shell whenever its working directory changes.
		public void ShowFor(string? directory)
			=> _ = ViewModel.ShowForAsync(directory);

		private void Header_Click(object sender, RoutedEventArgs e)
			=> ViewModel.IsExpanded = !ViewModel.IsExpanded;

		private static UnprocessedItemViewModel? ItemOf(object sender)
			=> (sender as FrameworkElement)?.Tag as UnprocessedItemViewModel;

		private async void Open_Click(object sender, RoutedEventArgs e)
		{
			if (ItemOf(sender) is { } item)
				await OpenAsync(item);
		}

		private async void Item_DoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
		{
			if (ItemOf(sender) is { } item && e.OriginalSource is not Button)
				await OpenAsync(item);
		}

		private static async Task OpenAsync(UnprocessedItemViewModel item)
		{
			try
			{
				var file = await Windows.Storage.StorageFile.GetFileFromPathAsync(item.AbsPath);
				await Launcher.LaunchFileAsync(file);
			}
			// The file may be exactly why it was not scanned (unreadable right now); nothing to do here.
			catch (Exception)
			{
			}
		}

		private async void Tag_Click(object sender, RoutedEventArgs e)
		{
			if (ItemOf(sender) is not { } item)
				return;

			var chooser = new PersonChooser();
			var dialog = new ContentDialog
			{
				XamlRoot = XamlRoot,
				Title = "MediaMind_UnprocessedTagTitle".GetLocalizedResource(),
				Content = chooser,
				PrimaryButtonText = "Confirm".GetLocalizedResource(),
				CloseButtonText = "Cancel".GetLocalizedResource(),
				DefaultButton = ContentDialogButton.Primary,
				IsPrimaryButtonEnabled = false,
			};
			chooser.SelectionChanged += () => dialog.IsPrimaryButtonEnabled = chooser.Selected is not null;
			chooser.SetPeople(await ViewModel.LoadPersonChoicesAsync());

			if (await dialog.ShowAsync() == ContentDialogResult.Primary && chooser.Selected is { } chosen)
				await ViewModel.TagAsync(item, chosen.Person.Id);
		}

		private async void Untag_Click(object sender, RoutedEventArgs e)
		{
			if (ItemOf(sender) is { } item)
				await ViewModel.UntagAsync(item);
		}
	}
}

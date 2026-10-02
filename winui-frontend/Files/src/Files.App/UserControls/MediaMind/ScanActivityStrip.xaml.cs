// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.ViewModels.UserControls.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Files.App.UserControls.MediaMind
{
	// MediaMind: the live "what is the engine doing" strip (see ScanActivityViewModel).
	public sealed partial class ScanActivityStrip : UserControl
	{
		public ScanActivityViewModel ViewModel { get; } = Ioc.Default.GetRequiredService<ScanActivityViewModel>();

		public ScanActivityStrip()
		{
			InitializeComponent();
		}

		private void ReviewDuplicates_Click(object sender, RoutedEventArgs e)
		{
			if ((sender as FrameworkElement)?.Tag is not ScanJobRowViewModel row)
				return;
			Ioc.Default.GetRequiredService<IContentPageContext>().ShellPage?
				.NavigateToPath($"duplicates:{row.LibraryId}::", typeof(Views.People.DuplicatesPage));
			ViewModel.Dismiss(row);
		}

		private async void Cancel_Click(object sender, RoutedEventArgs e)
		{
			if ((sender as FrameworkElement)?.Tag is not ScanJobRowViewModel row)
				return;
			var dialog = new ContentDialog
			{
				XamlRoot = XamlRoot,
				Title = (row.IsMove ? "MediaMind_JobCancelMoveTitle" : "MediaMind_JobCancelScanTitle").GetLocalizedResource(),
				Content = new TextBlock
				{
					Text = (row.IsMove ? "MediaMind_JobCancelMoveText" : "MediaMind_JobCancelScanText").GetLocalizedResource(),
					TextWrapping = TextWrapping.Wrap,
					MaxWidth = 440,
				},
				PrimaryButtonText = "MediaMind_JobCancelConfirm".GetLocalizedResource(),
				CloseButtonText = "MediaMind_JobCancelKeepGoing".GetLocalizedResource(),
				DefaultButton = ContentDialogButton.Close,
			};
			if (await dialog.ShowAsync() != ContentDialogResult.Primary)
				return;
			row.MarkCancelling();
			try
			{
				var engine = Ioc.Default.GetRequiredService<Files.App.Data.Contracts.IMediaMindEngineService>();
				if (engine.Api is not null)
					await engine.Api.Jobs.CancelAsync(row.JobId);
			}
			// Already finished: the row shows how it ended.
			catch (Exception)
			{
			}
		}

		private void Dismiss_Click(object sender, RoutedEventArgs e)
		{
			if ((sender as FrameworkElement)?.Tag is ScanJobRowViewModel row)
				ViewModel.Dismiss(row);
		}
	}
}

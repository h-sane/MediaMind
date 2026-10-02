// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Views.People;
using Files.App.ViewModels.UserControls.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using WinRT;

namespace Files.App.UserControls.MediaMind
{
	public sealed partial class SuggestionsPane : UserControl
	{
		public SuggestionsViewModel ViewModel;

		public SuggestionsPane()
		{
			InitializeComponent();

			ViewModel = Ioc.Default.GetRequiredService<SuggestionsViewModel>();
		}

		[DynamicWindowsRuntimeCast(typeof(Button))]
		private void NotADuplicateButton_Click(object sender, RoutedEventArgs e)
		{
			if (sender is Button button && button.DataContext is SuggestionItem item)
				_ = ViewModel.DismissDuplicateAsync(item);
		}

		// Opens the full bulk-review gallery in the main content frame — a
		// "same person?" call needs to see every uncertain photo, not decide
		// blind from one thumbnail on a small card.
		[DynamicWindowsRuntimeCast(typeof(Button))]
		private void ReviewPendingButton_Click(object sender, RoutedEventArgs e)
		{
			if (sender is not Button button || button.DataContext is not SuggestionItem item)
				return;

			var shellPage = Ioc.Default.GetRequiredService<IContentPageContext>().ShellPage;
			shellPage?.NavigateToPath($"pending:{item.LibraryId}:{item.PersonId}", typeof(PendingReviewPage));
		}

		[DynamicWindowsRuntimeCast(typeof(Button))]
		private void MoveOutlierButton_Click(object sender, RoutedEventArgs e)
		{
			if (sender is Button button && button.DataContext is SuggestionItem item)
				_ = ViewModel.MoveOutlierAsync(item);
		}

		[DynamicWindowsRuntimeCast(typeof(Button))]
		private void KeepOutlierButton_Click(object sender, RoutedEventArgs e)
		{
			if (sender is Button button && button.DataContext is SuggestionItem item)
				ViewModel.KeepOutlier(item);
		}
	}
}

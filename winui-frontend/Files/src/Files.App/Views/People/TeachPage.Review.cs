// Copyright (c) Files Community
// Licensed under the MIT License.

using CommunityToolkit.WinUI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Windows.Media.Playback;
using Windows.System;

namespace Files.App.Views.People
{
	// Needs your check: keyboard answers, delete, zoom, the video's controls and full screen.
	public sealed partial class TeachPage
	{
		// --- Keyboard ---------------------------------------------------------------

		// Listened for on the window, not the review panel: clicking an answer button (which is
		// disabled while it saves) otherwise takes focus off the panel and the keys stop working.
		private UIElement? keyRoot;
		private KeyEventHandler? windowKeyDown;

		private void Page_Loaded(object sender, RoutedEventArgs e)
		{
			Page_Unloaded(sender, e);
			keyRoot = MainWindow.Instance.Content;
			windowKeyDown ??= Window_KeyDown;
			keyRoot.AddHandler(KeyDownEvent, windowKeyDown, true);
		}

		private void Page_Unloaded(object sender, RoutedEventArgs e)
		{
			if (keyRoot is not null && windowKeyDown is not null)
				keyRoot.RemoveHandler(KeyDownEvent, windowKeyDown);
			keyRoot = null;
		}

		// Y = yes, N = no, S = skip, D or Del = delete, F = full screen, Esc = leave it, 0 = fit.
		// Typing in a text box and Ctrl/Alt shortcuts are left alone.
		private async void Window_KeyDown(object sender, KeyRoutedEventArgs e)
		{
			if (appInstance is not { IsCurrentPane: true }
				|| HotKeyHelpers.GetCurrentKeyModifiers() is not KeyModifiers.None
				|| e.OriginalSource is DependencyObject source && (source.FindAscendantOrSelf<TextBox>() is not null || source.FindAscendantOrSelf<AutoSuggestBox>() is not null))
				return;
			if (ViewModel.Viewer.IsOpen)
			{
				e.Handled = ViewerKey(e.Key);
				return;
			}
			if (ViewModel.IsShowingNoFaces)
			{
				if (NoFaceKey(e.Key, e.Handled))
					e.Handled = true;
				return;
			}
			if (ViewModel.IsPlacingGroups)
			{
				// The list moves its own selection with the arrows when it has focus.
				if (GroupKey(e.Key, e.Handled))
					e.Handled = true;
				return;
			}
			if (!ViewModel.IsReviewing)
				return;

			var review = ViewModel.Review;
			switch (e.Key)
			{
				case VirtualKey.Y when review.CanDecide:
					e.Handled = true;
					await review.YesAsync();
					break;
				case VirtualKey.N when review.CanDecide:
					e.Handled = true;
					await review.NoAsync();
					break;
				case VirtualKey.S:
					e.Handled = true;
					review.Skip();
					break;
				case VirtualKey.I when review.CanDecide:
					e.Handled = true;
					await review.IgnoreAsync();
					break;
				case VirtualKey.D or VirtualKey.Delete when review.CanDecide:
					e.Handled = true;
					await DeleteAsync();
					break;
				case VirtualKey.F:
					e.Handled = true;
					SetFocusMode(!focusMode);
					break;
				case VirtualKey.Escape when focusMode:
					e.Handled = true;
					SetFocusMode(false);
					break;
				case VirtualKey.Number0 or VirtualKey.NumberPad0:
					e.Handled = true;
					PreviewMedia.ResetZoom(false);
					break;
			}
		}

		private async void ReviewIgnore_Click(object sender, RoutedEventArgs e)
		{
			await ViewModel.Review.IgnoreAsync();
			FocusQueue();
		}

		// The current person's colour: a soft diagonal wash over the review area and a matching
		// edge on the picture. Kept faint so photos read true; it only has to register.
		private void ApplyPersonTint()
		{
			if (ViewModel.Review.Current is not { } item)
			{
				ReviewPanel.Background = null;
				PreviewFrame.BorderBrush = null;
				return;
			}
			var c = item.TintColor;
			ReviewPanel.Background = new LinearGradientBrush
			{
				StartPoint = new(0, 0),
				EndPoint = new(1, 1),
				GradientStops =
				{
					new GradientStop { Color = Windows.UI.Color.FromArgb(0x40, c.R, c.G, c.B), Offset = 0 },
					new GradientStop { Color = Windows.UI.Color.FromArgb(0x14, c.R, c.G, c.B), Offset = 0.55 },
					new GradientStop { Color = Windows.UI.Color.FromArgb(0x00, c.R, c.G, c.B), Offset = 1 },
				},
			};
			PreviewFrame.BorderBrush = new SolidColorBrush(Windows.UI.Color.FromArgb(0x80, c.R, c.G, c.B));
		}

		// --- Copies ---------------------------------------------------------------------

		private void UpdateCopiesButton()
		{
			var copies = ViewModel.Review.Current is { } item ? ViewModel.CopiesOf(item.Match.Path) : null;
			ReviewCopiesButton.Visibility = copies is null ? Visibility.Collapsed : Visibility.Visible;
			if (copies is not { } c)
				return;
			ReviewCopiesText.Text = string.Format(Strings.MediaMind_ReviewCopies.GetLocalizedResource(), c.Count);
			Label(ReviewCopiesButton, Strings.MediaMind_ReviewCopiesTip);
		}

		private void ReviewCopies_Click(object sender, RoutedEventArgs e)
		{
			if (ViewModel.Review.Current is { } item && ViewModel.CopiesOf(item.Match.Path) is { } c)
				AppInstance.NavigateToPath($"duplicates:{ViewModel.LibraryId}:{c.GroupId}:", typeof(DuplicatesPage));
		}

		// After a click the answer buttons are briefly disabled; put focus back on the queue.
		private void FocusQueue()
			=> ReviewList.Focus(FocusState.Programmatic);

		// --- Delete -----------------------------------------------------------------

		private async void ReviewDelete_Click(object sender, RoutedEventArgs e)
		{
			await DeleteAsync();
			FocusQueue();
		}

		private Task DeleteAsync()
			=> ViewModel.Review.DeleteSelectedFilesAsync(ConfirmDeleteAsync, DeleteFilesAsync);

		private const string DeleteWithoutAskingKey = "MediaMind.Review.DeleteWithoutAsking";

		private void UpdateAskAgainLink()
			=> ReviewAskAgainLink.Visibility = Utils.MediaMind.DeleteConfirmation.IsSkipped(DeleteWithoutAskingKey) ? Visibility.Visible : Visibility.Collapsed;

		private void ReviewAskAgain_Click(object sender, RoutedEventArgs e)
		{
			Utils.MediaMind.DeleteConfirmation.SetSkipped(DeleteWithoutAskingKey, false);
			UpdateAskAgainLink();
		}

		private async Task<bool> ConfirmDeleteAsync(IReadOnlyList<string> paths)
		{
			var toBin = Utils.MediaMind.DeleteConfirmation.IsSkipped(DeleteWithoutAskingKey)
				|| await Ioc.Default.GetRequiredService<IStorageTrashBinService>().CanGoTrashBin(paths[0]);
			var ok = await Utils.MediaMind.DeleteConfirmation.ConfirmAsync(XamlRoot, paths, toBin, DeleteWithoutAskingKey);
			UpdateAskAgainLink();
			return ok;
		}

		// The app's own delete, run after the card is already gone: files go to the Recycle Bin
		// where the drive has one (and land in undo history), otherwise they are deleted permanently.
		private async Task<bool> DeleteFilesAsync(IReadOnlyList<string> paths)
		{
			// A file that is playing cannot be deleted.
			if (ViewModel.Review.Current is { } current && paths.Contains(current.Match.AbsPath, StringComparer.OrdinalIgnoreCase))
				StopVideo();
			var items = paths.Select(p => StorageHelpers.FromPathAndType(p, FilesystemItemType.File));
			var result = await AppInstance.FilesystemHelpers.DeleteItemsAsync(items, DeleteConfirmationPolicies.Never, false, true);
			// The disk is the truth: a permanent delete on a network drive can report InProgress,
			// and a mounted vault can show the file for a moment after it is gone.
			var deleted = false;
			for (var i = 0; result != ReturnResult.Cancelled && i < 15 && !(deleted = paths.All(p => !SystemIO.File.Exists(p))); i++)
				await Task.Delay(200);
			return deleted;
		}

		private static void Label(FrameworkElement element, string resource)
		{
			var text = resource.GetLocalizedResource();
			AutomationProperties.SetName(element, text);
			ToolTipService.SetToolTip(element, text);
		}

		// --- Full screen ----------------------------------------------------------------

		// Full screen: the window is maximized (not the full-screen presenter, which hides the
		// minimize/maximize/close buttons), the page header and people list step aside, and the
		// picture takes all the room the list and the answers column leave.
		private bool focusMode;
		private bool focusMaximizedWindow;

		private void ReviewFullScreen_Click(object sender, RoutedEventArgs e)
			=> SetFocusMode(!focusMode);

		private static void ShowFullScreenState(Button button, FontIcon icon, bool on)
		{
			icon.Glyph = on ? "" : "";
			Label(button, on ? Strings.MediaMind_ReviewExitFullScreen : Strings.MediaMind_ReviewFullScreen);
		}

		private void SetFocusMode(bool on)
		{
			if (on == focusMode)
				return;
			focusMode = on;
			HeaderGrid.Visibility = on || ViewModel.Viewer.IsOpen ? Visibility.Collapsed : Visibility.Visible;
			FilterList.Visibility = on ? Visibility.Collapsed : Visibility.Visible;
			ApplyColumns(ContainerGrid.ActualWidth);

			// The same full screen in Needs your check, No one named yet and Group pictures.
			ShowFullScreenState(ReviewFullScreenButton, FullScreenIcon, on);
			ShowFullScreenState(ViewerFullScreenButton, ViewerFullScreenIcon, on);
			ShowFullScreenState(GroupFullScreenButton, GroupFullScreenIcon, on);
			ShowFullScreenState(NoFaceFullScreenButton, NoFaceFullScreenIcon, on);

			if (MainWindow.Instance.AppWindow.Presenter is not OverlappedPresenter presenter)
				return;
			if (on && presenter.State is not OverlappedPresenterState.Maximized)
			{
				presenter.Maximize();
				focusMaximizedWindow = true;
			}
			else if (!on && focusMaximizedWindow)
			{
				if (presenter.State is OverlappedPresenterState.Maximized)
					presenter.Restore();
				focusMaximizedWindow = false;
			}
		}

		// Below this page width the lists beside the picture shrink to their thumbnails, so the
		// picture keeps its room; the answers stay in their column on the right.
		private const double NarrowPageWidth = 1100;

		private void ApplyColumns(double width)
		{
			var narrow = width < NarrowPageWidth;
			FilterColumn.Width = new GridLength(focusMode ? 0 : narrow ? 200 : 248);
			BodyGrid.ColumnSpacing = focusMode ? 0 : 16;
			// Full screen gives the room to the picture: the queue keeps its width, it doesn't grow.
			QueueColumn.Width = new GridLength(narrow ? 104 : 300);
			PreviewColumn.Width = new GridLength(1, GridUnitType.Star);
			ReviewAnswersColumn.Width = new GridLength(width < 1400 ? 220 : 300);
			// The viewer's names column gives the picture more room on smaller windows.
			ViewerAnswersColumn.Width = new GridLength(width < 1400 ? 220 : 300);
			GroupAnswersColumn.Width = new GridLength(width < 1400 ? 220 : 300);
			GroupListColumn.Width = new GridLength(narrow ? 96 : 300);
			// A thumbnail strip has no room for the explanation; it would push the pictures off the bottom.
			GroupsIntroText.Visibility = narrow ? Visibility.Collapsed : Visibility.Visible;
			NoFaceListColumn.Width = new GridLength(narrow ? 96 : 300);
			NoFacesIntroText.Visibility = narrow ? Visibility.Collapsed : Visibility.Visible;
			NoFaceAnswersColumn.Width = new GridLength(width < 1400 ? 220 : 300);
			// The person bar's folder line gets its own row when the buttons would squeeze it out.
			var stacked = width < 1400;
			Grid.SetRow(PersonFolderPanel, stacked ? 1 : 0);
			Grid.SetColumn(PersonFolderPanel, stacked ? 0 : 1);
			Grid.SetColumnSpan(PersonFolderPanel, stacked ? 4 : 1);
		}
	}
}

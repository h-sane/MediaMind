// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.ViewModels.People;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Windows.Media.Playback;
using Windows.System;

namespace Files.App.Views.People
{
	// The full-size viewer over the face grid: open, walk, name, and its video.
	public sealed partial class TeachPage
	{
		private void OpenViewer(TeachFaceTileViewModel tile)
		{
			// The grid's selection would otherwise keep the selection bar (Name as, for the grid) up.
			FaceGrid.SelectedItems.Clear();
			ViewModel.OpenViewer(tile);
			DispatcherQueue.TryEnqueue(() => ViewerBackButton.Focus(FocusState.Programmatic));
		}

		private void FaceGrid_DoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
		{
			if ((e.OriginalSource as FrameworkElement)?.DataContext is TeachFaceTileViewModel tile)
				OpenViewer(tile);
		}

		private void ViewButton_Click(object sender, RoutedEventArgs e)
		{
			if (FaceGrid.SelectedItems.OfType<TeachFaceTileViewModel>().FirstOrDefault() is { } tile)
				OpenViewer(tile);
		}

		private void ViewerBack_Click(object sender, RoutedEventArgs e)
			=> ViewModel.Viewer.Close();

		private void ViewerPrevious_Click(object sender, RoutedEventArgs e)
			=> ViewModel.Viewer.Previous();

		private void ViewerNext_Click(object sender, RoutedEventArgs e)
			=> ViewModel.Viewer.Next();

		private async void ViewerPerson_Click(object sender, RoutedEventArgs e)
		{
			if ((sender as FrameworkElement)?.Tag is string name)
				await ViewModel.Viewer.NameAsync(name);
		}

		private async void ViewerNameBox_QuerySubmitted(AutoSuggestBox sender, AutoSuggestBoxQuerySubmittedEventArgs args)
		{
			var name = args.ChosenSuggestion as string ?? sender.Text;
			ViewerNameFlyout.Hide();
			sender.Text = string.Empty;
			await ViewModel.Viewer.NameAsync(name);
		}

		private async void ViewerOpen_Click(object sender, RoutedEventArgs e)
		{
			if (ViewModel.Viewer.Current is not { } tile)
				return;
			StopViewerVideo();
			try
			{
				await Launcher.LaunchFileAsync(await Windows.Storage.StorageFile.GetFileFromPathAsync(tile.Face.AbsPath));
			}
			// The drive may be offline; the viewer already shows what it can.
			catch (Exception)
			{
			}
		}

		private void ViewerFullScreen_Click(object sender, RoutedEventArgs e)
			=> SetFocusMode(!focusMode);

		// Left/Right walk, 1-9 name as the person with that number, F = full screen,
		// Esc leaves full screen first, then goes back to the faces.
		private bool ViewerKey(VirtualKey key)
		{
			var viewer = ViewModel.Viewer;
			switch (key)
			{
				case VirtualKey.F:
					SetFocusMode(!focusMode);
					return true;
				case VirtualKey.Escape when focusMode:
					SetFocusMode(false);
					return true;
				case VirtualKey.Escape:
					viewer.Close();
					return true;
				case VirtualKey.Left:
					viewer.Previous();
					return true;
				case VirtualKey.Right:
					viewer.Next();
					return true;
				case VirtualKey.Number0 or VirtualKey.NumberPad0:
					ViewerMedia.ResetZoom(false);
					return true;
			}
			var digit = key is >= VirtualKey.Number1 and <= VirtualKey.Number9 ? key - VirtualKey.Number1
				: key is >= VirtualKey.NumberPad1 and <= VirtualKey.NumberPad9 ? key - VirtualKey.NumberPad1
				: -1;
			if (digit < 0 || digit >= viewer.People.Count || viewer.People[digit].Key.Length == 0)
				return false;
			_ = viewer.NameAsync(viewer.People[digit].Name);
			return true;
		}

		private void Viewer_PropertyChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
		{
			// The page header steps aside while the viewer is open, so the picture gets the height.
			if (e.PropertyName == nameof(TeachViewerViewModel.IsOpen))
			{
				HeaderGrid.Visibility = ViewModel.Viewer.IsOpen || focusMode ? Visibility.Collapsed : Visibility.Visible;
				if (!ViewModel.Viewer.IsOpen)
					SetFocusMode(false);
			}
			if (e.PropertyName == nameof(TeachViewerViewModel.Current))
			{
				ViewerMedia.ResetZoom(true);
				PlayViewerVideo();
			}
		}

		// A video plays by itself, looping, streamed from the file; if Windows can't decode it the
		// viewer shows the frame the face was found in.
		private void PlayViewerVideo()
		{
			StopViewerVideo();
			var viewer = ViewModel.Viewer;
			if (viewer.Current is not { } tile || !viewer.IsVideo)
				return;
			try
			{
				var player = new MediaPlayer { AutoPlay = true, IsLoopingEnabled = true };
				viewer.ReportVideo(true);
				player.PlaybackSession.PlaybackStateChanged += (session, _) =>
				{
					var loading = session.PlaybackState is MediaPlaybackState.Opening or MediaPlaybackState.Buffering;
					DispatcherQueue.TryEnqueue(() => { if (viewer.Current == tile && ViewerMedia.Player == player) viewer.ReportVideo(loading); });
				};
				player.MediaFailed += (_, _) => DispatcherQueue.TryEnqueue(() =>
				{
					// A replaced player reports a failure as it is disposed; only the live one counts.
					if (viewer.Current != tile || ViewerMedia.Player != player)
						return;
					StopViewerVideo();
					viewer.ReportVideoFailed();
				});
				player.Source = Windows.Media.Core.MediaSource.CreateFromUri(new Uri(tile.Face.AbsPath));
				ViewerMedia.SetPlayer(player);
			}
			catch (Exception)
			{
				StopViewerVideo();
				viewer.ReportVideoFailed();
			}
		}

		private void StopViewerVideo()
		{
			var old = ViewerMedia.Player;
			if (old is null)
				return;
			ViewerMedia.SetPlayer(null);
			old.Pause();
			(old.Source as IDisposable)?.Dispose();
			old.Dispose();
		}
	}
}

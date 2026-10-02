// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Services.MediaMind;
using Files.App.ViewModels.People;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Media.Playback;
using Windows.System;

namespace Files.App.Views.People
{
	// One copy full screen: the whole picture with zoom, or the video with sound and its bar
	// (MediaZoomView, as in Who's who), the set's copies one after another, and Keep this one.
	// Side-by-side cards are too small to judge two near-identical copies (2026-09-27). The window
	// is maximized while it is open (not the full-screen presenter, which hides the caption buttons).
	public sealed partial class DuplicatesPage
	{
		private int viewerIndex = -1;
		private int viewerLoad;
		private bool viewerMaximizedWindow;

		private bool IsCopyViewerOpen => CopyViewer.Visibility == Visibility.Visible;

		private IReadOnlyList<DuplicateMemberViewModel> ViewerCopies
			=> ViewModel.Current?.Members ?? Array.Empty<DuplicateMemberViewModel>();

		private void CopyFullScreen_Click(object sender, RoutedEventArgs e)
		{
			if ((sender as FrameworkElement)?.Tag is DuplicateMemberViewModel member)
				OpenCopyViewer(member);
		}

		private void OpenCopyViewer(DuplicateMemberViewModel member)
		{
			var index = IndexOfCopy(member);
			if (index < 0)
				return;
			// The cards' videos stop playing behind it; they start again when it closes.
			foreach (var entry in players.Values)
				entry.Player.Pause();
			CopyViewer.Visibility = Visibility.Visible;
			CopyViewerSideColumn.Width = new GridLength(ActualWidth < 1400 ? 220 : 300);
			if (MainWindow.Instance.AppWindow.Presenter is OverlappedPresenter { State: not OverlappedPresenterState.Maximized } presenter)
			{
				presenter.Maximize();
				viewerMaximizedWindow = true;
			}
			ShowCopy(index);
		}

		private void CloseCopyViewer()
		{
			StopViewerVideo();
			CopyViewer.Visibility = Visibility.Collapsed;
			CopyMedia.ImageSource = null;
			viewerIndex = -1;
			if (viewerMaximizedWindow && MainWindow.Instance.AppWindow.Presenter is OverlappedPresenter { State: OverlappedPresenterState.Maximized } presenter)
				presenter.Restore();
			viewerMaximizedWindow = false;
			foreach (var entry in players.Values)
				entry.Player.Play();
		}

		private int IndexOfCopy(DuplicateMemberViewModel member)
		{
			var copies = ViewerCopies;
			for (var i = 0; i < copies.Count; i++)
				if (copies[i] == member)
					return i;
			return -1;
		}

		private void ShowCopy(int index)
		{
			var copies = ViewerCopies;
			if (copies.Count == 0)
			{
				CloseCopyViewer();
				return;
			}
			viewerIndex = (index % copies.Count + copies.Count) % copies.Count;
			var member = copies[viewerIndex];
			CopyViewerTitle.Text = string.Format(Strings.MediaMind_DupViewTitle.GetLocalizedResource(), member.Number, copies.Count, member.FileName);
			CopyViewerFacts.Text = string.Join("\n", new[] { member.Folder, member.Facts, member.Modified }.Where(t => !string.IsNullOrEmpty(t)));
			ToolTipService.SetToolTip(CopyViewerTitle, member.AbsPath);
			CopyViewerPrevious.IsEnabled = CopyViewerNext.IsEnabled = copies.Count > 1;
			ShowKeepState(member);

			StopViewerVideo();
			CopyMedia.ResetZoom(true);
			CopyMedia.ImageName = member.FileName;
			CopyMedia.ImageSource = null;
			var load = ++viewerLoad;
			if (member.IsVideo && PlayViewerVideo(member, load))
				return;
			ShowStill(member, load);
		}

		private void ShowKeepState(DuplicateMemberViewModel member)
		{
			CopyViewerKeep.Content = member.IsKeeper
				? Strings.MediaMind_DupViewKeeping.GetLocalizedResource()
				: string.Format(Strings.MediaMind_DupViewKeep.GetLocalizedResource(), member.Number);
			CopyViewerKeep.IsEnabled = !member.IsKeeper;
		}

		// A picture is shown whole, from the file; if it can't be read or decoded here, the
		// engine's large thumbnail stands in.
		private async void ShowStill(DuplicateMemberViewModel member, int load)
		{
			CopyMedia.PlayerVisibility = Visibility.Collapsed;
			CopyMedia.ImageVisibility = Visibility.Visible;
			CopyViewerRing.IsActive = true;
			BitmapImage? bitmap = null;
			try
			{
				if (!member.IsVideo)
					bitmap = await (await Task.Run(() => SystemIO.File.ReadAllBytesAsync(member.AbsPath))).ToBitmapAsync();
			}
			// Offline drive, or a format Windows can't decode: the thumbnail below.
			catch (Exception)
			{
			}
			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (bitmap is null && engine.Api is not null)
					bitmap = await (await engine.Api.Duplicates.ThumbnailAsync(ViewModel.LibraryId, member.File.Id, 1024)).ToBitmapAsync();
			}
			catch (Exception)
			{
			}
			if (load != viewerLoad)
				return;
			CopyMedia.ImageSource = bitmap ?? member.Thumbnail;
			CopyViewerRing.IsActive = false;
		}

		// A video plays with sound, looping, streamed from the file. False if it can't start.
		private bool PlayViewerVideo(DuplicateMemberViewModel member, int load)
		{
			try
			{
				var player = new MediaPlayer { AutoPlay = true, IsLoopingEnabled = true };
				CopyViewerRing.IsActive = true;
				player.PlaybackSession.PlaybackStateChanged += (session, _) =>
				{
					var loading = session.PlaybackState is MediaPlaybackState.Opening or MediaPlaybackState.Buffering;
					DispatcherQueue.TryEnqueue(() => { if (load == viewerLoad) CopyViewerRing.IsActive = loading; });
				};
				player.MediaFailed += (_, _) => DispatcherQueue.TryEnqueue(() =>
				{
					// A replaced player reports a failure as it is disposed; only the live one counts.
					if (load != viewerLoad || CopyMedia.Player != player)
						return;
					StopViewerVideo();
					ShowStill(member, load);
				});
				player.Source = Windows.Media.Core.MediaSource.CreateFromUri(new Uri(member.AbsPath));
				CopyMedia.ImageVisibility = Visibility.Collapsed;
				CopyMedia.PlayerVisibility = Visibility.Visible;
				CopyMedia.SetPlayer(player);
				return true;
			}
			catch (Exception)
			{
				StopViewerVideo();
				return false;
			}
		}

		private void StopViewerVideo()
		{
			var old = CopyMedia.Player;
			if (old is null)
				return;
			CopyMedia.SetPlayer(null);
			old.Pause();
			(old.Source as IDisposable)?.Dispose();
			old.Dispose();
		}

		private void CopyViewerPrevious_Click(object sender, RoutedEventArgs e)
			=> ShowCopy(viewerIndex - 1);

		private void CopyViewerNext_Click(object sender, RoutedEventArgs e)
			=> ShowCopy(viewerIndex + 1);

		private void CopyViewerClose_Click(object sender, RoutedEventArgs e)
			=> CloseCopyViewer();

		private void CopyViewerKeep_Click(object sender, RoutedEventArgs e)
			=> KeepViewerCopy(viewerIndex);

		// Picks the keeper (as clicking its card does); the decision itself stays on the page.
		private void KeepViewerCopy(int index)
		{
			var copies = ViewerCopies;
			if (index < 0 || index >= copies.Count)
				return;
			ViewModel.ChooseKeeper(copies[index].Number);
			ShowKeepState(copies[viewerIndex]);
		}

		private async void CopyViewerOpen_Click(object sender, RoutedEventArgs e)
		{
			var copies = ViewerCopies;
			if (viewerIndex < 0 || viewerIndex >= copies.Count)
				return;
			StopViewerVideo();
			try
			{
				await Launcher.LaunchFileAsync(await Windows.Storage.StorageFile.GetFileFromPathAsync(copies[viewerIndex].AbsPath));
			}
			// The drive may be offline; the viewer already shows what it can.
			catch (Exception)
			{
			}
		}

		// Left/Right = the other copies, 1-9 = keep that copy, 0 = fit, F or Esc = close.
		// Anything else (K, N, S) closes the viewer and then acts as on the page.
		private bool CopyViewerKey(VirtualKey key)
		{
			switch (key)
			{
				case VirtualKey.Left:
					ShowCopy(viewerIndex - 1);
					return true;
				case VirtualKey.Right:
					ShowCopy(viewerIndex + 1);
					return true;
				case VirtualKey.Escape or VirtualKey.F:
					CloseCopyViewer();
					return true;
				case VirtualKey.Number0 or VirtualKey.NumberPad0:
					CopyMedia.ResetZoom(false);
					return true;
			}
			var digit = key is >= VirtualKey.Number1 and <= VirtualKey.Number9 ? key - VirtualKey.Number1
				: key is >= VirtualKey.NumberPad1 and <= VirtualKey.NumberPad9 ? key - VirtualKey.NumberPad1
				: -1;
			if (digit >= 0)
			{
				var copies = ViewerCopies;
				for (var i = 0; i < copies.Count; i++)
					if (copies[i].Number == digit + 1)
					{
						KeepViewerCopy(i);
						ShowCopy(i);
					}
				return true;
			}
			CloseCopyViewer();
			return false;
		}
	}
}

// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.ViewModels.People;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Media.Playback;
using Windows.System;

namespace Files.App.Views.People
{
	// No faces found: look at each file, then keep it where it is, move it into a folder, or delete it.
	public sealed partial class TeachPage
	{
		private void NoFaceList_ContainerContentChanging(ListViewBase sender, ContainerContentChangingEventArgs args)
		{
			if (!args.InRecycleQueue && args.Item is TeachNoFaceItem item)
				item.EnsureThumbnail();
		}

		private void NoFaceFullScreen_Click(object sender, RoutedEventArgs e)
			=> SetFocusMode(!focusMode);

		private async void NoFaceOpen_Click(object sender, RoutedEventArgs e)
		{
			if (ViewModel.CurrentNoFace is not { } item)
				return;
			StopNoFaceVideo();
			try
			{
				await Launcher.LaunchFileAsync(await Windows.Storage.StorageFile.GetFileFromPathAsync(item.File.AbsPath));
			}
			// The drive may be offline; the page already shows what it can.
			catch (Exception)
			{
			}
		}

		// Keep it where it is: nothing changes on disk, the next one shows.
		private void NoFaceKeep_Click(object sender, RoutedEventArgs e)
			=> ViewModel.SelectNextNoFace(1);

		private async void NoFaceMove_Click(object sender, RoutedEventArgs e)
		{
			if (ViewModel.CurrentNoFace is not { } item)
				return;
			if (!Utils.MediaMind.FolderPicker.Pick(out var folder, ViewModel.WorkingFolder))
				return;
			// A playing file can't be moved.
			StopNoFaceVideo();
			await ViewModel.MoveNoFaceAsync(item, folder);
		}

		private async void NoFaceDelete_Click(object sender, RoutedEventArgs e)
			=> await DeleteNoFaceAsync();

		// The same confirmation and delete as Needs your check: the Recycle Bin where the drive has one.
		private async Task DeleteNoFaceAsync()
		{
			if (ViewModel.CurrentNoFace is not { } item)
				return;
			string[] paths = [item.File.AbsPath];
			if (!await ConfirmDeleteAsync(paths))
				return;
			StopNoFaceVideo();
			if (await DeleteFilesAsync(paths))
				await ViewModel.AfterNoFaceDeletedAsync(item);
		}

		// A video plays by itself (looping, with the video bar), streamed from the file.
		private void PlayNoFaceVideo()
		{
			StopNoFaceVideo();
			var vm = ViewModel;
			if (vm.CurrentNoFace is not { IsVideo: true } item)
				return;
			try
			{
				var player = new MediaPlayer { AutoPlay = true, IsLoopingEnabled = true };
				vm.ReportNoFaceVideo(true);
				player.PlaybackSession.PlaybackStateChanged += (session, _) =>
				{
					var loading = session.PlaybackState is MediaPlaybackState.Opening or MediaPlaybackState.Buffering;
					DispatcherQueue.TryEnqueue(() => { if (vm.CurrentNoFace == item && NoFaceMedia.Player == player) vm.ReportNoFaceVideo(loading); });
				};
				player.MediaFailed += (_, _) => DispatcherQueue.TryEnqueue(() =>
				{
					// A replaced player reports a failure as it is disposed; only the live one counts.
					if (vm.CurrentNoFace != item || NoFaceMedia.Player != player)
						return;
					StopNoFaceVideo();
					vm.ReportNoFaceVideoFailed();
				});
				player.Source = Windows.Media.Core.MediaSource.CreateFromUri(new Uri(item.File.AbsPath));
				NoFaceMedia.SetPlayer(player);
			}
			catch (Exception)
			{
				StopNoFaceVideo();
				vm.ReportNoFaceVideoFailed();
			}
		}

		private void StopNoFaceVideo()
		{
			var old = NoFaceMedia.Player;
			if (old is null)
				return;
			NoFaceMedia.SetPlayer(null);
			old.Pause();
			(old.Source as IDisposable)?.Dispose();
			old.Dispose();
		}

		private void OnCurrentNoFaceChanged()
		{
			NoFaceMedia.ResetZoom(true);
			if (ViewModel.IsShowingNoFaces)
				PlayNoFaceVideo();
			else
				StopNoFaceVideo();
			if (ViewModel.CurrentNoFace is { } item)
				NoFaceList.ScrollIntoView(item);
		}

		// Up/Down walk the list, F = full screen, Esc = leave it, 0 = fit, Del = delete (asks first).
		private bool NoFaceKey(VirtualKey key, bool handledByList)
		{
			switch (key)
			{
				case VirtualKey.Up when !handledByList:
					ViewModel.SelectNextNoFace(-1);
					return true;
				case VirtualKey.Down when !handledByList:
					ViewModel.SelectNextNoFace(1);
					return true;
				case VirtualKey.F:
					SetFocusMode(!focusMode);
					return true;
				case VirtualKey.Escape when focusMode:
					SetFocusMode(false);
					return true;
				case VirtualKey.Number0 or VirtualKey.NumberPad0:
					NoFaceMedia.ResetZoom(false);
					return true;
				case VirtualKey.Delete:
					_ = DeleteNoFaceAsync();
					return true;
			}
			return false;
		}
	}
}

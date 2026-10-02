// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Services.MediaMind;
using Files.App.ViewModels.People;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Windows.Media.Playback;
using Windows.System;

namespace Files.App.Views.People
{
	// People folders: choosing a person's folder, moving their files there, and placing group pictures.
	public sealed partial class TeachPage
	{
		private void ChooseFolder_Click(object sender, RoutedEventArgs e)
		{
			if (Utils.MediaMind.FolderPicker.Pick(out var folder, ViewModel.WorkingFolder))
				_ = ViewModel.SetPrimaryFolderAsync(folder);
		}

		private async void MoveFiles_Click(object sender, RoutedEventArgs e)
		{
			if (ViewModel.SelectedFilter?.PersonId is not long personId || await ViewModel.GetMovePlanAsync() is not { } plan)
				return;

			var lines = new List<string>
			{
				plan.Moves == 0
					? string.Format(Strings.MediaMind_TeachMoveNothing.GetLocalizedResource(), plan.Name)
					: string.Format(Strings.MediaMind_TeachMoveSummary.GetLocalizedResource(), plan.Moves, plan.PrimaryLocation),
			};
			if (plan.AlreadyThere > 0)
				lines.Add(string.Format(Strings.MediaMind_TeachMoveAlreadyThere.GetLocalizedResource(), plan.AlreadyThere, plan.Name));
			if (plan.ToGroupFolders > 0)
				lines.Add(string.Format(Strings.MediaMind_TeachMoveToGroups.GetLocalizedResource(), plan.ToGroupFolders));
			if (plan.GroupsWaiting > 0)
				lines.Add(string.Format(Strings.MediaMind_TeachGroupsWaiting.GetLocalizedResource(), plan.GroupsWaiting));
			if (plan.Moves > 0)
				lines.Add(Strings.MediaMind_TeachMoveSafety.GetLocalizedResource());

			var dialog = new ContentDialog
			{
				XamlRoot = XamlRoot,
				Title = string.Format(Strings.MediaMind_TeachMoveTitle.GetLocalizedResource(), plan.Name),
				Content = new TextBlock { Text = string.Join("\n\n", lines), TextWrapping = TextWrapping.Wrap, MaxWidth = 480 },
				PrimaryButtonText = plan.Moves > 0 ? string.Format(Strings.MediaMind_TeachMoveConfirm.GetLocalizedResource(), plan.Moves) : string.Empty,
				CloseButtonText = plan.Moves > 0 ? "Cancel".GetLocalizedResource() : Strings.MediaMind_TeachMoveOk.GetLocalizedResource(),
				DefaultButton = plan.Moves > 0 ? ContentDialogButton.Primary : ContentDialogButton.Close,
			};
			if (await dialog.ShowAsync() == ContentDialogResult.Primary)
				await ViewModel.MoveFilesAsync(personId, plan);
		}

		private async void ActivityCancel_Click(object sender, RoutedEventArgs e)
		{
			if (ViewModel.ActivityJobIsMove)
			{
				var dialog = new ContentDialog
				{
					XamlRoot = XamlRoot,
					Title = "MediaMind_JobCancelMoveTitle".GetLocalizedResource(),
					Content = new TextBlock { Text = "MediaMind_JobCancelMoveText".GetLocalizedResource(), TextWrapping = TextWrapping.Wrap, MaxWidth = 440 },
					PrimaryButtonText = "MediaMind_JobCancelConfirm".GetLocalizedResource(),
					CloseButtonText = "MediaMind_JobCancelKeepGoing".GetLocalizedResource(),
					DefaultButton = ContentDialogButton.Close,
				};
				if (await dialog.ShowAsync() != ContentDialogResult.Primary)
					return;
			}
			await ViewModel.CancelActivityAsync();
		}

		private void GroupList_ContainerContentChanging(ListViewBase sender, ContainerContentChangingEventArgs args)
		{
			if (!args.InRecycleQueue && args.Item is TeachGroupItem item)
				item.EnsureThumbnail();
		}

		private async void GroupFolder_Click(object sender, RoutedEventArgs e)
		{
			if (ViewModel.CurrentGroup is { } item && (sender as FrameworkElement)?.Tag is string person)
				await PlaceGroupAsync(item, "person", person, null, null);
		}

		private async void GroupStay_Click(object sender, RoutedEventArgs e)
		{
			if (ViewModel.CurrentGroup is { } item)
				await PlaceGroupAsync(item, "stay", null, null, null);
		}

		// The folder list opens on the search box, so typing filters it (or names a new folder).
		private void GroupFolderFlyout_Opened(object sender, object e)
			=> GroupFolderBox.Focus(FocusState.Programmatic);

		private async void GroupExistingFolder_ItemClick(object sender, ItemClickEventArgs e)
		{
			if (ViewModel.CurrentGroup is { } item && e.ClickedItem is GroupExistingFolder folder)
				await PlaceGroupAsync(item, "existing", null, null, folder.Path);
		}

		private async void GroupCreate_Click(object sender, RoutedEventArgs e)
		{
			GroupFolderFlyout.Hide();
			StopGroupVideo();
			await ViewModel.SubmitGroupFolderAsync();
		}

		private async void GroupFolderBox_KeyDown(object sender, KeyRoutedEventArgs e)
		{
			if (e.Key != VirtualKey.Enter)
				return;
			e.Handled = true;
			GroupFolderFlyout.Hide();
			StopGroupVideo();
			await ViewModel.SubmitGroupFolderAsync();
		}

		// A playing file can't be moved: the player lets go of it first.
		private Task PlaceGroupAsync(TeachGroupItem item, string choice, string? person, string? folderName, string? folderPath)
		{
			GroupFolderFlyout.Hide();
			StopGroupVideo();
			return ViewModel.PlaceGroupAsync(item, choice, person, folderName, ViewModel.GroupRemember, folderPath);
		}

		private async void GroupOpen_Click(object sender, RoutedEventArgs e)
		{
			if (ViewModel.CurrentGroup is not { } item)
				return;
			StopGroupVideo();
			try
			{
				await Launcher.LaunchFileAsync(await Windows.Storage.StorageFile.GetFileFromPathAsync(item.Question.AbsPath));
			}
			// The drive may be offline; the page already shows what it can.
			catch (Exception)
			{
			}
		}

		private void GroupFullScreen_Click(object sender, RoutedEventArgs e)
			=> SetFocusMode(!focusMode);

		// A group video plays by itself (looping, with the video bar), streamed from the file.
		private void PlayGroupVideo()
		{
			StopGroupVideo();
			var vm = ViewModel;
			if (vm.CurrentGroup is not { IsVideo: true } item)
				return;
			try
			{
				var player = new MediaPlayer { AutoPlay = true, IsLoopingEnabled = true };
				vm.ReportGroupVideo(true);
				player.PlaybackSession.PlaybackStateChanged += (session, _) =>
				{
					var loading = session.PlaybackState is MediaPlaybackState.Opening or MediaPlaybackState.Buffering;
					DispatcherQueue.TryEnqueue(() => { if (vm.CurrentGroup == item && GroupMedia.Player == player) vm.ReportGroupVideo(loading); });
				};
				player.MediaFailed += (_, _) => DispatcherQueue.TryEnqueue(() =>
				{
					// A replaced player reports a failure as it is disposed; only the live one counts.
					if (vm.CurrentGroup != item || GroupMedia.Player != player)
						return;
					StopGroupVideo();
					vm.ReportGroupVideoFailed();
				});
				player.Source = Windows.Media.Core.MediaSource.CreateFromUri(new Uri(item.Question.AbsPath));
				GroupMedia.SetPlayer(player);
			}
			catch (Exception)
			{
				StopGroupVideo();
				vm.ReportGroupVideoFailed();
			}
		}

		private void StopGroupVideo()
		{
			var old = GroupMedia.Player;
			if (old is null)
				return;
			GroupMedia.SetPlayer(null);
			old.Pause();
			(old.Source as IDisposable)?.Dispose();
			old.Dispose();
		}

		// The picture on screen changed (a click in the list, an answer, a reload).
		private void OnCurrentGroupChanged()
		{
			GroupMedia.ResetZoom(true);
			if (ViewModel.IsPlacingGroups)
				PlayGroupVideo();
			else
				StopGroupVideo();
			if (ViewModel.CurrentGroup is { } item)
				GroupList.ScrollIntoView(item);
		}

		// Up/Down walk the list, F = full screen, Esc = leave it, 0 = fit the picture again.
		private bool GroupKey(VirtualKey key, bool handledByList)
		{
			switch (key)
			{
				case VirtualKey.Up when !handledByList:
					ViewModel.SelectNextGroup(-1);
					return true;
				case VirtualKey.Down when !handledByList:
					ViewModel.SelectNextGroup(1);
					return true;
				case VirtualKey.F:
					SetFocusMode(!focusMode);
					return true;
				case VirtualKey.Escape when focusMode:
					SetFocusMode(false);
					return true;
				case VirtualKey.Number0 or VirtualKey.NumberPad0:
					GroupMedia.ResetZoom(false);
					return true;
			}
			return false;
		}
	}
}

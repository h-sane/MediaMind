// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.ViewModels.People;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Navigation;
using Windows.System;

namespace Files.App.Views.People
{
	// MediaMind: "Who's who" — name a few clear faces per person, then sort the whole
	// library by them. A full page in the content frame (not a dialog): picking good
	// examples needs room to see many faces at once. See TeachPageViewModel.
	public sealed partial class TeachPage : Page
	{
		private IShellPage? appInstance;
		private IShellPage AppInstance
			=> appInstance ?? throw new InvalidOperationException("The Who's who page has not been initialized.");

		public TeachPageViewModel ViewModel { get; private set; } = null!;

		public TeachPage()
		{
			InitializeComponent();
			Loaded += Page_Loaded;
			Unloaded += Page_Unloaded;
		}

		protected override async void OnNavigatedTo(NavigationEventArgs e)
		{
			if (e.Parameter is not NavigationArguments parameters || parameters.NavPathParam is not string navPath)
				return;

			appInstance = parameters.AssociatedTabInstance!;

			// "teach:{libraryId}:{under}" or "teach::{folderPath}" (not scanned yet)
			var parts = navPath.Split(':', 3);
			var libraryId = parts.Length > 1 ? parts[1] : string.Empty;
			var rest = parts.Length > 2 ? parts[2] : string.Empty;
			ViewModel = libraryId.Length > 0
				? new TeachPageViewModel(libraryId, rest, string.Empty)
				: new TeachPageViewModel(string.Empty, string.Empty, rest);
			ViewModel.PropertyChanged += ViewModel_PropertyChanged;
			ViewModel.Review.PropertyChanged += Review_PropertyChanged;
			ViewModel.Viewer.PropertyChanged += Viewer_PropertyChanged;
			Bindings.Update();
			UpdateAskAgainLink();

			var shellViewModel = AppInstance.GetRequiredShellViewModel();

			AppInstance.InstanceViewModel.IsPageTypeNotHome = true;
			AppInstance.InstanceViewModel.IsPageTypeSearchResults = false;
			AppInstance.InstanceViewModel.IsPageTypeMtpDevice = false;
			AppInstance.InstanceViewModel.IsPageTypeRecycleBin = false;
			AppInstance.InstanceViewModel.IsPageTypeCloudDrive = false;
			AppInstance.InstanceViewModel.IsPageTypeFtp = false;
			AppInstance.InstanceViewModel.IsPageTypeZipFolder = false;
			AppInstance.InstanceViewModel.IsPageTypeLibrary = false;
			AppInstance.InstanceViewModel.GitRepositoryPath = null;
			AppInstance.InstanceViewModel.IsGitRepository = false;
			AppInstance.InstanceViewModel.IsPageTypeReleaseNotes = false;
			// Refresh reloads this page; Up goes back to its folder (ModernShellPage).
			AppInstance.ToolbarViewModel.CanRefresh = true;
			AppInstance.ToolbarViewModel.CanGoBack = AppInstance.CanNavigateBackward;
			AppInstance.ToolbarViewModel.CanGoForward = AppInstance.CanNavigateForward;
			AppInstance.ToolbarViewModel.CanNavigateToParent = true;

			await shellViewModel.SetWorkingDirectoryAsync("Home");

			AppInstance.ToolbarViewModel.PathComponents.Clear();
			AppInstance.ToolbarViewModel.PathComponents.Add(new PathBoxItem()
			{
				Title = Strings.MediaMind_TeachTitle.GetLocalizedResource(),
				Path = navPath,
			});

			Utils.MediaMind.SidebarAutoCollapse.Enter();
			base.OnNavigatedTo(e);
		}

		private void ContainerGrid_SizeChanged(object sender, SizeChangedEventArgs e)
			=> ApplyColumns(e.NewSize.Width);

		private void FaceGrid_ContainerContentChanging(ListViewBase sender, ContainerContentChangingEventArgs args)
		{
			if (!args.InRecycleQueue && args.Item is TeachFaceTileViewModel tile)
				tile.EnsureThumbnail();
		}

		private void FaceGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
			=> ViewModel.SetSelection(FaceGrid.SelectedItems.OfType<TeachFaceTileViewModel>());

		private async void SortButton_Click(object sender, RoutedEventArgs e)
			=> await ViewModel.SortAsync();

		private async void ScanFirstButton_Click(object sender, RoutedEventArgs e)
		{
			// Scan the folder this page was opened from, then come back here when it finishes.
			await Ioc.Default.GetRequiredService<ICommandManager>().ScanForPeople.ExecuteAsync();
		}

		private void NameBox_TextChanged(AutoSuggestBox sender, AutoSuggestBoxTextChangedEventArgs args)
		{
			if (args.Reason != AutoSuggestionBoxTextChangeReason.UserInput)
				return;
			var text = sender.Text.Trim();
			sender.ItemsSource = text.Length == 0
				? null
				: ViewModel.PersonNames.Where(n => n.Contains(text, StringComparison.CurrentCultureIgnoreCase)).ToList();
		}

		private async void NameBox_QuerySubmitted(AutoSuggestBox sender, AutoSuggestBoxQuerySubmittedEventArgs args)
			=> await NameAsync(args.ChosenSuggestion as string ?? sender.Text);

		private async void NameList_ItemClick(object sender, ItemClickEventArgs e)
		{
			if (e.ClickedItem is string name)
				await NameAsync(name);
		}

		private async Task NameAsync(string name)
		{
			if (string.IsNullOrWhiteSpace(name))
				return;
			NameFlyout.Hide();
			NameBox.Text = string.Empty;
			await ViewModel.NameSelectedAsync(name);
		}

		private async void RemoveExamplesButton_Click(object sender, RoutedEventArgs e)
			=> await ViewModel.RemoveSelectedExamplesAsync();

		private void ClearSelectionButton_Click(object sender, RoutedEventArgs e)
			=> FaceGrid.SelectedItems.Clear();

		// --- Needs your check -------------------------------------------------------

		private bool syncingReviewSelection;

		private void Review_PropertyChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
		{
			// After a decision the view model moves to the next face; mirror that in the list.
			if (e.PropertyName != nameof(TeachReviewViewModel.Current))
				return;
			PreviewMedia.ResetZoom(true);
			ApplyPersonTint();
			UpdateCopiesButton();
			PlayCurrentVideo();
			if (ReviewList.SelectedItems.Contains(ViewModel.Review.Current))
				return;
			syncingReviewSelection = true;
			ReviewList.SelectedItem = ViewModel.Review.Current;
			if (ViewModel.Review.Current is not null)
				ReviewList.ScrollIntoView(ViewModel.Review.Current);
			syncingReviewSelection = false;
		}

		private void ViewModel_PropertyChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
		{
			if (e.PropertyName == nameof(TeachPageViewModel.CurrentNoFace))
			{
				OnCurrentNoFaceChanged();
				return;
			}
			if (e.PropertyName == nameof(TeachPageViewModel.NoFacesVisibility))
			{
				OnCurrentNoFaceChanged();
				if (!ViewModel.IsShowingNoFaces && !ViewModel.IsPlacingGroups && !ViewModel.IsReviewing && !ViewModel.Viewer.IsOpen)
					SetFocusMode(false);
				return;
			}
			if (e.PropertyName == nameof(TeachPageViewModel.CurrentGroup))
			{
				OnCurrentGroupChanged();
				return;
			}
			if (e.PropertyName == nameof(TeachPageViewModel.GroupsVisibility))
			{
				OnCurrentGroupChanged();
				if (!ViewModel.IsPlacingGroups && !ViewModel.IsShowingNoFaces && !ViewModel.IsReviewing && !ViewModel.Viewer.IsOpen)
					SetFocusMode(false);
				return;
			}
			if (e.PropertyName != nameof(TeachPageViewModel.IsReviewing))
				return;
			if (ViewModel.IsReviewing)
				DispatcherQueue.TryEnqueue(FocusQueue);
			else if (!ViewModel.IsPlacingGroups && !ViewModel.IsShowingNoFaces && !ViewModel.Viewer.IsOpen)
				SetFocusMode(false);
		}

		private void ReviewList_ContainerContentChanging(ListViewBase sender, ContainerContentChangingEventArgs args)
		{
			if (!args.InRecycleQueue && args.Item is TeachReviewItemViewModel item)
				item.EnsureThumbnail();
		}

		private void ReviewList_SelectionChanged(object sender, SelectionChangedEventArgs e)
		{
			if (!syncingReviewSelection)
				ViewModel.Review.Select(ReviewList.SelectedItems.OfType<TeachReviewItemViewModel>().ToList());
		}

		private async void ReviewYes_Click(object sender, RoutedEventArgs e)
		{
			await ViewModel.Review.YesAsync();
			FocusQueue();
		}

		private async void ReviewNo_Click(object sender, RoutedEventArgs e)
		{
			await ViewModel.Review.NoAsync();
			FocusQueue();
		}

		private void ReviewSkip_Click(object sender, RoutedEventArgs e)
		{
			ViewModel.Review.Skip();
			FocusQueue();
		}

		// The "Guests" label row can't be clicked, focused or selected.
		private void FilterList_ContainerContentChanging(ListViewBase sender, ContainerContentChangingEventArgs args)
		{
			var header = args.Item is TeachFilterItem { IsHeader: true };
			args.ItemContainer.IsHitTestVisible = !header;
			args.ItemContainer.IsTabStop = !header;
		}

		private void ReviewElseMenu_Opening(object sender, object e)
		{
			ReviewElseMenu.Items.Clear();
			var candidate = ViewModel.Review.Current?.Match.PersonId;
			var afterMembers = false;
			foreach (var person in ViewModel.ReassignTargets.Where(p => p.PersonId != candidate))
			{
				if (person.IsGuest && !afterMembers && ReviewElseMenu.Items.Count > 0)
					ReviewElseMenu.Items.Add(new MenuFlyoutSeparator());
				afterMembers |= person.IsGuest;
				var item = new MenuFlyoutItem { Text = person.Name };
				var id = person.PersonId!.Value;
				var name = person.Name;
				item.Click += async (_, _) =>
				{
					await ViewModel.Review.SomeoneElseAsync(id, name);
					FocusQueue();
				};
				ReviewElseMenu.Items.Add(item);
			}
			if (ReviewElseMenu.Items.Count > 0)
				ReviewElseMenu.Items.Add(new MenuFlyoutSeparator());
			var someoneNew = new MenuFlyoutItem { Text = Strings.MediaMind_ViewerSomeoneNew.GetLocalizedResource() };
			someoneNew.Click += (_, _) => FlyoutBase.ShowAttachedFlyout(ReviewElseButton);
			ReviewElseMenu.Items.Add(someoneNew);
		}

		private async void ReviewNameBox_QuerySubmitted(AutoSuggestBox sender, AutoSuggestBoxQuerySubmittedEventArgs args)
		{
			var name = args.ChosenSuggestion as string ?? sender.Text;
			ReviewNameFlyout.Hide();
			sender.Text = string.Empty;
			await ViewModel.Review.SomeoneNewAsync(name);
			FocusQueue();
		}

		// A video under review plays by itself (with sound, looping, with VideoBar's controls),
		// streamed from the file rather than loaded whole, so it is never judged from one frame.
		// One player at a time; it is released before a delete, since a playing file can't be deleted.
		private void PlayCurrentVideo()
		{
			StopVideo();
			if (ViewModel.Review.Current is not { IsVideo: true } item)
				return;
			try
			{
				var player = new Windows.Media.Playback.MediaPlayer
				{
					AutoPlay = true,
					IsLoopingEnabled = true,
				};
				var review = ViewModel.Review;
				review.ReportVideo(true);
				player.PlaybackSession.PlaybackStateChanged += (session, _) =>
				{
					var loading = session.PlaybackState is Windows.Media.Playback.MediaPlaybackState.Opening or Windows.Media.Playback.MediaPlaybackState.Buffering;
					DispatcherQueue.TryEnqueue(() => { if (review.Current == item && PreviewMedia.Player == player) review.ReportVideo(loading); });
				};
				player.MediaFailed += (_, _) =>
					DispatcherQueue.TryEnqueue(() =>
					{
						// A replaced player reports a failure as it is disposed; only the live one counts.
						if (review.Current != item || PreviewMedia.Player != player)
							return;
						StopVideo();
						review.ReportVideoFailed();
					});
				player.Source = Windows.Media.Core.MediaSource.CreateFromUri(new Uri(item.Match.AbsPath));
				PreviewMedia.SetPlayer(player);
			}
			// A bad path: show the frame the face came from instead.
			catch (Exception)
			{
				StopVideo();
				ViewModel.Review.ReportVideoFailed();
			}
		}

		private void StopVideo()
		{
			var old = PreviewMedia.Player;
			if (old is null)
				return;
			PreviewMedia.SetPlayer(null);
			old.Pause();
			(old.Source as IDisposable)?.Dispose();
			old.Dispose();
		}

		protected override void OnNavigatedFrom(NavigationEventArgs e)
		{
			StopVideo();
			StopViewerVideo();
			StopGroupVideo();
			StopNoFaceVideo();
			SetFocusMode(false);
			ViewModel?.OnLeaving();
			Utils.MediaMind.SidebarAutoCollapse.Leave();
			base.OnNavigatedFrom(e);
		}

		private async void ReviewOpen_Click(object sender, RoutedEventArgs e)
		{
			if (ViewModel.Review.Current is not { } item)
				return;
			try
			{
				var file = await Windows.Storage.StorageFile.GetFileFromPathAsync(item.Match.AbsPath);
				await Launcher.LaunchFileAsync(file);
			}
			// The drive may be offline; the preview already says so.
			catch (Exception)
			{
			}
		}
	}
}

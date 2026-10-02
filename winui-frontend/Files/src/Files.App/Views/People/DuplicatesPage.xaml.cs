// Copyright (c) Files Community
// Licensed under the MIT License.

using CommunityToolkit.WinUI;
using Files.App.ViewModels.People;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Navigation;
using Microsoft.Extensions.Logging;
using Windows.System;

namespace Files.App.Views.People
{
	// MediaMind: "Duplicates" — one set of copies at a time, side by side; keep one, the rest go.
	// Keyboard-first like Who's who. See DuplicatesPageViewModel.
	public sealed partial class DuplicatesPage : Page
	{
		private const string DeleteWithoutAskingKey = "MediaMind.Duplicates.DeleteWithoutAsking";

		private IShellPage? appInstance;
		private IShellPage AppInstance
			=> appInstance ?? throw new InvalidOperationException("The Duplicates page has not been initialized.");

		public DuplicatesPageViewModel ViewModel { get; private set; } = null!;

		private UIElement? keyRoot;
		private KeyEventHandler? windowKeyDown;

		public DuplicatesPage()
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

			// "duplicates:{libraryId}:{groupId}:{under}" or "duplicates:::{folderPath}" (not a library yet)
			var parts = navPath.Split(':', 4);
			var libraryId = parts.Length > 1 ? parts[1] : string.Empty;
			long? groupId = parts.Length > 2 && long.TryParse(parts[2], out var g) ? g : null;
			var rest = parts.Length > 3 ? parts[3] : string.Empty;
			ViewModel = libraryId.Length > 0
				? new DuplicatesPageViewModel(libraryId, groupId, rest, string.Empty)
				: new DuplicatesPageViewModel(string.Empty, null, string.Empty, rest);
			ViewModel.NavigateToLibrary = id => AppInstance.NavigateToPath($"duplicates:{id}::", typeof(DuplicatesPage));
			ViewModel.PropertyChanged += (_, args) =>
			{
				if (args.PropertyName == nameof(DuplicatesPageViewModel.Current))
					OnCurrentChanged();
				else if (args.PropertyName == nameof(DuplicatesPageViewModel.ShowExact))
					ModeBar.SelectedItem = ViewModel.ShowExact ? ExactModeItem : LookAlikeModeItem;
			};
			ModeBar.SelectedItem = ViewModel.ShowExact ? ExactModeItem : LookAlikeModeItem;
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
				Title = Strings.MediaMind_DupTitle.GetLocalizedResource(),
				Path = navPath,
			});

			Utils.MediaMind.SidebarAutoCollapse.Enter();
			base.OnNavigatedTo(e);
		}

		protected override void OnNavigatedFrom(NavigationEventArgs e)
		{
			if (IsCopyViewerOpen)
				CloseCopyViewer();
			StopPlayers();
			ViewModel?.Detach();
			Utils.MediaMind.SidebarAutoCollapse.Leave();
			base.OnNavigatedFrom(e);
		}

		private bool syncingSelection;

		private void OnCurrentChanged()
		{
			// Another set on screen (a decision, Skip, a click in the list): the viewer closes.
			if (IsCopyViewerOpen)
				CloseCopyViewer();
			// After a decision the view model moves on; mirror that in the list.
			if (ViewModel.Current is { } group && !GroupList.SelectedItems.Contains(group))
			{
				syncingSelection = true;
				GroupList.SelectedItem = group;
				syncingSelection = false;
			}
			if (ViewModel.Current is { } shown)
				GroupList.ScrollIntoView(shown);
			// Room for every copy in one row when they fit; more than four wrap to a second row.
			CopiesLayout.MaximumRowsOrColumns = Math.Clamp(ViewModel.Current?.Members.Count ?? 2, 2, 4);
			CompareScroller.ChangeView(null, 0, null, true);
		}

		// The pictures take the height the answers leave, so each card's details stay in view;
		// below the minimum the copies scroll instead of shrinking away.
		private const double CopyDetailsHeight = 104;
		private const double MinCopyImageHeight = 200;
		private double copyImageHeight = 340;

		private void CompareScroller_SizeChanged(object sender, SizeChangedEventArgs e)
		{
			copyImageHeight = Math.Max(MinCopyImageHeight, e.NewSize.Height - CopyDetailsHeight);
			for (var i = 0; i < (CopiesRepeater.ItemsSourceView?.Count ?? 0); i++)
				SizeCopy(CopiesRepeater.TryGetElement(i));
		}

		private void CopiesRepeater_ElementPrepared(ItemsRepeater sender, ItemsRepeaterElementPreparedEventArgs args)
		{
			SizeCopy(args.Element);
			// Started once the layout settles: cards are prepared and cleared several times
			// on the way, and a player per pass only races itself.
			var card = args.Element;
			DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () =>
			{
				if (CopiesRepeater.GetElementIndex(card) >= 0)
					StartPlayer(card);
			});
		}

		private void SizeCopy(UIElement? card)
		{
			if (card?.FindDescendant("CopyImageArea") is FrameworkElement area)
				area.Height = copyImageHeight;
		}

		// --- Keyboard: on the window, so it works whatever has focus (see TeachPage) ---------

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

		// 1-9 = keep that copy, K = keep it and remove the others, N = not duplicates, S = skip,
		// F = the kept copy full screen.
		private async void Window_KeyDown(object sender, KeyRoutedEventArgs e)
		{
			if (ViewModel is null || appInstance is not { IsCurrentPane: true }
				|| HotKeyHelpers.GetCurrentKeyModifiers() is not KeyModifiers.None
				|| e.OriginalSource is DependencyObject source && source.FindAscendantOrSelf<TextBox>() is not null)
				return;
			if (IsCopyViewerOpen && CopyViewerKey(e.Key))
			{
				e.Handled = true;
				return;
			}
			if (e.Key == VirtualKey.F && ViewModel.Current is { } current)
			{
				e.Handled = true;
				OpenCopyViewer(current.Members.FirstOrDefault(m => m.IsKeeper) ?? current.Members[0]);
				return;
			}

			if (e.Key is >= VirtualKey.Number1 and <= VirtualKey.Number9 or >= VirtualKey.NumberPad1 and <= VirtualKey.NumberPad9)
			{
				e.Handled = true;
				var digit = e.Key >= VirtualKey.NumberPad1 ? e.Key - VirtualKey.NumberPad0 : e.Key - VirtualKey.Number0;
				ViewModel.ChooseKeeper((int)digit);
				return;
			}
			switch (e.Key)
			{
				case VirtualKey.K when ViewModel.CanDecide:
					e.Handled = true;
					await KeepAsync();
					break;
				case VirtualKey.N when ViewModel.CanDecide:
					e.Handled = true;
					await ViewModel.NotDuplicatesAsync();
					break;
				case VirtualKey.S:
					e.Handled = true;
					ViewModel.Skip();
					break;
			}
		}

		private void FocusList()
			=> GroupList.Focus(FocusState.Programmatic);

		// --- Actions ---------------------------------------------------------------------

		private async void FindButton_Click(object sender, RoutedEventArgs e)
			=> await ViewModel.ScanAsync();

		private async void KeepButton_Click(object sender, RoutedEventArgs e)
		{
			await KeepAsync();
			FocusList();
		}

		private async void NotDuplicatesButton_Click(object sender, RoutedEventArgs e)
		{
			await ViewModel.NotDuplicatesAsync();
			FocusList();
		}

		private void SkipButton_Click(object sender, RoutedEventArgs e)
		{
			ViewModel.Skip();
			FocusList();
		}

		private Task KeepAsync()
			=> ViewModel.KeepChosenAsync(async (paths, toBin) =>
			{
				var ok = await Utils.MediaMind.DeleteConfirmation.ConfirmAsync(XamlRoot, paths, toBin, DeleteWithoutAskingKey);
				UpdateAskAgainLink();
				if (ok)
					StopPlayers();
				return ok;
			});

		private void UpdateAskAgainLink()
			=> AskAgainLink.Visibility = Utils.MediaMind.DeleteConfirmation.IsSkipped(DeleteWithoutAskingKey) ? Visibility.Visible : Visibility.Collapsed;

		private void AskAgain_Click(object sender, RoutedEventArgs e)
		{
			Utils.MediaMind.DeleteConfirmation.SetSkipped(DeleteWithoutAskingKey, false);
			UpdateAskAgainLink();
		}

		private void Copy_Tapped(object sender, TappedRoutedEventArgs e)
		{
			if (sender is UIElement card && MemberOf(card) is { } member)
				ViewModel.ChooseKeeper(member.Number);
		}

		private async void Copy_DoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
		{
			if (sender is not UIElement card || MemberOf(card) is not { } member)
				return;
			try
			{
				var file = await Windows.Storage.StorageFile.GetFileFromPathAsync(member.AbsPath);
				await Launcher.LaunchFileAsync(file);
			}
			// The drive may be offline; the card stays as it is.
			catch (Exception)
			{
			}
		}

		private void GroupList_SelectionChanged(object sender, SelectionChangedEventArgs e)
		{
			if (!syncingSelection)
				ViewModel.Select(GroupList.SelectedItems.OfType<DuplicateGroupViewModel>().ToList());
		}

		private void ModeBar_SelectionChanged(SelectorBar sender, SelectorBarSelectionChangedEventArgs args)
			=> ViewModel.ShowExact = sender.SelectedItem == ExactModeItem;

		private void SelectAll_Click(object sender, RoutedEventArgs e)
		{
			GroupList.SelectAll();
			FocusList();
		}

		// --- Video: every copy plays, looping and muted; the one under the pointer has sound ------

		private readonly Dictionary<UIElement, (Windows.Media.Playback.MediaPlayer Player, string Path)> players = [];

		private void StartPlayer(UIElement card)
		{
			if (MemberOf(card) is not { IsVideo: true } member
				|| card.FindDescendant("CopyPlayer") is not MediaPlayerElement element)
				return;
			// Already playing this copy: leave it running rather than restarting it.
			if (players.TryGetValue(card, out var running) && running.Path == member.AbsPath)
				return;
			StopPlayer(card);
			try
			{
				var player = new Windows.Media.Playback.MediaPlayer { AutoPlay = true, IsLoopingEnabled = true, IsMuted = true };
				// A format Windows can't decode (e.g. 10-bit H.264): the still frame stays instead.
				// A player that was already replaced (cards are re-prepared while the layout settles)
				// reports a failure as it is disposed; only the card's current player counts.
				player.MediaFailed += (_, args) => DispatcherQueue.TryEnqueue(() =>
				{
					if (!players.TryGetValue(card, out var live) || live.Player != player)
						return;
					element.Visibility = Visibility.Collapsed;
					Ioc.Default.GetRequiredService<Microsoft.Extensions.Logging.ILogger<App>>()
						.LogWarning("Duplicates: a video copy can't play here ({Error}); showing its still frame", args.Error);
				});
				player.Source = Windows.Media.Core.MediaSource.CreateFromUri(new Uri(member.AbsPath));
				element.SetMediaPlayer(player);
				element.Visibility = Visibility.Visible;
				players[card] = (player, member.AbsPath);
			}
			catch (Exception)
			{
				element.Visibility = Visibility.Collapsed;
			}
		}

		// Which copy a card shows. Asked of the repeater by position: while a card is being
		// prepared its DataContext is still the page's, so it can't be read from the card.
		private DuplicateMemberViewModel? MemberOf(UIElement card)
		{
			var index = CopiesRepeater.GetElementIndex(card);
			return index >= 0 && index < (CopiesRepeater.ItemsSourceView?.Count ?? 0)
				? CopiesRepeater.ItemsSourceView!.GetAt(index) as DuplicateMemberViewModel
				: null;
		}

		private void StopPlayer(UIElement card)
		{
			if (!players.Remove(card, out var entry))
				return;
			var player = entry.Player;
			if (card.FindDescendant("CopyPlayer") is MediaPlayerElement element)
			{
				element.SetMediaPlayer(null);
				element.Visibility = Visibility.Collapsed;
			}
			player.Pause();
			(player.Source as IDisposable)?.Dispose();
			player.Dispose();
		}

		// Before files are removed: a file that is playing can't be deleted.
		private void StopPlayers()
		{
			foreach (var card in players.Keys.ToList())
				StopPlayer(card);
		}

		private void CopiesRepeater_ElementClearing(ItemsRepeater sender, ItemsRepeaterElementClearingEventArgs args)
			=> StopPlayer(args.Element);

		private void Copy_PointerEntered(object sender, PointerRoutedEventArgs e)
		{
			if (sender is UIElement card && players.TryGetValue(card, out var entry))
				entry.Player.IsMuted = false;
		}

		private void Copy_PointerExited(object sender, PointerRoutedEventArgs e)
		{
			if (sender is UIElement card && players.TryGetValue(card, out var entry))
				entry.Player.IsMuted = true;
		}

		private void GroupList_ContainerContentChanging(ListViewBase sender, ContainerContentChangingEventArgs args)
		{
			if (!args.InRecycleQueue && args.Item is DuplicateGroupViewModel group)
				group.EnsureThumbnail();
		}
	}
}

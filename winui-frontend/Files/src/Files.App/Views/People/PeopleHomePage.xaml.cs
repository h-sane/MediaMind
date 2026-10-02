// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.ViewModels.People;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Navigation;
using Windows.ApplicationModel.DataTransfer;
using Windows.System;

namespace Files.App.Views.People
{
	// MediaMind: content page the People sidebar header navigates to — every scanned
	// library at once, as a Faces grid or a Folders tree, with pins and collections
	// (docs/PEOPLE_VIEW_V2_DESIGN.md). Always opens, even with nothing scanned yet.
	public sealed partial class PeopleHomePage : Page
	{
		private IShellPage? appInstance;
		private IShellPage AppInstance
			=> appInstance ?? throw new InvalidOperationException("The People home page has not been initialized.");

		public PeopleHomePageViewModel ViewModel { get; } = new();

		public PeopleHomePage()
		{
			InitializeComponent();
		}

		protected override async void OnNavigatedTo(NavigationEventArgs e)
		{
			if (e.Parameter is NavigationArguments parameters)
				appInstance = parameters.AssociatedTabInstance;

			if (appInstance is not null)
			{
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
				AppInstance.ToolbarViewModel.CanRefresh = false;
				AppInstance.ToolbarViewModel.CanGoBack = AppInstance.CanNavigateBackward;
				AppInstance.ToolbarViewModel.CanGoForward = AppInstance.CanNavigateForward;
				AppInstance.ToolbarViewModel.CanNavigateToParent = false;

				await shellViewModel.SetWorkingDirectoryAsync("Home");

				AppInstance.ToolbarViewModel.PathComponents.Clear();
				AppInstance.ToolbarViewModel.PathComponents.Add(new PathBoxItem()
				{
					Title = Strings.People.GetLocalizedResource(),
					Path = "People",
				});
			}

			base.OnNavigatedTo(e);
		}

		protected override void OnNavigatedFrom(NavigationEventArgs e)
		{
			ViewModel.Dispose();
			base.OnNavigatedFrom(e);
		}

		private static object? TagOf(object sender)
			=> (sender as FrameworkElement)?.Tag;

		private static string Loc(string key)
			=> key.GetLocalizedResource();

		// ---- open ---------------------------------------------------------------

		private void PersonTile_DoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
		{
			// A double-click on the card's own buttons or name box is not "open".
			if (IsInsideInteractiveControl(e.OriginalSource as DependencyObject, sender as DependencyObject))
				return;

			if (TagOf(sender) is PeopleTileViewModel tile)
				ViewModel.OpenDetail(tile);
		}

		private static bool IsInsideInteractiveControl(DependencyObject? node, DependencyObject? stopAt)
		{
			for (; node is not null && node != stopAt; node = VisualTreeHelper.GetParent(node))
				if (node is ButtonBase or TextBox)
					return true;

			return false;
		}

		private void Card_DoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
		{
			if (TagOf(sender) is FolderCardViewModel { Node: not null } card)
				ViewModel.OpenNode(card.Node.Id);
		}

		private void Breadcrumb_Click(object sender, RoutedEventArgs e)
		{
			if (TagOf(sender) is BreadcrumbItemViewModel crumb)
				ViewModel.NavigateTo(crumb.NodeId);
		}

		private void CollectionChip_Click(object sender, RoutedEventArgs e)
		{
			if (TagOf(sender) is CollectionChipViewModel chip)
				ViewModel.OpenCollection(chip.Id);
		}

		// ---- person pop-up ------------------------------------------------------

		private void DetailScrim_Tapped(object sender, TappedRoutedEventArgs e)
			=> ViewModel.CloseDetail();

		private void DetailCard_Tapped(object sender, TappedRoutedEventArgs e)
			=> e.Handled = true;

		private void DetailClose_Click(object sender, RoutedEventArgs e)
			=> ViewModel.CloseDetail();

		private void DetailEscape_Invoked(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
		{
			args.Handled = true;
			ViewModel.CloseDetail();
		}

		// The full person view opens beside the People page, which stays as it is.
		private async void DetailOpenInTab_Click(object sender, RoutedEventArgs e)
		{
			if (ViewModel.Detail is not { } detail)
				return;

			ViewModel.CloseDetail();
			await NavigationHelpers.OpenPathInNewTab(detail.Path, true);
		}

		private async void DetailNameBox_KeyDown(object sender, KeyRoutedEventArgs e)
		{
			if (e.Key == VirtualKey.Enter)
			{
				e.Handled = true;
				await CommitDetailNameAsync();
			}
		}

		private async void DetailNameBox_LostFocus(object sender, RoutedEventArgs e)
			=> await CommitDetailNameAsync();

		private async Task CommitDetailNameAsync()
		{
			if (ViewModel.Detail is { } detail && await detail.RenameAsync(DetailNameBox.Text))
				await ViewModel.RefreshAsync();
		}

		private async void MediaThumb_DoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
		{
			if (TagOf(sender) is not PersonMediaThumbViewModel thumb)
				return;

			try
			{
				var file = await Windows.Storage.StorageFile.GetFileFromPathAsync(thumb.AbsPath);
				await Launcher.LaunchFileAsync(file);
			}
			// The photo may have been moved or deleted since the scan.
			catch (Exception)
			{
			}
		}

		// ---- remove / merge / restore -------------------------------------------

		private async void RemoveButton_Click(object sender, RoutedEventArgs e)
		{
			if (TagOf(sender) is PeopleTileViewModel tile)
				await ViewModel.HideAsync(tile);
		}

		private async void MergeButton_Click(object sender, RoutedEventArgs e)
		{
			if (TagOf(sender) is not PeopleTileViewModel source)
				return;

			var box = new AutoSuggestBox { PlaceholderText = Loc("MediaMind_PeopleMergeName"), MinWidth = 300 };
			var error = new TextBlock
			{
				Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["SystemFillColorCriticalBrush"],
				TextWrapping = TextWrapping.Wrap,
				Visibility = Visibility.Collapsed,
			};
			box.TextChanged += (s, args) =>
			{
				error.Visibility = Visibility.Collapsed;
				if (args.Reason == AutoSuggestionBoxTextChangeReason.UserInput)
					s.ItemsSource = ViewModel.MergeNameChoices(source, s.Text).ToList();
			};

			PeopleTileViewModel? target = null;
			var dialog = new ContentDialog
			{
				XamlRoot = XamlRoot,
				Title = $"{Loc("MediaMind_PeopleMergeTitle")}…",
				Content = new StackPanel { Spacing = 8, Children = { FaceColumn(source), box, error } },
				PrimaryButtonText = Loc("MediaMind_PeopleMerge"),
				CloseButtonText = Loc("Cancel"),
				DefaultButton = ContentDialogButton.Primary,
			};
			dialog.PrimaryButtonClick += (_, args) =>
			{
				target = ViewModel.FindMergeTarget(source, box.Text);
				if (target is null)
				{
					args.Cancel = true;
					error.Text = string.Format(Loc("MediaMind_PeopleMergeNoMatch"), box.Text.Trim());
					error.Visibility = Visibility.Visible;
				}
			};

			if (await dialog.ShowAsync() == ContentDialogResult.Primary && target is not null)
				await ViewModel.MergeAsync(source, target);
		}

		private async void HiddenButton_Click(object sender, RoutedEventArgs e)
		{
			var list = new StackPanel { Spacing = 8, MinWidth = 320 };
			var dialog = new ContentDialog
			{
				XamlRoot = XamlRoot,
				Title = Loc("MediaMind_PeopleHiddenTitle"),
				Content = new ScrollViewer { MaxHeight = 420, Content = list },
				CloseButtonText = Loc("Close"),
			};

			foreach (var tile in ViewModel.HiddenPeople.ToList())
			{
				var row = new Grid { ColumnSpacing = 12 };
				row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
				row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
				row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

				var picture = TilePicture(tile, 40);
				var label = new TextBlock { Text = $"{tile.Text}  ·  {tile.MediaCount}", VerticalAlignment = VerticalAlignment.Center };
				var restore = new Button { Content = Loc("MediaMind_PeopleRestore") };
				restore.Click += async (_, _) =>
				{
					restore.IsEnabled = false;
					list.Children.Remove(row);
					await ViewModel.UnhideAsync(tile);
					if (list.Children.Count == 0)
						dialog.Hide();
				};

				Grid.SetColumn(label, 1);
				Grid.SetColumn(restore, 2);
				row.Children.Add(picture);
				row.Children.Add(label);
				row.Children.Add(restore);
				list.Children.Add(row);
			}

			await dialog.ShowAsync();
		}

		// ---- pin ----------------------------------------------------------------

		private void Tile_PointerEntered(object sender, PointerRoutedEventArgs e)
			=> SetHover(sender, true);

		private void Tile_PointerExited(object sender, PointerRoutedEventArgs e)
			=> SetHover(sender, false);

		private static void SetHover(object sender, bool hovered)
		{
			switch (TagOf(sender))
			{
				case PeopleTileViewModel tile:
					tile.IsHovered = hovered;
					break;
				case FolderCardViewModel card:
					card.IsHovered = hovered;
					break;
			}
		}

		private async void PinButton_Click(object sender, RoutedEventArgs e)
		{
			switch (TagOf(sender))
			{
				case PeopleTileViewModel tile:
					await ViewModel.TogglePinAsync(tile);
					break;
				case FolderCardViewModel card:
					await ViewModel.TogglePinAsync(card);
					break;
			}
		}

		// ---- context menus ------------------------------------------------------

		private void PersonTile_ContextRequested(UIElement sender, ContextRequestedEventArgs e)
		{
			if (TagOf(sender) is not PeopleTileViewModel tile)
				return;

			var flyout = new MenuFlyout();
			flyout.Items.Add(PinItem(tile.IsPinned, () => ViewModel.TogglePinAsync(tile)));
			AddCollectionItems(flyout, tile.Keys, tile.Entry.CollectionId is not null);
			ShowFlyout(flyout, sender, e);
		}

		private void Card_ContextRequested(UIElement sender, ContextRequestedEventArgs e)
		{
			if (TagOf(sender) is not FolderCardViewModel card)
				return;

			var flyout = new MenuFlyout();
			flyout.Items.Add(PinItem(card.IsPinned, () => ViewModel.TogglePinAsync(card)));

			if (card is { IsCollection: true, Node: not null })
				AddCollectionManageItems(flyout, card.Node.Id, card.Node.Name);
			else if (card.Available)
				AddCollectionItems(flyout, [card.Key], ViewModel.ViewingCollection);

			ShowFlyout(flyout, sender, e);
		}

		private void CollectionChip_ContextRequested(UIElement sender, ContextRequestedEventArgs e)
		{
			if (TagOf(sender) is not CollectionChipViewModel chip)
				return;

			var flyout = new MenuFlyout();
			AddCollectionManageItems(flyout, chip.Id, chip.Name);
			ShowFlyout(flyout, sender, e);
		}

		private static MenuFlyoutItem PinItem(bool isPinned, Func<Task> toggle)
		{
			var item = new MenuFlyoutItem { Text = Loc(isPinned ? "MediaMind_PeopleUnpin" : "MediaMind_PeoplePin") };
			item.Click += async (_, _) => await toggle();
			return item;
		}

		private void AddCollectionItems(MenuFlyout flyout, IReadOnlyList<string> keys, bool canRemove)
		{
			var move = new MenuFlyoutSubItem
			{
				Text = Loc("MediaMind_PeopleMoveToCollection"),
				IsEnabled = ViewModel.Collections.Count > 0,
			};
			foreach (var collection in ViewModel.Collections)
			{
				var id = collection.Id;
				var item = new MenuFlyoutItem { Text = collection.Name };
				item.Click += async (_, _) => await ViewModel.MoveToCollectionAsync(id, keys);
				move.Items.Add(item);
			}

			flyout.Items.Add(move);

			if (canRemove)
			{
				var remove = new MenuFlyoutItem { Text = Loc("MediaMind_PeopleRemoveFromCollection") };
				remove.Click += async (_, _) => await ViewModel.RemoveFromCollectionAsync(keys);
				flyout.Items.Add(remove);
			}
		}

		private void AddCollectionManageItems(MenuFlyout flyout, string collectionId, string name)
		{
			var rename = new MenuFlyoutItem { Text = Loc("Rename") };
			rename.Click += async (_, _) =>
			{
				var newName = await PromptNameAsync(Loc("Rename"), Loc("Rename"), name);
				if (newName is not null)
					await ViewModel.RenameCollectionAsync(collectionId, newName);
			};
			flyout.Items.Add(rename);

			var delete = new MenuFlyoutItem { Text = Loc("Delete") };
			delete.Click += async (_, _) => await ViewModel.DeleteCollectionAsync(collectionId);
			flyout.Items.Add(delete);
		}

		private static void ShowFlyout(MenuFlyout flyout, UIElement sender, ContextRequestedEventArgs e)
		{
			e.Handled = true;
			if (e.TryGetPosition(sender, out var point))
				flyout.ShowAt(sender, new FlyoutShowOptions { Position = point });
			else
				flyout.ShowAt((FrameworkElement)sender);
		}

		// ---- collections: create, drag and drop ---------------------------------

		private async void NewCollection_Click(object sender, RoutedEventArgs e)
		{
			var name = await PromptNameAsync(Loc("MediaMind_PeopleNewCollection"), Loc("Create"));
			if (name is not null)
				await ViewModel.CreateCollectionAsync(name);
		}

		private async Task<string?> PromptNameAsync(string title, string primaryText, string initial = "")
		{
			var box = new TextBox
			{
				PlaceholderText = Loc("MediaMind_PeopleCollectionName"),
				Text = initial,
			};
			var dialog = new ContentDialog
			{
				XamlRoot = XamlRoot,
				Title = title,
				Content = box,
				PrimaryButtonText = primaryText,
				CloseButtonText = Loc("Cancel"),
				DefaultButton = ContentDialogButton.Primary,
			};

			var result = await dialog.ShowAsync();
			return result == ContentDialogResult.Primary && !string.IsNullOrWhiteSpace(box.Text) ? box.Text.Trim() : null;
		}

		private void PersonTile_DragStarting(UIElement sender, DragStartingEventArgs args)
		{
			if (TagOf(sender) is not PeopleTileViewModel tile)
			{
				args.Cancel = true;
				return;
			}

			PeopleDragPayload.Keys = tile.Keys;
			PeopleDragPayload.Label = tile.Text;
			args.Data.SetText(tile.Text);
			args.Data.RequestedOperation = DataPackageOperation.Move;
		}

		// A folder card can be dragged into a collection; a collection card cannot be dragged.
		private void Card_DragStarting(UIElement sender, DragStartingEventArgs args)
		{
			if (TagOf(sender) is not FolderCardViewModel { IsCollection: false, Available: true } card)
			{
				args.Cancel = true;
				return;
			}

			PeopleDragPayload.Keys = [card.Key];
			PeopleDragPayload.Label = card.Text;
			args.Data.SetText(card.Text);
			args.Data.RequestedOperation = DataPackageOperation.Move;
		}

		private static (string Id, string Name)? CollectionTarget(object sender)
			=> TagOf(sender) switch
			{
				CollectionChipViewModel chip => (chip.Id, chip.Name),
				FolderCardViewModel { IsCollection: true, Node: not null } card => (card.Node.Id, card.Text),
				_ => null,
			};

		private void Collection_DragOver(object sender, DragEventArgs e)
		{
			if (PeopleDragPayload.Keys is null || CollectionTarget(sender) is not { } target)
				return;

			e.AcceptedOperation = DataPackageOperation.Move;
			e.DragUIOverride.Caption = $"{Loc("MediaMind_PeopleMoveToCollection")}: {target.Name}";
			e.Handled = true;
		}

		private async void Collection_Drop(object sender, DragEventArgs e)
		{
			var keys = PeopleDragPayload.Keys;
			PeopleDragPayload.Keys = null;
			e.Handled = true;

			if (keys is null || CollectionTarget(sender) is not { } target)
				return;

			await ViewModel.MoveToCollectionAsync(target.Id, keys);
		}

		// ---- possible duplicates ------------------------------------------------

		private async void DuplicateBadge_Click(object sender, RoutedEventArgs e)
		{
			if (TagOf(sender) is not PeopleTileViewModel tile || ViewModel.DuplicateCounterpart(tile) is not { } other)
				return;

			var content = new StackPanel
			{
				Orientation = Orientation.Horizontal,
				Spacing = 32,
				HorizontalAlignment = HorizontalAlignment.Center,
			};
			content.Children.Add(FaceColumn(tile));
			content.Children.Add(FaceColumn(other));

			var dialog = new ContentDialog
			{
				XamlRoot = XamlRoot,
				Title = Loc("MediaMind_PeopleDuplicateDialogTitle"),
				Content = content,
				PrimaryButtonText = Loc("MediaMind_PeopleLinkSame"),
				SecondaryButtonText = Loc("MediaMind_PeopleLinkDifferent"),
				CloseButtonText = Loc("Cancel"),
				DefaultButton = ContentDialogButton.Close,
			};

			switch (await dialog.ShowAsync())
			{
				case ContentDialogResult.Primary:
					await ViewModel.LinkDuplicateAsync(tile, same: true);
					break;
				case ContentDialogResult.Secondary:
					await ViewModel.LinkDuplicateAsync(tile, same: false);
					break;
			}
		}

		private static PersonPicture TilePicture(PeopleTileViewModel tile, double size)
		{
			var picture = new PersonPicture
			{
				Width = size,
				Height = size,
				DisplayName = tile.Text,
				ProfilePicture = tile.Thumbnail,
			};
			// The thumbnail arrives asynchronously after the dialog is already up.
			tile.PropertyChanged += (_, args) =>
			{
				if (args.PropertyName == nameof(PeopleTileViewModel.Thumbnail))
					picture.ProfilePicture = tile.Thumbnail;
			};
			return picture;
		}

		private static StackPanel FaceColumn(PeopleTileViewModel tile)
		{
			var picture = TilePicture(tile, 112);
			var column = new StackPanel { Spacing = 8, HorizontalAlignment = HorizontalAlignment.Center };
			column.Children.Add(picture);
			column.Children.Add(new TextBlock
			{
				Text = tile.Text,
				FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
				HorizontalAlignment = HorizontalAlignment.Center,
			});
			return column;
		}

		// ---- inline naming ------------------------------------------------------

		private async void PersonNameTextBox_KeyDown(object sender, KeyRoutedEventArgs e)
		{
			if (e.Key != VirtualKey.Enter)
				return;

			e.Handled = true;
			if (sender is TextBox { Tag: PeopleTileViewModel tile } textBox)
				await ViewModel.NamedAsync(tile, textBox.Text);
		}

		private async void PersonNameTextBox_LostFocus(object sender, RoutedEventArgs e)
		{
			if (sender is TextBox { Tag: PeopleTileViewModel tile } textBox)
				await ViewModel.NamedAsync(tile, textBox.Text);
		}

		private async void PersonNameConfirmButton_Click(object sender, RoutedEventArgs e)
		{
			if (sender is not Button { Tag: PeopleTileViewModel tile } button)
				return;

			if ((button.Parent as Grid)?.Children.OfType<TextBox>().FirstOrDefault() is TextBox textBox)
				await ViewModel.NamedAsync(tile, textBox.Text);
		}
	}
}

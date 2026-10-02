// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Items.MediaMind;
using Files.App.ViewModels.People;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Navigation;
using Windows.System;

namespace Files.App.Views.People
{
	// MediaMind: content page for a People Group (ADR-0007) — a tile grid of
	// child Groups + Persons only, never media. Navigated the same generic way
	// BaseLayoutPage subclasses are (ItemDisplayFrame.Navigate + NavigationArguments),
	// but is not itself a BaseLayoutPage since a Group's contents aren't file-shaped.
	public sealed partial class PeopleGroupPage : Page
	{
		private IShellPage? appInstance;
		private IShellPage AppInstance
			=> appInstance ?? throw new InvalidOperationException("The People group page has not been initialized.");

		public PeopleGroupPageViewModel? ViewModel { get; private set; }

		public PeopleGroupPage()
		{
			InitializeComponent();
		}

		protected override async void OnNavigatedTo(NavigationEventArgs e)
		{
			if (e.Parameter is not NavigationArguments parameters || parameters.NavPathParam is not string navPath)
				return;

			appInstance = parameters.AssociatedTabInstance!;

			// "group:{libraryId}:{groupPath}"
			var parts = navPath.Split(':', 3);
			var group = parts.Length == 3 ? App.PeopleManager.FindGroup(parts[1], parts[2]) : null;

			ViewModel = group is not null ? new PeopleGroupPageViewModel(group) : null;
			Bindings.Update();

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
				Title = group?.Text ?? Strings.People.GetLocalizedResource(),
				Path = navPath,
			});

			base.OnNavigatedTo(e);
		}

		protected override void OnNavigatedFrom(NavigationEventArgs e)
		{
			ViewModel?.Dispose();
			base.OnNavigatedFrom(e);
		}

		private void GroupTile_DoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
		{
			if ((sender as FrameworkElement)?.Tag is PeopleGroupItem group)
				_ = NavigationHelpers.OpenPath(group.Path, AppInstance);
		}

		private void PersonTile_DoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
		{
			if ((sender as FrameworkElement)?.Tag is PersonItem person && person.Path is not null)
				_ = NavigationHelpers.OpenPath(person.Path, AppInstance);
		}

		private async void PersonNameTextBox_KeyDown(object sender, KeyRoutedEventArgs e)
		{
			if (e.Key != VirtualKey.Enter)
				return;

			e.Handled = true;
			if (sender is TextBox { Tag: PersonTileViewModel vm } textBox)
				await vm.NameAsync(textBox.Text);
		}

		private async void PersonNameTextBox_LostFocus(object sender, RoutedEventArgs e)
		{
			if (sender is TextBox { Tag: PersonTileViewModel vm } textBox)
				await vm.NameAsync(textBox.Text);
		}

		private async void PersonNameConfirmButton_Click(object sender, RoutedEventArgs e)
		{
			if (sender is not Button { Tag: PersonTileViewModel vm } button)
				return;

			if ((button.Parent as Grid)?.Children.OfType<TextBox>().FirstOrDefault() is TextBox textBox)
				await vm.NameAsync(textBox.Text);
		}
	}
}

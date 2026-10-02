// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.ViewModels.People;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

namespace Files.App.Views.People
{
	// MediaMind: bulk-review gallery for one person's pending face matches
	// (ADR "Suggestions" redesign) — opened from a SuggestionsPane card into the
	// main content frame, never a dialog, since deciding "is this the same
	// person?" needs to see every uncertain photo at once.
	public sealed partial class PendingReviewPage : Page
	{
		private IShellPage? appInstance;
		private IShellPage AppInstance
			=> appInstance ?? throw new InvalidOperationException("The pending review page has not been initialized.");

		public PendingReviewPageViewModel? ViewModel { get; private set; }

		public PendingReviewPage()
		{
			InitializeComponent();
		}

		protected override async void OnNavigatedTo(NavigationEventArgs e)
		{
			if (e.Parameter is not NavigationArguments parameters || parameters.NavPathParam is not string navPath)
				return;

			appInstance = parameters.AssociatedTabInstance!;

			// "pending:{libraryId}:{personId}"
			var parts = navPath.Split(':', 3);
			ViewModel = parts.Length == 3 && long.TryParse(parts[2], out var personId)
				? new PendingReviewPageViewModel(parts[1], personId)
				: null;
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
				Title = Strings.MediaMind_ReviewMatches.GetLocalizedResource(),
				Path = navPath,
			});

			Utils.MediaMind.SidebarAutoCollapse.Enter();
			base.OnNavigatedTo(e);
		}

		protected override void OnNavigatedFrom(NavigationEventArgs e)
		{
			Utils.MediaMind.SidebarAutoCollapse.Leave();
			base.OnNavigatedFrom(e);
		}

		private void SelectAllCheckBox_Checked(object sender, RoutedEventArgs e) => ViewModel?.SelectAll(true);

		private void SelectAllCheckBox_Unchecked(object sender, RoutedEventArgs e) => ViewModel?.SelectAll(false);

		private async void ConfirmSelectedButton_Click(object sender, RoutedEventArgs e)
		{
			if (ViewModel is not null)
				await ViewModel.CommitSelectedAsync("confirmed");
		}

		private async void RejectSelectedButton_Click(object sender, RoutedEventArgs e)
		{
			if (ViewModel is not null)
				await ViewModel.CommitSelectedAsync("rejected");
		}
	}
}

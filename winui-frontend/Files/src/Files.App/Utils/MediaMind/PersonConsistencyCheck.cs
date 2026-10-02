// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Items.MediaMind;
using Files.App.Dialogs;
using Files.App.ViewModels.UserControls.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Files.App.Utils.MediaMind
{
	// MediaMind Phase 4 part 2 (BLOCK5_UI_BLUEPRINT.md §3 feature 6, ADR-0010):
	// on-demand "Check for misfiled photos" on a Person. Ranks this person's
	// binding outliers by named-other-person match (SuggestionsViewModel.
	// CheckPersonConsistencyAsync) and drops them into the Suggestions pane as
	// Consistency cards. Advisory only — nothing moves until a card is acted on.
	// Launched from the Person sidebar context menu (SidebarViewModel), same as
	// PersonConsolidation.
	internal static class PersonConsistencyCheck
	{
		public static async Task RunAsync(PersonItem? item)
		{
			if (item is null)
				return;

			var suggestions = Ioc.Default.GetRequiredService<SuggestionsViewModel>();
			var found = await suggestions.CheckPersonConsistencyAsync(item.Person.Id, item.LibraryId);

			if (found == 0)
			{
				await ShowInfoAsync(
					Strings.MediaMind_CheckConsistency.GetLocalizedResource(),
					Strings.MediaMind_NoOutliersFound.GetLocalizedResource());
			}
		}

		private static Task ShowInfoAsync(string title, string message)
		{
			var dialog = new DynamicDialog(new DynamicDialogViewModel
			{
				TitleText = title,
				DisplayControl = new Grid
				{
					MinWidth = 320d,
					Children = { new TextBlock { Text = message, TextWrapping = TextWrapping.WrapWholeWords } },
				},
				CloseButtonText = Strings.OK.GetLocalizedResource(),
				DynamicButtons = DynamicDialogButtons.Cancel,
			});

			return dialog.TryShowAsync();
		}
	}
}

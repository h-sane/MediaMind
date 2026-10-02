// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Data.Items.MediaMind;
using Files.App.Dialogs;
using Microsoft.UI.Xaml.Controls;

namespace Files.App.Utils.MediaMind
{
	// MediaMind: "Rename person" on the Person sidebar context menu — the same
	// action as the Settings People page's PeopleViewModel.EditExistingPersonAsync,
	// exposed at the point of use instead of requiring a trip to Settings.
	internal static class PersonRename
	{
		public static async Task RunAsync(PersonItem? item)
		{
			if (item is null)
				return;

			var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
			if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is not { } api)
				return;

			var inputText = new TextBox
			{
				PlaceholderText = Strings.MediaMind_PersonNamePlaceholder.GetLocalizedResource(),
				Text = item.Person.Name ?? string.Empty,
			};
			DynamicDialog dialog = null!;
			inputText.TextChanged += (_, _) =>
			{
				var valid = !string.IsNullOrWhiteSpace(inputText.Text);
				dialog.ViewModel.DynamicButtonsEnabled = valid
					? DynamicDialogButtons.Primary | DynamicDialogButtons.Cancel
					: DynamicDialogButtons.Cancel;
				if (valid)
					dialog.ViewModel.AdditionalData = inputText.Text.Trim();
			};

			dialog = new DynamicDialog(new DynamicDialogViewModel
			{
				TitleText = Strings.MediaMind_RenamePerson.GetLocalizedResource(),
				DisplayControl = new Grid { MinWidth = 300d, Children = { inputText } },
				PrimaryButtonAction = (vm, _) => vm.Hide(),
				PrimaryButtonText = Strings.Confirm.GetLocalizedResource(),
				CloseButtonText = Strings.Cancel.GetLocalizedResource(),
				DynamicButtonsEnabled = DynamicDialogButtons.Primary | DynamicDialogButtons.Cancel,
				DynamicButtons = DynamicDialogButtons.Primary | DynamicDialogButtons.Cancel,
			});

			await dialog.TryShowAsync();

			if (dialog.DynamicResult is not DynamicDialogResult.Primary || dialog.ViewModel.AdditionalData is not string name)
				return;

			await api.Persons.RenameAsync(item.LibraryId, item.Person.Id, name);
			item.UpdateFrom(item.Person with { Name = name });

			_ = App.PeopleManager.RefreshAsync();
		}
	}
}

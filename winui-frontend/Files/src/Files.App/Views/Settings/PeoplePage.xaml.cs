// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.ViewModels.Settings;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Windows.System;

namespace Files.App.Views.Settings
{
	// MediaMind: rename/merge management for Persons, modeled on TagsPage's
	// inline-edit-swap pattern (Edit/Save/Cancel buttons toggling a TextBox), plus
	// a merge flyout with no TagsPage precedent — a plain target-picker ListView.
	public sealed partial class PeoplePage : Page
	{
		public PeoplePage()
		{
			InitializeComponent();
		}

		private ListedPersonViewModel? FindGroupSource(FrameworkElement sender)
			=> sender.Tag as ListedPersonViewModel;

		private void EditPerson_Click(object sender, RoutedEventArgs e)
		{
			if (FindGroupSource((FrameworkElement)sender) is not ListedPersonViewModel person)
				return;

			person.NewName = person.DisplayName;
			person.IsEditing = true;
		}

		private void CommitRename_Click(object sender, RoutedEventArgs e)
			=> Commit(FindGroupSource((FrameworkElement)sender));

		private void CancelRename_Click(object sender, RoutedEventArgs e)
		{
			if (FindGroupSource((FrameworkElement)sender) is ListedPersonViewModel person)
				person.IsEditing = false;
		}

		private void RenameTextBox_KeyDown(object sender, KeyRoutedEventArgs e)
		{
			if (e.Key != VirtualKey.Enter)
				return;

			Commit(FindGroupSource((FrameworkElement)sender));
			e.Handled = true;
		}

		private void Commit(ListedPersonViewModel? person)
		{
			if (person is null)
				return;

			person.IsEditing = false;
			var newName = person.NewName?.Trim();
			if (!string.IsNullOrEmpty(newName) && newName != person.DisplayName)
				_ = ViewModel.EditExistingPersonAsync(person, newName);
		}

		private void MergeFlyout_Opening(object? sender, object e)
		{
			if (sender is not Flyout { Target: Button { Tag: ListedPersonViewModel source } } flyout ||
				flyout.Content is not ListView list)
				return;

			var group = ViewModel.Libraries.FirstOrDefault(g => g.People.Contains(source));
			list.ItemsSource = group?.People.Where(p => p != source).ToList() ?? [];
			list.Tag = new MergeContext(flyout, group, source);
		}

		private void MergeTargetList_ItemClick(object sender, ItemClickEventArgs e)
		{
			if (sender is not ListView { Tag: MergeContext context } ||
				e.ClickedItem is not ListedPersonViewModel target ||
				context.Group is null)
				return;

			_ = ViewModel.MergePersonsAsync(context.Group, context.Source, target);
			context.Flyout.Hide();
		}

		private sealed record MergeContext(Flyout Flyout, PeopleLibraryGroupViewModel? Group, ListedPersonViewModel Source);
	}
}

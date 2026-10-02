// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.ViewModels.UserControls.MediaMind;
using Microsoft.UI.Xaml.Controls;

namespace Files.App.UserControls.MediaMind
{
	// MediaMind: pick one person of a library (tagging a not-scanned file by hand).
	public sealed partial class PersonChooser : UserControl
	{
		private List<PersonChoiceViewModel> all = [];

		public PersonChoiceViewModel? Selected => PeopleList.SelectedItem as PersonChoiceViewModel;

		// Raised when the selection changes, so the dialog can enable its Tag button.
		public event Action? SelectionChanged;

		public PersonChooser()
		{
			InitializeComponent();
		}

		public void SetPeople(List<PersonChoiceViewModel> people)
		{
			all = people;
			PeopleList.ItemsSource = all;
		}

		private void SearchBox_TextChanged(object sender, TextChangedEventArgs e)
		{
			var query = SearchBox.Text.Trim();
			PeopleList.ItemsSource = query.Length == 0
				? all
				: all.Where(p => p.Text.Contains(query, StringComparison.CurrentCultureIgnoreCase)).ToList();
		}

		private void PeopleList_SelectionChanged(object sender, SelectionChangedEventArgs e)
			=> SelectionChanged?.Invoke();
	}
}

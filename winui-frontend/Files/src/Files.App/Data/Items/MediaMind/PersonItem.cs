// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Controls;
using Files.App.Services.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Files.App.Data.Items.MediaMind
{
	// MediaMind: sidebar leaf for a Person (ADR-0007). Modeled on FileTagItem — a
	// virtual projection, not a real filesystem location. Path is the "person:"
	// pseudo-path intercepted in NavigationHelpers/BaseShellPage/ModernShellPage.
	public sealed partial class PersonItem : ObservableObject, INavigationControlItem
	{
		public string LibraryId { get; }

		public Person Person { get; private set; }

		public string? Text { get; private set; }

		public string? Path { get; }

		public SectionType Section { get; set; } = SectionType.People;

		public ContextMenuOptions? MenuOptions { get; set; } = new() { IsLocationItem = true };

		public NavigationControlItemType ItemType => NavigationControlItemType.Person;

		public object? Children => null;

		public bool IsExpanded { get => false; set { } }

		public object? ToolTip => Text;

		public IconElement? IconElement
		{
			get
			{
				var source = new FontIconSource { Glyph = "" };
				return source.CreateIconElement();
			}
		}

		FrameworkElement? ISidebarItemPresentationModel.IconElement => IconElement;
		FrameworkElement? ISidebarItemPresentationModel.ItemDecorator => null;

		public PersonItem(string libraryId, Person person)
		{
			LibraryId = libraryId;
			Person = person;
			Text = person.Name ?? person.AutoLabel;
			Path = $"person:{libraryId}:{person.Id}";
		}

		// Refreshes Text after a rename (Settings People page) without rebuilding the item.
		public void UpdateFrom(Person person)
		{
			Person = person;
			Text = person.Name ?? person.AutoLabel;
			OnPropertyChanged(nameof(Text));
			OnPropertyChanged(nameof(ToolTip));
		}

		public int CompareTo(INavigationControlItem? other)
		{
			var text = Text ?? throw new InvalidOperationException("The person name has not been initialized.");
			var otherText = other?.Text
				?? throw new ArgumentException("The compared item must have a name.", nameof(other));

			return text.CompareTo(otherText);
		}
	}
}

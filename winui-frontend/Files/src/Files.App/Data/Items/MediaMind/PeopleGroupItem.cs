// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Controls;
using Files.App.Services.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Files.App.Data.Items.MediaMind
{
	// MediaMind: sidebar branch for a People Group (ADR-0007/0008), or a library's
	// root node when built from PeopleTreeOut.Root. Unlike FileTagItem (always a
	// leaf), Children is non-null: the whole tree arrives in one TreeAsync call, so
	// child items are built once, eagerly, from the already-fetched PeopleGroup —
	// no lazy per-node fetch or filesystem watcher (ExpandableSidebarItemBase is a
	// real-folder abstraction and does not fit this virtual, fully-materialized tree).
	public sealed partial class PeopleGroupItem : ObservableObject, INavigationControlItem
	{
		public string LibraryId { get; }

		public PeopleGroup Group { get; }

		// Set instead of Group.Name for a library's root node, so the sidebar shows
		// the library's display name rather than the tree root's (usually empty) name.
		public string? Text { get; }

		public string Path { get; }

		public SectionType Section { get; set; } = SectionType.People;

		public ContextMenuOptions? MenuOptions { get; set; } = new() { IsLocationItem = true };

		public NavigationControlItemType ItemType => NavigationControlItemType.PeopleGroup;

		private readonly List<INavigationControlItem> children;
		public object? Children => children;

		// Typed views over the same children, for PeopleGroupPage's tile grid and
		// PeopleManager's tree lookup — Children stays "object?" only to satisfy
		// INavigationControlItem/the sidebar control's generic contract.
		public IReadOnlyList<PeopleGroupItem> Subgroups { get; }
		public IReadOnlyList<PersonItem> ChildPersons { get; }

		// Must raise PropertyChanged: SidebarViewModel's flat tree inserts child rows
		// only when it observes IsExpanded flip (a plain auto-property fires nothing,
		// so the chevron shows but expands to nothing). Matches ExpandableSidebarItemBase.
		private bool isExpanded;
		public bool IsExpanded
		{
			get => isExpanded;
			set => SetProperty(ref isExpanded, value);
		}

		public object? ToolTip => Text;

		public IconElement? IconElement
		{
			get
			{
				var source = new FontIconSource { Glyph = "" };
				return source.CreateIconElement();
			}
		}

		FrameworkElement? ISidebarItemPresentationModel.IconElement => IconElement;
		FrameworkElement? ISidebarItemPresentationModel.ItemDecorator => null;

		public PeopleGroupItem(string libraryId, PeopleGroup group, string? displayNameOverride = null)
		{
			LibraryId = libraryId;
			Group = group;
			Text = displayNameOverride ?? group.Name;
			Path = $"group:{libraryId}:{group.Path}";

			var subgroups = new List<PeopleGroupItem>(group.Subgroups.Count);
			foreach (var subgroup in group.Subgroups)
				subgroups.Add(new PeopleGroupItem(libraryId, subgroup));
			Subgroups = subgroups;

			var childPersons = new List<PersonItem>(group.Persons.Count);
			foreach (var person in group.Persons)
				childPersons.Add(new PersonItem(libraryId, person));
			ChildPersons = childPersons;

			children = new List<INavigationControlItem>(subgroups.Count + childPersons.Count);
			children.AddRange(subgroups);
			children.AddRange(childPersons);
		}

		public int CompareTo(INavigationControlItem? other)
		{
			var text = Text ?? throw new InvalidOperationException("The group name has not been initialized.");
			var otherText = other?.Text
				?? throw new ArgumentException("The compared item must have a name.", nameof(other));

			return text.CompareTo(otherText);
		}
	}
}

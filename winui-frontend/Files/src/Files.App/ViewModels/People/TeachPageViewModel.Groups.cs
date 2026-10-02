// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Services.MediaMind;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Files.App.ViewModels.People
{
	// Group pictures, one at a time like Needs your check: the list on the left, the picture itself
	// on the right (whole, zoomable, videos playing) with the choices under it. A group folder is
	// picked from the folders already there (an OT4 made earlier) or made new.
	public sealed partial class TeachPageViewModel
	{
		private TeachGroupItem? currentGroup;
		public TeachGroupItem? CurrentGroup
		{
			get => currentGroup;
			set
			{
				if (!SetProperty(ref currentGroup, value))
					return;
				groupVideoFailed = false;
				groupFolderQuery = string.Empty;
				OnPropertyChanged(nameof(GroupFolderQuery));
				FilterGroupFolders();
				OnPropertyChanged(nameof(GroupFileName));
				OnPropertyChanged(nameof(GroupPeopleText));
				OnPropertyChanged(nameof(GroupNewFolderHint));
				OnPropertyChanged(nameof(GroupAnswerVisibility));
				OnPropertyChanged(nameof(GroupFolders));
				RaiseGroupMedia();
				_ = LoadGroupPreviewAsync(value);
			}
		}

		public string GroupFileName => CurrentGroup?.FileName ?? string.Empty;

		public string GroupPeopleText => CurrentGroup?.PeopleText ?? string.Empty;

		public string GroupNewFolderHint => CurrentGroup?.NewFolderHint ?? string.Empty;

		public ObservableCollection<GroupFolderOption>? GroupFolders => CurrentGroup?.Folders;

		public Visibility GroupAnswerVisibility => CurrentGroup is null ? Visibility.Collapsed : Visibility.Visible;

		// Do the same for every picture of exactly these people, here and in watched folders.
		public bool GroupRemember { get; set; } = true;

		// --- the picture itself ---

		public bool GroupIsVideo => CurrentGroup?.IsVideo == true;

		private bool groupVideoFailed;

		public Visibility GroupPlayerVisibility => GroupIsVideo && !groupVideoFailed ? Visibility.Visible : Visibility.Collapsed;

		public Visibility GroupImageVisibility => GroupIsVideo && !groupVideoFailed ? Visibility.Collapsed : Visibility.Visible;

		private BitmapImage? groupPreview;
		public BitmapImage? GroupPreview
		{
			get => groupPreview;
			private set => SetProperty(ref groupPreview, value);
		}

		private bool groupPreviewLoading;
		public bool GroupPreviewLoading
		{
			get => groupPreviewLoading;
			private set => SetProperty(ref groupPreviewLoading, value);
		}

		private void RaiseGroupMedia()
		{
			OnPropertyChanged(nameof(GroupIsVideo));
			OnPropertyChanged(nameof(GroupPlayerVisibility));
			OnPropertyChanged(nameof(GroupImageVisibility));
		}

		// Windows couldn't play it: show a still (the engine's thumbnail of it) instead.
		public void ReportGroupVideoFailed()
		{
			if (groupVideoFailed || CurrentGroup is not { IsVideo: true } item)
				return;
			groupVideoFailed = true;
			RaiseGroupMedia();
			_ = LoadGroupPreviewAsync(item);
		}

		public void ReportGroupVideo(bool loading)
			=> GroupPreviewLoading = loading;

		// A picture is shown whole, from the file; a video's still comes from the engine. If the file
		// can't be read or decoded here, the engine's large thumbnail stands in.
		private async Task LoadGroupPreviewAsync(TeachGroupItem? item)
		{
			GroupPreview = null;
			if (item is null || item.IsVideo && !groupVideoFailed)
			{
				GroupPreviewLoading = item is not null;
				return;
			}
			GroupPreviewLoading = true;
			BitmapImage? bitmap = null;
			try
			{
				if (!item.IsVideo)
					bitmap = await (await Task.Run(() => SystemIO.File.ReadAllBytesAsync(item.Question.AbsPath))).ToBitmapAsync();
			}
			// Offline drive, or a format Windows can't decode: the thumbnail below.
			catch (Exception)
			{
			}
			try
			{
				if (bitmap is null && await ApiAsync() is { } api)
					bitmap = await (await api.Teach.FileThumbnailAsync(LibraryId, item.Question.Path, 1024)).ToBitmapAsync();
			}
			catch (Exception)
			{
			}
			if (CurrentGroup != item)
				return;
			GroupPreview = bitmap;
			GroupPreviewLoading = false;
		}

		public void SelectNextGroup(int step)
		{
			if (Groups.Count == 0)
				return;
			var index = CurrentGroup is { } current ? Groups.IndexOf(current) : -1;
			CurrentGroup = Groups[Math.Clamp(index + step, 0, Groups.Count - 1)];
		}

		// --- choosing a group folder: the ones already there, or a new one ---

		public ObservableCollection<GroupExistingFolder> GroupFolderMatches { get; } = [];

		private string groupFolderQuery = string.Empty;
		public string GroupFolderQuery
		{
			get => groupFolderQuery;
			set
			{
				value ??= string.Empty;
				if (groupFolderQuery == value)
					return;
				groupFolderQuery = value;
				OnPropertyChanged();
				FilterGroupFolders();
			}
		}

		private void FilterGroupFolders()
		{
			GroupFolderMatches.Clear();
			if (CurrentGroup is not { } item)
				return;
			var query = GroupFolderQuery.Trim();
			foreach (var folder in item.ExistingFolders)
				if (query.Length == 0 || folder.Display.Contains(query, StringComparison.CurrentCultureIgnoreCase))
					GroupFolderMatches.Add(folder);
			OnPropertyChanged(nameof(GroupNoFoldersVisibility));
			OnPropertyChanged(nameof(CanCreateGroupFolder));
			OnPropertyChanged(nameof(GroupCreateText));
		}

		public Visibility GroupNoFoldersVisibility => GroupFolderMatches.Count == 0 ? Visibility.Visible : Visibility.Collapsed;

		// The typed name, when no folder already has it (a folder that has it is picked from the list).
		private GroupExistingFolder? ExactMatch
			=> GroupFolderMatches.FirstOrDefault(f => string.Equals(f.Display, GroupFolderQuery.Trim(), StringComparison.CurrentCultureIgnoreCase));

		public bool CanCreateGroupFolder => GroupFolderQuery.Trim().Length > 0 && ExactMatch is null;

		public string GroupCreateText => GroupFolderQuery.Trim().Length == 0
			? Strings.MediaMind_TeachGroupNewCreate.GetLocalizedResource()
			: string.Format(Strings.MediaMind_TeachGroupCreateNamed.GetLocalizedResource(), GroupFolderQuery.Trim());

		// Enter in the box: the folder with that name if there is one, else a new one.
		public Task SubmitGroupFolderAsync()
		{
			if (CurrentGroup is not { } item || GroupFolderQuery.Trim().Length == 0)
				return Task.CompletedTask;
			return ExactMatch is { } folder
				? PlaceGroupAsync(item, "existing", null, null, GroupRemember, folder.Path)
				: PlaceGroupAsync(item, "new", null, GroupFolderQuery.Trim(), GroupRemember);
		}
	}

	// A folder already under a group picture's new-folder parent, shown relative to it ("OT4").
	public sealed record GroupExistingFolder(string Display, string Path);
}

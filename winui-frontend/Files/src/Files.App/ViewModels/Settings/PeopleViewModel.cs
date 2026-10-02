// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Services.MediaMind;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Files.App.ViewModels.Settings
{
	// MediaMind: rename/merge management for Persons, one section per library —
	// modeled on TagsViewModel, but flat (Persons.ListAsync, not the nested
	// TreeAsync tree the sidebar uses; this page has no need for Group structure).
	public sealed partial class PeopleViewModel : ObservableObject
	{
		private readonly IMediaMindEngineService engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();

		public ObservableCollection<PeopleLibraryGroupViewModel> Libraries { get; } = [];

		public PeopleViewModel()
		{
			_ = LoadAsync();
		}

		public async Task LoadAsync()
		{
			if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
				return;

			var api = engine.Api;
			var libraries = await api.Libraries.ListAsync();

			Libraries.Clear();
			foreach (var library in libraries)
			{
				try
				{
					var persons = await api.Persons.ListAsync(library.Id);
					if (persons.Persons.Count == 0)
						continue;

					var group = new PeopleLibraryGroupViewModel(library.Id, library.Name);
					foreach (var person in persons.Persons)
						group.People.Add(new ListedPersonViewModel(library.Id, person));

					Libraries.Add(group);
				}
				// A library with no scan yet must not blank the whole page — skip it.
				catch (Exception)
				{
				}
			}
		}

		public async Task EditExistingPersonAsync(ListedPersonViewModel item, string newName)
		{
			var api = engine.Api;
			if (api is null)
				return;

			await api.Persons.RenameAsync(item.LibraryId, item.Person.Id, newName);
			item.UpdateName(newName);

			_ = App.PeopleManager.RefreshAsync();
		}

		public async Task MergePersonsAsync(PeopleLibraryGroupViewModel group, ListedPersonViewModel source, ListedPersonViewModel target)
		{
			var api = engine.Api;
			if (api is null)
				return;

			await api.Persons.MergeAsync(group.LibraryId, source.Person.Id, target.Person.Id);
			group.People.Remove(source);

			_ = App.PeopleManager.RefreshAsync();
		}
	}

	public sealed partial class PeopleLibraryGroupViewModel(string libraryId, string libraryName) : ObservableObject
	{
		public string LibraryId { get; } = libraryId;

		public string LibraryName { get; } = libraryName;

		public ObservableCollection<ListedPersonViewModel> People { get; } = [];
	}

	public sealed partial class ListedPersonViewModel : ObservableObject
	{
		public string LibraryId { get; }

		public Person Person { get; private set; }

		private string displayName;
		public string DisplayName
		{
			get => displayName;
			private set => SetProperty(ref displayName, value);
		}

		private bool isEditing;
		public bool IsEditing
		{
			get => isEditing;
			set => SetProperty(ref isEditing, value);
		}

		private string? newName;
		public string? NewName
		{
			get => newName;
			set => SetProperty(ref newName, value);
		}

		private BitmapImage? thumbnail;
		public BitmapImage? Thumbnail
		{
			get => thumbnail;
			private set => SetProperty(ref thumbnail, value);
		}

		public ListedPersonViewModel(string libraryId, Person person)
		{
			LibraryId = libraryId;
			Person = person;
			displayName = person.Name ?? person.AutoLabel;
			_ = LoadThumbnailAsync();
		}

		public void UpdateName(string name)
		{
			Person = Person with { Name = name };
			DisplayName = name;
		}

		private async Task LoadThumbnailAsync()
		{
			if (Person.SampleFaceIds.Count == 0)
				return;

			try
			{
				var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
				if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is null)
					return;

				var bytes = await engine.Api.Persons.FaceThumbnailAsync(LibraryId, Person.SampleFaceIds[0], 96);
				var bitmap = await bytes.ToBitmapAsync();
				if (bitmap is null)
					return;

				await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() => Thumbnail = bitmap);
			}
			catch (Exception)
			{
			}
		}
	}
}

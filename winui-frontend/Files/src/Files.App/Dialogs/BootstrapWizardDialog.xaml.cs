// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Services.MediaMind;
using Microsoft.Extensions.Logging;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Runtime.CompilerServices;
using WinRT;

namespace Files.App.Dialogs
{
	// MediaMind Phase 5 (BLOCK5_UI_BLUEPRINT.md §4, feature 8 / ADR-0002): the
	// bootstrap-from-folders reviewed proposal. Refreshes folder-binding suggestions
	// across every watched library and lists the proposed people; each is committed
	// only on an explicit Add (Bindings.AcceptAsync) or Dismiss — never auto-applied
	// (review-before-commit). Launched from WatchedFoldersPage.
	public sealed partial class BootstrapWizardDialog : ContentDialog, INotifyPropertyChanged
	{
		private readonly ILogger logger = Ioc.Default.GetRequiredService<ILogger<App>>();
		private MediaMindApiClient? api;

		private FrameworkElement RootAppElement
		{
			[DynamicWindowsRuntimeCast(typeof(FrameworkElement))]
			get => (FrameworkElement)MainWindow.Instance.Content;
		}

		public ObservableCollection<BootstrapProposal> Proposals { get; } = [];

		private bool isLoading = true;
		public bool IsLoading { get => isLoading; private set => Set(ref isLoading, value); }

		private bool isEmpty;
		public bool IsEmpty { get => isEmpty; private set => Set(ref isEmpty, value); }

		private bool hasProposals;
		public bool HasProposals { get => hasProposals; private set => Set(ref hasProposals, value); }

		public BootstrapWizardDialog()
		{
			InitializeComponent();
			Loaded += (_, _) => _ = LoadProposalsAsync();
		}

		private async Task LoadProposalsAsync()
		{
			var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
			if (!await engine.EnsureStartedAsync(CancellationToken.None) || engine.Api is not { } client)
			{
				IsLoading = false;
				IsEmpty = true;
				return;
			}

			api = client;
			try
			{
				var libraries = await client.Libraries.ListAsync();
				foreach (var library in libraries)
				{
					try
					{
						await client.Bindings.RefreshAsync(library.Id);
						var result = await client.Bindings.SuggestionsAsync(library.Id, "pending");
						foreach (var suggestion in result.Suggestions)
							Proposals.Add(new BootstrapProposal(library.Id, suggestion));
					}
					// One library that never scanned (or is offline) must not blank the
					// whole wizard — skip it and keep aggregating the rest.
					catch (Exception ex)
					{
						logger.LogWarning(ex, "Failed to load bindings for library {LibraryId}.", library.Id);
					}
				}
			}
			catch (Exception ex)
			{
				logger.LogWarning(ex, "Failed to load bootstrap proposals.");
			}

			IsLoading = false;
			HasProposals = Proposals.Count > 0;
			IsEmpty = Proposals.Count == 0;
		}

		private async void Accept_Click(object sender, RoutedEventArgs e)
		{
			if (api is null || (sender as FrameworkElement)?.Tag is not BootstrapProposal proposal)
				return;

			try
			{
				await api.Bindings.AcceptAsync(proposal.LibraryId, proposal.SuggestionId);
				proposal.MarkResolved(Strings.MediaMind_BootstrapAdded.GetLocalizedResource());
				_ = App.PeopleManager.RefreshAsync();
			}
			catch (Exception ex)
			{
				logger.LogWarning(ex, "Failed to accept binding suggestion {SuggestionId}.", proposal.SuggestionId);
			}
		}

		private async void Dismiss_Click(object sender, RoutedEventArgs e)
		{
			if (api is null || (sender as FrameworkElement)?.Tag is not BootstrapProposal proposal)
				return;

			try
			{
				await api.Bindings.DismissAsync(proposal.LibraryId, proposal.SuggestionId);
				proposal.MarkResolved(Strings.MediaMind_BootstrapDismissed.GetLocalizedResource());
			}
			catch (Exception ex)
			{
				logger.LogWarning(ex, "Failed to dismiss binding suggestion {SuggestionId}.", proposal.SuggestionId);
			}
		}

		public event PropertyChangedEventHandler? PropertyChanged;

		private void Set<T>(ref T field, T value, [CallerMemberName] string? name = null)
		{
			if (EqualityComparer<T>.Default.Equals(field, value))
				return;
			field = value;
			PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
		}
	}

	// One reviewed proposal row. PersonSummary is the proposed person's name (or the
	// folder leaf when the engine hasn't named it yet); Detail carries the folder +
	// photo count so the user can judge before committing.
	public sealed partial class BootstrapProposal : ObservableObject
	{
		public string LibraryId { get; }

		public long SuggestionId { get; }

		public string PersonSummary { get; }

		public string Detail { get; }

		private bool isResolved;
		public bool IsResolved { get => isResolved; private set => SetProperty(ref isResolved, value); }

		private string resolvedText = string.Empty;
		public string ResolvedText { get => resolvedText; private set => SetProperty(ref resolvedText, value); }

		public BootstrapProposal(string libraryId, BindingSuggestion suggestion)
		{
			LibraryId = libraryId;
			SuggestionId = suggestion.Id;

			var leaf = System.IO.Path.GetFileName(suggestion.FolderRel.TrimEnd('\\', '/'));
			PersonSummary = suggestion.PersonNames.Count > 0
				? string.Join(", ", suggestion.PersonNames)
				: (string.IsNullOrEmpty(leaf) ? suggestion.FolderRel : leaf);

			var folder = string.IsNullOrEmpty(suggestion.FolderRel) ? leaf : suggestion.FolderRel;
			Detail = string.Format(Strings.MediaMind_BootstrapDetail.GetLocalizedResource(), folder, suggestion.FileCount);
		}

		public void MarkResolved(string text)
		{
			ResolvedText = text;
			IsResolved = true;
		}
	}
}

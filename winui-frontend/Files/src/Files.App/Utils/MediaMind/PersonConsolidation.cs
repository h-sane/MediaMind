// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Data.Items.MediaMind;
using Files.App.Dialogs;
using Files.App.Services.MediaMind;
using Microsoft.Extensions.Logging;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Net;

namespace Files.App.Utils.MediaMind
{
	// MediaMind Phase 4 (BLOCK5_UI_BLUEPRINT.md §4): per-person Consolidation — the
	// one byte-moving flow. Mirrors the Electron app's PersonViewBanner: pin a
	// primary folder, preview the planned moves, confirm, then run the move as a
	// background job (progress renders in StatusCenter via MediaMindJobStatusBridge).
	// The engine does copy-then-delete + journaling, so the action is undoable.
	// Launched from the Person sidebar context menu (SidebarViewModel).
	internal static class PersonConsolidation
	{
		private static readonly ILogger Logger = Ioc.Default.GetRequiredService<ILogger<App>>();

		public static async Task SetPrimaryFolderAsync(PersonItem? item)
		{
			if (item is null || await GetApiAsync() is not { } api)
				return;

			if (!FolderPicker.Pick(out var folderPath))
				return;

			try
			{
				var result = await api.Persons.SetPrimaryFolderAsync(item.LibraryId, item.Person.Id, folderPath);
				item.UpdateFrom(item.Person with { PrimaryFolderPath = result.PrimaryFolderPath });
			}
			catch (Exception ex)
			{
				Logger.LogWarning(ex, "Failed to set primary folder for person {PersonId}.", item.Person.Id);
			}
		}

		public static async Task ClearPrimaryFolderAsync(PersonItem? item)
		{
			if (item is null || await GetApiAsync() is not { } api)
				return;

			try
			{
				await api.Persons.SetPrimaryFolderAsync(item.LibraryId, item.Person.Id, null);
				item.UpdateFrom(item.Person with { PrimaryFolderPath = null });
			}
			catch (Exception ex)
			{
				Logger.LogWarning(ex, "Failed to clear primary folder for person {PersonId}.", item.Person.Id);
			}
		}

		public static async Task ConsolidateAsync(PersonItem? item)
		{
			if (item is null || await GetApiAsync() is not { } api)
				return;

			var folder = item.Person.PrimaryFolderPath;
			if (string.IsNullOrWhiteSpace(folder))
			{
				await ShowInfoAsync(Strings.MediaMind_Consolidate.GetLocalizedResource(), Strings.MediaMind_SetFolderFirst.GetLocalizedResource());
				return;
			}

			OrganizePreview preview;
			try
			{
				preview = await api.Organize.PreviewAsync(item.LibraryId, "prominent", item.Person.Id);
			}
			catch (Exception ex)
			{
				Logger.LogWarning(ex, "Failed to preview consolidation for person {PersonId}.", item.Person.Id);
				return;
			}

			if (preview.Planned == 0)
			{
				await ShowInfoAsync(
					Strings.MediaMind_NothingToMove.GetLocalizedResource(),
					string.Format(Strings.MediaMind_AlreadyInFolder.GetLocalizedResource(), folder));
				return;
			}

			if (!await ConfirmMoveAsync(preview.Planned, folder))
				return;

			try
			{
				// Progress + completion render in StatusCenter automatically (job type
				// "organize-execute" flows through MediaMindJobStatusBridge).
				await api.Organize.ExecuteJobAsync(
					item.LibraryId,
					expectedPlanned: preview.Planned,
					expectedPlanHash: preview.PlanHash,
					mode: "move",
					groupScope: "prominent",
					personId: item.Person.Id);
			}
			catch (Exception ex)
			{
				Logger.LogWarning(ex, "Failed to start consolidation for person {PersonId}.", item.Person.Id);
			}
		}

		public static async Task UndoAsync(PersonItem? item)
		{
			if (item is null || await GetApiAsync() is not { } api)
				return;

			try
			{
				await api.Organize.UndoAsync(item.LibraryId);
			}
			catch (MediaMindApiException ex) when (ex.StatusCode == HttpStatusCode.NotFound)
			{
				await ShowInfoAsync(Strings.MediaMind_UndoConsolidation.GetLocalizedResource(), Strings.MediaMind_NothingToUndo.GetLocalizedResource());
			}
			catch (Exception ex)
			{
				Logger.LogWarning(ex, "Failed to undo consolidation for library {LibraryId}.", item.LibraryId);
			}
		}

		private static async Task<MediaMindApiClient?> GetApiAsync()
		{
			var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
			return await engine.EnsureStartedAsync(CancellationToken.None) ? engine.Api : null;
		}

		private static async Task<bool> ConfirmMoveAsync(int planned, string folder)
		{
			var dialog = new DynamicDialog(new DynamicDialogViewModel
			{
				TitleText = string.Format(Strings.MediaMind_ConsolidateTitle.GetLocalizedResource(), planned),
				DisplayControl = new Grid
				{
					MinWidth = 320d,
					Children = { new TextBlock { Text = string.Format(Strings.MediaMind_ConsolidateBody.GetLocalizedResource(), folder), TextWrapping = TextWrapping.WrapWholeWords } },
				},
				PrimaryButtonAction = (vm, _) => vm.Hide(),
				PrimaryButtonText = Strings.MediaMind_Move.GetLocalizedResource(),
				CloseButtonText = Strings.Cancel.GetLocalizedResource(),
				DynamicButtons = DynamicDialogButtons.Primary | DynamicDialogButtons.Cancel,
			});

			await dialog.TryShowAsync();
			return dialog.DynamicResult is DynamicDialogResult.Primary;
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

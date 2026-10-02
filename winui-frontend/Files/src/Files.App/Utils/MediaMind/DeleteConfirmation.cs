// Copyright (c) Files Community
// Licensed under the MIT License.

using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Files.App.Utils.MediaMind
{
	// MediaMind: the one delete confirmation used by the review pages. It names the files,
	// says plainly whether they go to the Recycle Bin or are deleted for good (a network drive
	// such as the vault has no Recycle Bin), and offers "Don't ask again on this page".
	// Each page keeps its own "don't ask" setting under its own key.
	internal static class DeleteConfirmation
	{
		public static bool IsSkipped(string settingKey)
		{
			try { return Windows.Storage.ApplicationData.Current.LocalSettings.Values[settingKey] is true; }
			catch (Exception) { return false; }
		}

		public static void SetSkipped(string settingKey, bool skipped)
		{
			try { Windows.Storage.ApplicationData.Current.LocalSettings.Values[settingKey] = skipped; }
			catch (Exception) { }
		}

		// True to go ahead. Returns at once when the user chose not to be asked.
		public static async Task<bool> ConfirmAsync(XamlRoot xamlRoot, IReadOnlyList<string> paths, bool toRecycleBin, string settingKey)
		{
			if (IsSkipped(settingKey))
				return true;
			var dontAsk = new CheckBox { Content = Strings.MediaMind_ReviewDeleteDontAsk.GetLocalizedResource() };
			var dialog = new ContentDialog
			{
				XamlRoot = xamlRoot,
				Title = paths.Count == 1
					? Strings.MediaMind_ReviewDeleteTitle.GetLocalizedResource()
					: string.Format(Strings.MediaMind_ReviewDeleteTitleMany.GetLocalizedResource(), paths.Count),
				Content = new StackPanel
				{
					Spacing = 12,
					MaxWidth = 420,
					Children =
					{
						new TextBlock { Text = string.Join("\n", paths.Take(5).Select(SystemIO.Path.GetFileName)) + (paths.Count > 5 ? "\n…" : string.Empty), TextWrapping = TextWrapping.Wrap, TextTrimming = TextTrimming.CharacterEllipsis },
						new TextBlock
						{
							Text = (toRecycleBin ? Strings.MediaMind_ReviewDeleteToBin : Strings.MediaMind_ReviewDeletePermanent).GetLocalizedResource(),
							TextWrapping = TextWrapping.Wrap,
							Opacity = 0.8,
						},
						dontAsk,
					},
				},
				PrimaryButtonText = Strings.MediaMind_ReviewDeleteConfirm.GetLocalizedResource(),
				CloseButtonText = Strings.Cancel.GetLocalizedResource(),
				DefaultButton = ContentDialogButton.Primary,
			};
			if (await dialog.ShowAsync() != ContentDialogResult.Primary)
				return false;
			if (dontAsk.IsChecked == true)
				SetSkipped(settingKey, true);
			return true;
		}
	}
}

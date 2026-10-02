// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Windows.Storage;

namespace Files.App.Utils.MediaMind
{
	// MediaMind's "choose a folder" dialogs open where the user last worked: the last folder picked
	// or the last folder files were moved into, remembered across restarts. They opened at the same
	// fixed place every time, so every move meant navigating back down again (2026-09-27).
	internal static class FolderPicker
	{
		private const string LastFolderKey = "MediaMind.LastFolder";

		// near: where to open when nothing is remembered yet (the folder being worked on).
		public static bool Pick(out string folder, string? near = null)
		{
			var start = Existing(LastFolder) ?? Existing(near);
			var picked = Ioc.Default.GetRequiredService<ICommonDialogService>().Open_FileOpenDialog(
				MainWindow.Instance.WindowHandle, true, [], Environment.SpecialFolder.MyPictures, out folder, null, start);
			if (!picked || string.IsNullOrWhiteSpace(folder))
				return false;
			Remember(folder);
			return true;
		}

		// After an operation put files somewhere, the next dialog opens there.
		public static void Remember(string? folder)
		{
			if (string.IsNullOrWhiteSpace(folder))
				return;
			try
			{
				ApplicationData.Current.LocalSettings.Values[LastFolderKey] = folder;
			}
			// Settings unavailable (unpackaged run): the dialog just opens at its default.
			catch (Exception)
			{
			}
		}

		private static string? LastFolder
		{
			get
			{
				try
				{
					return ApplicationData.Current.LocalSettings.Values[LastFolderKey] as string;
				}
				catch (Exception)
				{
					return null;
				}
			}
		}

		// A folder that was deleted or is on a drive that's gone falls back to the next choice.
		private static string? Existing(string? folder)
		{
			try
			{
				return !string.IsNullOrWhiteSpace(folder) && SystemIO.Directory.Exists(folder) ? folder : null;
			}
			catch (Exception)
			{
				return null;
			}
		}
	}
}

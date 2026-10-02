// Copyright (c) Files Community
// Licensed under the MIT License.

using System.Collections.Concurrent;
using Windows.Win32;
using Windows.Win32.Foundation;

namespace Files.App.Utils.MediaMind
{
	// MediaMind: one spelling per folder for "which library holds this folder?".
	// A mapped drive (e.g. a Cryptomator vault on D:) and its network path
	// (\\cryptomator-vault\...) are the same folder; a library registered under one
	// must still match when the user browses the other.
	internal static class MediaMindPaths
	{
		private static readonly ConcurrentDictionary<string, string> DriveRoots = new(StringComparer.OrdinalIgnoreCase);

		public static string Canonical(string path)
		{
			path = path.Replace('/', '\\').TrimEnd('\\');
			if (path.Length >= 2 && char.IsLetter(path[0]) && path[1] == ':')
			{
				var drive = path[..2];
				// Only a mapping is remembered: a vault drive often mounts after the app starts,
				// and a cached "not mapped" would hide it for the whole session.
				if (!DriveRoots.TryGetValue(drive, out var remote))
				{
					remote = RemoteNameOf(drive);
					if (remote.Length > 0)
						DriveRoots[drive] = remote;
				}
				if (remote.Length > 0)
					path = remote + path[2..];
			}
			return path;
		}

		public static bool IsUnder(string path, string root)
		{
			path = Canonical(path);
			root = Canonical(root);
			return path.Equals(root, StringComparison.OrdinalIgnoreCase)
				|| path.StartsWith(root + "\\", StringComparison.OrdinalIgnoreCase);
		}

		// "" when the drive is local (not mapped to a network path).
		private static unsafe string RemoteNameOf(string drive)
		{
			Span<char> remote = stackalloc char[512];
			uint length = (uint)remote.Length;
			return PInvoke.WNetGetConnection(drive, remote, ref length) == WIN32_ERROR.NO_ERROR
				? remote.ToString().TrimEnd('\0').Split('\0')[0].TrimEnd('\\')
				: string.Empty;
		}
	}
}

// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Services.MediaMind;
using System.IO;
using System.Net;
using System.Net.Http;
using Windows.Storage;

namespace Files.App.Utils.MediaMind
{
	// MediaMind: virtual-path adapter for a Person's media page (/persons/{id}/media),
	// analogous to FolderSearch's "tag:" handling but backed by the engine's flat
	// result list instead of an on-disk index walk. ListedItems are built by field
	// assignment only — same style as FolderSearch.GetListedItemAsync — so a file on
	// a currently-unmounted drive still renders (ADR-0004; no File.Exists check).
	internal static class PeopleSearch
	{
		public static async Task<List<ListedItem>> SearchAsync(string libraryId, long personId, CancellationToken ct)
		{
			var engine = Ioc.Default.GetRequiredService<IMediaMindEngineService>();
			if (!await engine.EnsureStartedAsync(ct) || engine.Api is null || engine.Client is null)
				return [];

			var api = engine.Api;
			var httpClient = engine.Client;
			var media = await api.Persons.MediaAsync(libraryId, personId, ct);

			var results = new List<ListedItem>(media.Count);
			foreach (var item in media)
			{
				var listedItem = new ListedItem(null)
				{
					PrimaryItemAttribute = StorageItemTypes.File,
					ItemNameRaw = Path.GetFileName(item.Path),
					ItemPath = item.AbsPath,
					ItemType = item.Kind,
					LoadFileIcon = false,
					ViaPlacement = item.ViaPlacement == true,
					// Every other ListedItem construction site sets this (FolderSearch,
					// the Win32/Universal storage enumerators) — the Name text and the
					// thumbnail/icon container are both bound to Opacity, so leaving it at
					// the CLR double default (0.0) renders a fully transparent name and
					// thumbnail, not a missing one. This is why both looked "blank".
					Opacity = 1,
				};
				results.Add(listedItem);

				_ = LoadThumbnailAsync(listedItem, api, httpClient, libraryId, item);
			}

			return results;
		}

		private static async Task LoadThumbnailAsync(ListedItem listedItem, MediaMindApiClient api, HttpClient httpClient, string libraryId, PersonMediaItem item)
		{
			try
			{
				// A face-crop thumbnail if this file matched the person's face; otherwise
				// (placement-attributed, ADR-0010) fall back to the full-file preview —
				// there is no generic path-keyed thumbnail endpoint, only preview/raw.
				byte[] bytes = item.FaceId is long faceId
					? await api.Persons.FaceThumbnailAsync(libraryId, faceId)
					: await httpClient.GetByteArrayAsync(api.Files.PreviewUrl(libraryId, item.Path, 256));

				var bitmap = await bytes.ToBitmapAsync();
				if (bitmap is null)
					return;

				await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() => listedItem.FileImage = bitmap);
			}
			// GetBytesAsync/GetByteArrayAsync are plain HttpClient passthroughs (no
			// MediaMindApiException mapping — that only wraps the typed JSON endpoints),
			// so the engine's 409 library_offline (ADR-0004) surfaces as a raw
			// HttpRequestException with StatusCode set.
			catch (HttpRequestException ex) when (ex.StatusCode is HttpStatusCode.Conflict)
			{
				await MainWindow.Instance.DispatcherQueue.EnqueueOrInvokeAsync(() => listedItem.IsOffline = true);
			}
			// Thumbnail loading is best-effort; any other failure just leaves the generic file icon.
			catch (Exception)
			{
			}
		}
	}
}

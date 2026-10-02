// Copyright (c) Files Community
// Licensed under the MIT License.

using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;

namespace Files.App.Services.MediaMind
{
	/// <summary>
	/// Thrown for a non-2xx response from the MediaMind engine. Mirrors client.ts's
	/// <c>request()</c>, which throws <c>Error(detail)</c> using the response body's
	/// <c>detail</c> field when present.
	/// </summary>
	public sealed class MediaMindApiException(string detail, HttpStatusCode statusCode) : Exception(detail)
	{
		public HttpStatusCode StatusCode { get; } = statusCode;

		/// <summary>
		/// True for the engine's 409 <c>library_offline</c> response (ADR-0004): the
		/// library's drive is unmounted and it has no off-drive index yet. Mirrors
		/// client.ts's <c>isLibraryOffline</c>.
		/// </summary>
		public bool IsLibraryOffline => StatusCode is HttpStatusCode.Conflict && Message == "library_offline";
	}

	/// <summary>
	/// Typed client for the MediaMind engine's HTTP surface. Mirrors
	/// <c>app/src/renderer/src/api/client.ts</c>'s <c>api</c> object 1:1 — group
	/// names, method names, and endpoint shapes match; keep the two in sync.
	/// Bound to an <see cref="HttpClient"/> that already has <c>BaseAddress</c> and
	/// the <c>X-MediaMind-Token</c> header preset (see <see cref="MediaMindEngineService"/>).
	/// </summary>
	public sealed class MediaMindApiClient
	{
		private readonly HttpClient _http;

		public MediaMindApiClient(HttpClient http)
		{
			_http = http;
			Libraries = new(this);
			Files = new(this);
			Fs = new(this);
			FsOps = new(this);
			Scans = new(this);
			Jobs = new(this);
			Duplicates = new(this);
			Providers = new(this);
			Organize = new(this);
			Pending = new(this);
			MultiPerson = new(this);
			Persons = new(this);
			DuplicateFlags = new(this);
			Bindings = new(this);
			FacesPrep = new(this);
			GlobalPeople = new(this);
			PeopleView = new(this);
			Unprocessed = new(this);
			Teach = new(this);
		}

		public Task<Health> HealthAsync(CancellationToken ct = default)
			=> GetAsync("/v1/health", MediaMindJsonContext.Default.Health, ct);

		public LibrariesApi Libraries { get; }
		public FilesApi Files { get; }
		public FsApi Fs { get; }
		public FsOpsApi FsOps { get; }
		public ScansApi Scans { get; }
		public JobsApi Jobs { get; }
		public DuplicatesApi Duplicates { get; }
		public ProvidersApi Providers { get; }
		public OrganizeApi Organize { get; }
		public PendingApi Pending { get; }
		public MultiPersonApi MultiPerson { get; }
		public PersonsApi Persons { get; }
		public DuplicateFlagsApi DuplicateFlags { get; }
		public BindingsApi Bindings { get; }
		public FacesPrepApi FacesPrep { get; }
		public GlobalPeopleApi GlobalPeople { get; }
		public PeopleViewApi PeopleView { get; }
		public UnprocessedApi Unprocessed { get; }
		public TeachApi Teach { get; }

		// -------------------------------------------------------------------
		// Core request plumbing
		// -------------------------------------------------------------------

		internal Task<TResponse> GetAsync<TResponse>(string path, JsonTypeInfo<TResponse> responseType, CancellationToken ct)
			=> SendAsync(HttpMethod.Get, path, null, responseType, ct);

		internal Task<TResponse> PostAsync<TResponse>(string path, JsonTypeInfo<TResponse> responseType, CancellationToken ct)
			=> SendAsync(HttpMethod.Post, path, null, responseType, ct);

		internal Task<TResponse> PostAsync<TBody, TResponse>(string path, TBody body, JsonTypeInfo<TBody> bodyType, JsonTypeInfo<TResponse> responseType, CancellationToken ct)
			=> SendAsync(HttpMethod.Post, path, JsonSerializer.Serialize(body, bodyType), responseType, ct);

		internal Task<TResponse> PatchAsync<TBody, TResponse>(string path, TBody body, JsonTypeInfo<TBody> bodyType, JsonTypeInfo<TResponse> responseType, CancellationToken ct)
			=> SendAsync(HttpMethod.Patch, path, JsonSerializer.Serialize(body, bodyType), responseType, ct);

		internal Task<TResponse> PutAsync<TBody, TResponse>(string path, TBody body, JsonTypeInfo<TBody> bodyType, JsonTypeInfo<TResponse> responseType, CancellationToken ct)
			=> SendAsync(HttpMethod.Put, path, JsonSerializer.Serialize(body, bodyType), responseType, ct);

		internal Task<TResponse> DeleteAsync<TResponse>(string path, JsonTypeInfo<TResponse> responseType, CancellationToken ct)
			=> SendAsync(HttpMethod.Delete, path, null, responseType, ct);

		internal Task DeleteAsync(string path, CancellationToken ct)
			=> SendAsync(HttpMethod.Delete, path, null, ct);

		internal Task<byte[]> GetBytesAsync(string path, CancellationToken ct)
			=> _http.GetByteArrayAsync(path, ct);

		internal Uri BuildUri(string path)
			=> new(_http.BaseAddress!, path);

		private async Task<TResponse> SendAsync<TResponse>(HttpMethod method, string path, string? jsonBody, JsonTypeInfo<TResponse> responseType, CancellationToken ct)
		{
			using var request = BuildRequest(method, path, jsonBody);
			using var response = await _http.SendAsync(request, ct);
			await EnsureSuccessAsync(response, ct);

			if (response.StatusCode is HttpStatusCode.NoContent)
				return default!;

			var stream = await response.Content.ReadAsStreamAsync(ct);
			return (await JsonSerializer.DeserializeAsync(stream, responseType, ct))!;
		}

		private async Task SendAsync(HttpMethod method, string path, string? jsonBody, CancellationToken ct)
		{
			using var request = BuildRequest(method, path, jsonBody);
			using var response = await _http.SendAsync(request, ct);
			await EnsureSuccessAsync(response, ct);
		}

		private static HttpRequestMessage BuildRequest(HttpMethod method, string path, string? jsonBody)
		{
			var request = new HttpRequestMessage(method, path);
			if (jsonBody is not null)
				request.Content = new StringContent(jsonBody, Encoding.UTF8, "application/json");
			return request;
		}

		private static async Task EnsureSuccessAsync(HttpResponseMessage response, CancellationToken ct)
		{
			if (response.IsSuccessStatusCode)
				return;

			var detail = response.ReasonPhrase ?? response.StatusCode.ToString();
			try
			{
				var body = await response.Content.ReadAsStringAsync(ct);
				using var doc = JsonDocument.Parse(body);
				if (doc.RootElement.TryGetProperty("detail", out var d) && d.ValueKind is JsonValueKind.String)
					detail = d.GetString() ?? detail;
			}
			catch
			{
				// Non-JSON error body — keep the status-derived detail.
			}

			throw new MediaMindApiException(detail, response.StatusCode);
		}

		private static string Q(string value) => Uri.EscapeDataString(value);

		// -------------------------------------------------------------------
		// api.libraries
		// -------------------------------------------------------------------

		public sealed class LibrariesApi(MediaMindApiClient c)
		{
			public Task<List<Library>> ListAsync(CancellationToken ct = default)
				=> c.GetAsync("/v1/libraries", MediaMindJsonContext.Default.ListLibrary, ct);

			public Task<Library> AddAsync(string path, CancellationToken ct = default)
				=> c.PostAsync("/v1/libraries", new PathBody(path), MediaMindJsonContext.Default.PathBody, MediaMindJsonContext.Default.Library, ct);

			public Task RemoveAsync(string id, CancellationToken ct = default)
				=> c.DeleteAsync($"/v1/libraries/{Q(id)}", ct);
		}

		// -------------------------------------------------------------------
		// api.files
		// -------------------------------------------------------------------

		public sealed class FilesApi(MediaMindApiClient c)
		{
			public Task<LibraryFiles> ListAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/files", MediaMindJsonContext.Default.LibraryFiles, ct);

			public Uri PreviewUrl(string libraryId, string path, int size = 2560)
				=> c.BuildUri($"/v1/libraries/{Q(libraryId)}/files/preview?path={Q(path)}&size={size}");

			public Uri RawUrl(string libraryId, string path)
				=> c.BuildUri($"/v1/libraries/{Q(libraryId)}/files/raw?path={Q(path)}");
		}

		// -------------------------------------------------------------------
		// api.fs (+ quickAccess, recent, settings, discovery)
		// -------------------------------------------------------------------

		public sealed class FsApi
		{
			private readonly MediaMindApiClient _c;

			public FsApi(MediaMindApiClient c)
			{
				_c = c;
				QuickAccess = new(c);
				Recent = new(c);
				Settings = new(c);
				Discovery = new(c);
			}

			public QuickAccessApi QuickAccess { get; }
			public RecentApi Recent { get; }
			public SettingsApi Settings { get; }
			public DiscoveryApi Discovery { get; }

			public Task<List<Drive>> DrivesAsync(CancellationToken ct = default)
				=> _c.GetAsync("/v1/fs/drives", MediaMindJsonContext.Default.ListDrive, ct);

			public Task<BrowseDir> ListAsync(string path, CancellationToken ct = default)
				=> _c.GetAsync($"/v1/fs/list?path={Q(path)}", MediaMindJsonContext.Default.BrowseDir, ct);

			public Task<HasMediaResult> HasMediaAsync(IReadOnlyList<string> paths, CancellationToken ct = default)
				=> _c.GetAsync($"/v1/fs/has-media?{string.Join('&', paths.Select(p => $"paths={Q(p)}"))}", MediaMindJsonContext.Default.HasMediaResult, ct);

			public Task<OkResult> PrewarmAsync(string path, int size, CancellationToken ct = default)
				=> _c.GetAsync($"/v1/fs/prewarm?path={Q(path)}&size={size}", MediaMindJsonContext.Default.OkResult, ct);

			public Uri PreviewUrl(string path, int size = 2560)
				=> _c.BuildUri($"/v1/fs/preview?path={Q(path)}&size={size}");

			public Uri RawUrl(string path)
				=> _c.BuildUri($"/v1/fs/raw?path={Q(path)}");

			public Task<BrowseMetadata> MetadataAsync(string path, CancellationToken ct = default)
				=> _c.GetAsync($"/v1/fs/metadata?path={Q(path)}", MediaMindJsonContext.Default.BrowseMetadata, ct);

			public Task<FolderStats> FolderStatsAsync(string path, CancellationToken ct = default)
				=> _c.GetAsync($"/v1/fs/folder-stats?path={Q(path)}", MediaMindJsonContext.Default.FolderStats, ct);

			public Task<FolderFaces> FolderFacesAsync(string path, int limit = 3, CancellationToken ct = default)
				=> _c.GetAsync($"/v1/fs/folder-faces?path={Q(path)}&limit={limit}", MediaMindJsonContext.Default.FolderFaces, ct);

			public Task<DiskUsage> DiskUsageAsync(string path, CancellationToken ct = default)
				=> _c.GetAsync($"/v1/fs/disk-usage?path={Q(path)}", MediaMindJsonContext.Default.DiskUsage, ct);

			public sealed class QuickAccessApi(MediaMindApiClient c)
			{
				public Task<QuickAccessList> ListAsync(CancellationToken ct = default)
					=> c.GetAsync("/v1/fs/quick-access", MediaMindJsonContext.Default.QuickAccessList, ct);

				public Task<QuickAccessList> PinAsync(string path, CancellationToken ct = default)
					=> c.PostAsync("/v1/fs/quick-access", new PathBody(path), MediaMindJsonContext.Default.PathBody, MediaMindJsonContext.Default.QuickAccessList, ct);

				public Task<QuickAccessList> UnpinAsync(string path, CancellationToken ct = default)
					=> c.DeleteAsync($"/v1/fs/quick-access?path={Q(path)}", MediaMindJsonContext.Default.QuickAccessList, ct);

				public Task<QuickAccessList> ReorderAsync(IReadOnlyList<string> paths, CancellationToken ct = default)
					=> c.PutAsync("/v1/fs/quick-access/reorder", new PathsBody(paths), MediaMindJsonContext.Default.PathsBody, MediaMindJsonContext.Default.QuickAccessList, ct);
			}

			public sealed class RecentApi(MediaMindApiClient c)
			{
				public Task<RecentFilesList> ListAsync(CancellationToken ct = default)
					=> c.GetAsync("/v1/fs/recent", MediaMindJsonContext.Default.RecentFilesList, ct);

				public Task<RecentFilesList> RecordAsync(string path, CancellationToken ct = default)
					=> c.PostAsync("/v1/fs/recent", new PathBody(path), MediaMindJsonContext.Default.PathBody, MediaMindJsonContext.Default.RecentFilesList, ct);
			}

			public sealed class SettingsApi(MediaMindApiClient c)
			{
				public Task<MediaMindSettings> GetAsync(CancellationToken ct = default)
					=> c.GetAsync("/v1/fs/settings", MediaMindJsonContext.Default.MediaMindSettings, ct);

				public Task<MediaMindSettings> UpdateAsync(MediaMindSettingsPatch patch, CancellationToken ct = default)
					=> c.PatchAsync("/v1/fs/settings", patch, MediaMindJsonContext.Default.MediaMindSettingsPatch, MediaMindJsonContext.Default.MediaMindSettings, ct);
			}

			public sealed class DiscoveryApi(MediaMindApiClient c)
			{
				public Task<List<DiscoverySuggestion>> SuggestionsAsync(CancellationToken ct = default)
					=> c.GetAsync("/v1/fs/discovery/suggestions", MediaMindJsonContext.Default.ListDiscoverySuggestion, ct);

				public Task<Library> RegisterAsync(string folder, CancellationToken ct = default)
					=> c.PostAsync("/v1/fs/discovery/register", new FolderBody(folder), MediaMindJsonContext.Default.FolderBody, MediaMindJsonContext.Default.Library, ct);

				public Task<OkResult> DismissAsync(string folder, CancellationToken ct = default)
					=> c.PostAsync("/v1/fs/discovery/dismiss", new FolderBody(folder), MediaMindJsonContext.Default.FolderBody, MediaMindJsonContext.Default.OkResult, ct);
			}
		}

		// -------------------------------------------------------------------
		// api.fsOps
		// -------------------------------------------------------------------

		public sealed class FsOpsApi(MediaMindApiClient c)
		{
			public Task<PathResult> NewFolderAsync(string parent, string? name = null, CancellationToken ct = default)
				=> c.PostAsync("/v1/fs/new-folder", new NewFolderBody(parent, name), MediaMindJsonContext.Default.NewFolderBody, MediaMindJsonContext.Default.PathResult, ct);

			public Task<PathResult> RenameAsync(string path, string newName, CancellationToken ct = default)
				=> c.PostAsync("/v1/fs/rename", new RenameBody(path, newName), MediaMindJsonContext.Default.RenameBody, MediaMindJsonContext.Default.PathResult, ct);

			public Task<ExecutionReport> DeleteAsync(IReadOnlyList<string> paths, bool permanent = false, CancellationToken ct = default)
				=> c.PostAsync("/v1/fs/delete", new DeletePathsBody(paths, permanent), MediaMindJsonContext.Default.DeletePathsBody, MediaMindJsonContext.Default.ExecutionReport, ct);

			public Task<ExecutionReport> MoveAsync(IReadOnlyList<string> sources, string dest, CancellationToken ct = default)
				=> c.PostAsync("/v1/fs/move", new MoveCopyBody(sources, dest), MediaMindJsonContext.Default.MoveCopyBody, MediaMindJsonContext.Default.ExecutionReport, ct);

			public Task<ExecutionReport> CopyAsync(IReadOnlyList<string> sources, string dest, CancellationToken ct = default)
				=> c.PostAsync("/v1/fs/copy", new MoveCopyBody(sources, dest), MediaMindJsonContext.Default.MoveCopyBody, MediaMindJsonContext.Default.ExecutionReport, ct);

			public Task<FsUndoResult> UndoAsync(CancellationToken ct = default)
				=> c.PostAsync("/v1/fs/undo", MediaMindJsonContext.Default.FsUndoResult, ct);

			public Task<FsRedoResult> RedoAsync(CancellationToken ct = default)
				=> c.PostAsync("/v1/fs/redo", MediaMindJsonContext.Default.FsRedoResult, ct);

			public Task<PathResult> CreateShortcutAsync(string target, string destFolder, string? name = null, CancellationToken ct = default)
				=> c.PostAsync("/v1/fs/create-shortcut", new CreateShortcutBody(target, destFolder, name), MediaMindJsonContext.Default.CreateShortcutBody, MediaMindJsonContext.Default.PathResult, ct);
		}

		// -------------------------------------------------------------------
		// api.scans / api.jobs
		// -------------------------------------------------------------------

		public sealed class ScansApi(MediaMindApiClient c)
		{
			// withDuplicates (faces scans): find duplicate files first, in the same job.
			public Task<JobSnapshot> StartAsync(string libraryId, string type = "dedupe", double nearThreshold = 5, string? providerId = null, CancellationToken ct = default, bool withDuplicates = false)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/scans", new ScanStartBody(type, nearThreshold, providerId, withDuplicates), MediaMindJsonContext.Default.ScanStartBody, MediaMindJsonContext.Default.JobSnapshot, ct);

			public Task<JobSnapshot> GetAsync(string libraryId, string jobId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/scans/{Q(jobId)}", MediaMindJsonContext.Default.JobSnapshot, ct);

			public Task<StatusResult> CancelAsync(string libraryId, string jobId, CancellationToken ct = default)
				=> c.DeleteAsync($"/v1/libraries/{Q(libraryId)}/scans/{Q(jobId)}", MediaMindJsonContext.Default.StatusResult, ct);
		}

		public sealed class JobsApi(MediaMindApiClient c)
		{
			public Task<JobSnapshot> GetAsync(string jobId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/jobs/{Q(jobId)}", MediaMindJsonContext.Default.JobSnapshot, ct);

			public Task<StatusResult> CancelAsync(string jobId, CancellationToken ct = default)
				=> c.DeleteAsync($"/v1/jobs/{Q(jobId)}", MediaMindJsonContext.Default.StatusResult, ct);
		}

		// -------------------------------------------------------------------
		// api.duplicates
		// -------------------------------------------------------------------

		public sealed class DuplicatesApi(MediaMindApiClient c)
		{
			public Task<DuplicatesOut> ListAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/duplicates", MediaMindJsonContext.Default.DuplicatesOut, ct);

			public Task<RecycleBinCheckResult> RecycleBinCheckAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/duplicates/recycle-bin-check", MediaMindJsonContext.Default.RecycleBinCheckResult, ct);

			public Task<UpdatedCountResult> ResolveAsync(string libraryId, IReadOnlyList<DuplicateResolution> resolutions, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/duplicates/resolutions", new DuplicatesResolveBody(resolutions), MediaMindJsonContext.Default.DuplicatesResolveBody, MediaMindJsonContext.Default.UpdatedCountResult, ct);

			public Task<ExecutionReport> ExecuteAsync(string libraryId, bool dryRun, int expectedTrashCount, bool permanent = false, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/duplicates/execute", new DuplicatesExecuteBody(dryRun, expectedTrashCount, permanent), MediaMindJsonContext.Default.DuplicatesExecuteBody, MediaMindJsonContext.Default.ExecutionReport, ct);

			/// <summary>
			/// Real deletion as a background job — track it to completion via the WS
			/// job broadcast (<see cref="MediaMindEngineService.JobEvents"/>) instead of
			/// awaiting completion here, same pattern as client.ts's executeJob.
			/// </summary>
			public Task<JobSnapshot> ExecuteJobAsync(string libraryId, int expectedTrashCount, bool permanent = false, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/duplicates/execute-job", new DuplicatesExecuteJobBody(expectedTrashCount, permanent), MediaMindJsonContext.Default.DuplicatesExecuteJobBody, MediaMindJsonContext.Default.JobSnapshot, ct);

			// "Not duplicates" for one group; it stays hidden after rescans unless its files change.
			public Task<OkResult> DismissGroupAsync(string libraryId, long groupId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/duplicates/groups/{groupId}/dismiss", MediaMindJsonContext.Default.OkResult, ct);

			public Task<DuplicatesConfirmResult> ConfirmAsync(string libraryId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/duplicates/confirm", MediaMindJsonContext.Default.DuplicatesConfirmResult, ct);

			public Task<DuplicatesResetDismissalsResult> ResetDismissalsAsync(string libraryId, CancellationToken ct = default)
				=> c.DeleteAsync($"/v1/libraries/{Q(libraryId)}/duplicates/dismissals", MediaMindJsonContext.Default.DuplicatesResetDismissalsResult, ct);

			public Task<byte[]> ThumbnailAsync(string libraryId, long memberId, int size = 256, CancellationToken ct = default)
				=> c.GetBytesAsync($"/v1/libraries/{Q(libraryId)}/duplicates/files/{memberId}/thumbnail?size={size}", ct);
		}

		// -------------------------------------------------------------------
		// api.providers
		// -------------------------------------------------------------------

		public sealed class ProvidersApi(MediaMindApiClient c)
		{
			public Task<List<Provider>> ListAsync(CancellationToken ct = default)
				=> c.GetAsync("/v1/providers", MediaMindJsonContext.Default.ListProvider, ct);

			public Task<JobSnapshot> DownloadAsync(string id, CancellationToken ct = default)
				=> c.PostAsync($"/v1/providers/{Q(id)}/download", new LicenseAcceptedBody(true), MediaMindJsonContext.Default.LicenseAcceptedBody, MediaMindJsonContext.Default.JobSnapshot, ct);
		}

		// -------------------------------------------------------------------
		// api.organize
		// -------------------------------------------------------------------

		public sealed class OrganizeApi(MediaMindApiClient c)
		{
			/// <summary>
			/// mode 'move' organizes in place (changes originals); 'copy' exports
			/// (leaves originals). groupScope 'all' copies a group photo into every
			/// named person's folder (export fan-out); 'prominent' routes to the
			/// dominant person only.
			/// </summary>
			public Task<OrganizePreview> PreviewAsync(string libraryId, string groupScope = "prominent", long? personId = null, CancellationToken ct = default)
				=> c.PostAsync(
					$"/v1/libraries/{Q(libraryId)}/organize/preview?group_scope={groupScope}" + (personId is not null ? $"&person_id={personId}" : string.Empty),
					MediaMindJsonContext.Default.OrganizePreview,
					ct);

			public Task<ExecutionReport> ExecuteAsync(
				string libraryId,
				bool dryRun,
				int? expectedPlanned = null,
				string? expectedPlanHash = null,
				IReadOnlyList<string>? excludedSources = null,
				string mode = "move",
				string groupScope = "prominent",
				long? personId = null,
				CancellationToken ct = default)
				=> c.PostAsync(
					$"/v1/libraries/{Q(libraryId)}/organize/execute",
					new OrganizeExecuteBody(dryRun, expectedPlanned, expectedPlanHash, excludedSources ?? [], mode, groupScope, personId),
					MediaMindJsonContext.Default.OrganizeExecuteBody,
					MediaMindJsonContext.Default.ExecutionReport,
					ct);

			/// <summary>
			/// Real execution as a background job — track it to completion via the WS
			/// job broadcast, same pattern as <see cref="DuplicatesApi.ExecuteJobAsync"/>.
			/// </summary>
			public Task<JobSnapshot> ExecuteJobAsync(
				string libraryId,
				int? expectedPlanned = null,
				string? expectedPlanHash = null,
				IReadOnlyList<string>? excludedSources = null,
				string mode = "move",
				string groupScope = "prominent",
				long? personId = null,
				CancellationToken ct = default)
				=> c.PostAsync(
					$"/v1/libraries/{Q(libraryId)}/organize/execute-job",
					new OrganizeExecuteBody(false, expectedPlanned, expectedPlanHash, excludedSources ?? [], mode, groupScope, personId),
					MediaMindJsonContext.Default.OrganizeExecuteBody,
					MediaMindJsonContext.Default.JobSnapshot,
					ct);

			public Task<OrganizeUndoResult> UndoAsync(string libraryId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/organize/undo", MediaMindJsonContext.Default.OrganizeUndoResult, ct);

			public Task<List<OrganizeAction>> AuditAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/organize/audit", MediaMindJsonContext.Default.ListOrganizeAction, ct);

			public Task<List<DuplicateLocationGroup>> DuplicateLocationsAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/organize/duplicate-locations", MediaMindJsonContext.Default.ListDuplicateLocationGroup, ct);

			public Task<ExecutionReport> PruneDuplicateLocationsAsync(string libraryId, IReadOnlyList<string> paths, bool dryRun, bool permanent = false, CancellationToken ct = default)
				=> c.PostAsync(
					$"/v1/libraries/{Q(libraryId)}/organize/duplicate-locations/prune",
					new PruneDuplicateLocationsBody(paths, dryRun, permanent),
					MediaMindJsonContext.Default.PruneDuplicateLocationsBody,
					MediaMindJsonContext.Default.ExecutionReport,
					ct);
		}

		// -------------------------------------------------------------------
		// api.pending / api.multiPerson
		// -------------------------------------------------------------------

		public sealed class PendingApi(MediaMindApiClient c)
		{
			public Task<List<PendingMatch>> ListAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/pending", MediaMindJsonContext.Default.ListPendingMatch, ct);

			// Only files the folder watcher picked up recently (Suggestions), not a scan's questions.
			public Task<List<PendingMatch>> ListArrivedAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/pending?arrived=true", MediaMindJsonContext.Default.ListPendingMatch, ct);

			public Task<UpdatedCountResult> DecideAsync(string libraryId, IReadOnlyList<PendingDecisionItem> decisions, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/pending/decisions", new PendingDecideBody(decisions), MediaMindJsonContext.Default.PendingDecideBody, MediaMindJsonContext.Default.UpdatedCountResult, ct);
		}

		public sealed class MultiPersonApi(MediaMindApiClient c)
		{
			public Task<List<MultiPersonFile>> ListAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/multi-person", MediaMindJsonContext.Default.ListMultiPersonFile, ct);

			public Task<UpdatedCountResult> SetChoicesAsync(string libraryId, IReadOnlyList<RouteChoice> choices, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/route-choices", new RouteChoicesBody(choices), MediaMindJsonContext.Default.RouteChoicesBody, MediaMindJsonContext.Default.UpdatedCountResult, ct);
		}

		// -------------------------------------------------------------------
		// api.persons
		// -------------------------------------------------------------------

		public sealed class PersonsApi(MediaMindApiClient c)
		{
			public Task<PersonsOut> ListAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/persons", MediaMindJsonContext.Default.PersonsOut, ct);

			public Task<PeopleTreeOut> TreeAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/people-tree", MediaMindJsonContext.Default.PeopleTreeOut, ct);

			public Task<RecurringUnnamed> RecurringUnnamedAsync(string libraryId, int? minAppearances = null, CancellationToken ct = default)
				=> c.GetAsync(
					$"/v1/libraries/{Q(libraryId)}/recurring-unnamed" + (minAppearances is not null ? $"?min_appearances={minAppearances}" : string.Empty),
					MediaMindJsonContext.Default.RecurringUnnamed,
					ct);

			public Task<OkResult> RenameAsync(string libraryId, long personId, string? name, CancellationToken ct = default)
				=> c.PatchAsync($"/v1/libraries/{Q(libraryId)}/persons/{personId}", new NameBody(name), MediaMindJsonContext.Default.NameBody, MediaMindJsonContext.Default.OkResult, ct);

			public Task<OkResult> MergeAsync(string libraryId, long sourceId, long targetId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/persons/merge", new PersonMergeBody(sourceId, targetId), MediaMindJsonContext.Default.PersonMergeBody, MediaMindJsonContext.Default.OkResult, ct);

			public Task<List<MergeSuggestion>> MergeSuggestionsAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/persons/merge-suggestions", MediaMindJsonContext.Default.ListMergeSuggestion, ct);

			public Task<OkResult> DismissMergeSuggestionAsync(string libraryId, long personAId, long personBId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/persons/merge-suggestions/dismiss", new PersonMergeDismissBody(personAId, personBId), MediaMindJsonContext.Default.PersonMergeDismissBody, MediaMindJsonContext.Default.OkResult, ct);

			public Task<List<PersonMediaItem>> MediaAsync(string libraryId, long personId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/persons/{personId}/media", MediaMindJsonContext.Default.ListPersonMediaItem, ct);

			public Task<byte[]> FaceThumbnailAsync(string libraryId, long faceId, int size = 192, CancellationToken ct = default)
				=> c.GetBytesAsync($"/v1/libraries/{Q(libraryId)}/faces/{faceId}/thumbnail?size={size}", ct);

			public Task<RejectFaceResult> RejectFaceAsync(string libraryId, long faceId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/faces/{faceId}/reject", MediaMindJsonContext.Default.RejectFaceResult, ct);

			public Task<OkResult> ReassignFaceAsync(string libraryId, long faceId, long personId, CancellationToken ct = default)
				=> c.PatchAsync($"/v1/libraries/{Q(libraryId)}/faces/{faceId}/person", new PersonIdBody(personId), MediaMindJsonContext.Default.PersonIdBody, MediaMindJsonContext.Default.OkResult, ct);

			public Task<MaterializePreview> MaterializePreviewAsync(string libraryId, long personId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/persons/{personId}/materialize/preview", MediaMindJsonContext.Default.MaterializePreview, ct);

			public Task<ExecutionReport> MaterializeAsync(string libraryId, long personId, MaterializeBody body, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/persons/{personId}/materialize", body, MediaMindJsonContext.Default.MaterializeBody, MediaMindJsonContext.Default.ExecutionReport, ct);

			public Task<PrimaryFolderResult> SetPrimaryFolderAsync(string libraryId, long personId, string? path, CancellationToken ct = default)
				=> c.PutAsync($"/v1/libraries/{Q(libraryId)}/persons/{personId}/primary-folder", new NullablePathBody(path), MediaMindJsonContext.Default.NullablePathBody, MediaMindJsonContext.Default.PrimaryFolderResult, ct);
		}

		// -------------------------------------------------------------------
		// api.duplicateFlags
		// -------------------------------------------------------------------

		// -------------------------------------------------------------------
		// api.unprocessed: files a scan could not process, and hand labels
		// -------------------------------------------------------------------

		public sealed class UnprocessedApi(MediaMindApiClient c)
		{
			public Task<List<UnprocessedFile>> ListAsync(string libraryId, string? under = null, CancellationToken ct = default)
				=> c.GetAsync(
					$"/v1/libraries/{Q(libraryId)}/unprocessed" + (string.IsNullOrEmpty(under) ? string.Empty : $"?under={Q(under)}"),
					MediaMindJsonContext.Default.ListUnprocessedFile,
					ct);

			public Task<OkResult> TagAsync(string libraryId, string path, long personId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/unprocessed/tag", new UnprocessedTagBody(path, personId), MediaMindJsonContext.Default.UnprocessedTagBody, MediaMindJsonContext.Default.OkResult, ct);

			public Task<OkResult> UntagAsync(string libraryId, string path, long personId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/unprocessed/untag", new UnprocessedTagBody(path, personId), MediaMindJsonContext.Default.UnprocessedTagBody, MediaMindJsonContext.Default.OkResult, ct);
		}

		public sealed class TeachApi(MediaMindApiClient c)
		{
			public Task<TeachFacesResult> FacesAsync(string libraryId, string? under, bool unnamedOnly, bool includeBackground, int limit = 600, CancellationToken ct = default)
				=> c.GetAsync(
					$"/v1/libraries/{Q(libraryId)}/teach/faces?limit={limit}&unnamed={(unnamedOnly ? "true" : "false")}&include_background={(includeBackground ? "true" : "false")}"
						+ (string.IsNullOrEmpty(under) ? string.Empty : $"&under={Q(under)}"),
					MediaMindJsonContext.Default.TeachFacesResult,
					ct);

			public Task<List<TeachPerson>> PeopleAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/teach/people", MediaMindJsonContext.Default.ListTeachPerson, ct);

			public Task<TeachExamplesResult> AddExamplesAsync(string libraryId, IReadOnlyList<long> faceIds, long? personId, string? name, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/teach/examples", new TeachExamplesBody(faceIds, personId, name), MediaMindJsonContext.Default.TeachExamplesBody, MediaMindJsonContext.Default.TeachExamplesResult, ct);

			public Task<TeachStats> StatsAsync(string libraryId, string? under, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/teach/stats" + (string.IsNullOrEmpty(under) ? string.Empty : $"?under={Q(under)}"), MediaMindJsonContext.Default.TeachStats, ct);

			public Task<PrimaryLocationResult> SetPrimaryLocationAsync(string libraryId, long personId, string? path, CancellationToken ct = default)
				=> c.PutAsync($"/v1/libraries/{Q(libraryId)}/teach/people/{personId}/primary-location", new PrimaryLocationBody(path), MediaMindJsonContext.Default.PrimaryLocationBody, MediaMindJsonContext.Default.PrimaryLocationResult, ct);

			public Task<PersonMovePlan> MovePlanAsync(string libraryId, long personId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/teach/people/{personId}/move-plan", MediaMindJsonContext.Default.PersonMovePlan, ct);

			// The same plan as a job (progress per folder read); the plan is the job's result.
			public Task<JobSnapshot> StartMovePlanAsync(string libraryId, long personId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/teach/people/{personId}/move-plan", MediaMindJsonContext.Default.JobSnapshot, ct);

			// Starts the move as a job (progress and the result arrive through the engine's job updates).
			public Task<JobSnapshot> MoveAsync(string libraryId, long personId, string planHash, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/teach/people/{personId}/move", new PersonMoveBody(planHash), MediaMindJsonContext.Default.PersonMoveBody, MediaMindJsonContext.Default.JobSnapshot, ct);

			public Task<List<NoFaceFile>> NoFacesAsync(string libraryId, string? under = null, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/teach/no-faces" + (string.IsNullOrEmpty(under) ? string.Empty : $"?under={Q(under)}"), MediaMindJsonContext.Default.ListNoFaceFile, ct);

			public Task<List<GroupQuestion>> GroupsAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/teach/groups", MediaMindJsonContext.Default.ListGroupQuestion, ct);

			public Task<GroupPlaceResult> PlaceGroupAsync(string libraryId, GroupPlaceBody body, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/teach/groups/place", body, MediaMindJsonContext.Default.GroupPlaceBody, MediaMindJsonContext.Default.GroupPlaceResult, ct);

			public Task<byte[]> FileThumbnailAsync(string libraryId, string path, int size = 256, CancellationToken ct = default)
				=> c.GetBytesAsync($"/v1/libraries/{Q(libraryId)}/files/thumbnail?path={Q(path)}&size={size}", ct);

			public Task<AutoFileLibraries> AutoFileLibrariesAsync(CancellationToken ct = default)
				=> c.GetAsync("/v1/auto-file", MediaMindJsonContext.Default.AutoFileLibraries, ct);

			public Task<AutoFileBody> AutoFileAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/auto-file", MediaMindJsonContext.Default.AutoFileBody, ct);

			public Task<AutoFileBody> SetAutoFileAsync(string libraryId, bool enabled, CancellationToken ct = default)
				=> c.PutAsync($"/v1/libraries/{Q(libraryId)}/auto-file", new AutoFileBody(enabled), MediaMindJsonContext.Default.AutoFileBody, MediaMindJsonContext.Default.AutoFileBody, ct);

			// "member": belongs to this folder; "guest": only in a few of its pictures.
			public Task<TeachMembershipResult> SetMembershipAsync(string libraryId, long personId, string membership, CancellationToken ct = default)
				=> c.PutAsync($"/v1/libraries/{Q(libraryId)}/teach/people/{personId}/membership", new TeachMembershipBody(membership), MediaMindJsonContext.Default.TeachMembershipBody, MediaMindJsonContext.Default.TeachMembershipResult, ct);

			public Task<TeachRemoveResult> RemoveExamplesAsync(string libraryId, IReadOnlyList<long> faceIds, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/teach/examples/remove", new TeachRemoveBody(faceIds), MediaMindJsonContext.Default.TeachRemoveBody, MediaMindJsonContext.Default.TeachRemoveResult, ct);

			public Task<byte[]> FrameAsync(string libraryId, long faceId, int size = 1600, CancellationToken ct = default)
				=> c.GetBytesAsync($"/v1/libraries/{Q(libraryId)}/teach/faces/{faceId}/frame?size={size}", ct);

			public Task<TeachApplyResult> ApplyAsync(string libraryId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/teach/apply", MediaMindJsonContext.Default.TeachApplyResult, ct);

			// The same sort as a job (progress per folder read); the TeachApplyResult is its result.
			public Task<JobSnapshot> StartApplyAsync(string libraryId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/teach/apply-job", MediaMindJsonContext.Default.JobSnapshot, ct);

			// Drops index rows of files that are gone from disk; never touches a file.
			public Task<ForgetMissingResult> ForgetMissingAsync(string libraryId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/files/forget-missing", MediaMindJsonContext.Default.ForgetMissingResult, ct);
		}

		public sealed class DuplicateFlagsApi(MediaMindApiClient c)
		{
			public Task<List<DuplicateFlag>> ListAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/duplicate-flags", MediaMindJsonContext.Default.ListDuplicateFlag, ct);

			public Task<StatusResult> DismissAsync(string libraryId, long flagId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/duplicate-flags/{flagId}/dismiss", MediaMindJsonContext.Default.StatusResult, ct);
		}

		// -------------------------------------------------------------------
		// api.bindings
		// -------------------------------------------------------------------

		public sealed class BindingsApi(MediaMindApiClient c)
		{
			public Task<RefreshSuggestionsResult> RefreshAsync(string libraryId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/bindings/refresh", MediaMindJsonContext.Default.RefreshSuggestionsResult, ct);

			public Task<BindingsSuggestionsResult> SuggestionsAsync(string libraryId, string status = "pending", CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/bindings/suggestions?status={status}", MediaMindJsonContext.Default.BindingsSuggestionsResult, ct);

			public Task<FolderBinding> AcceptAsync(string libraryId, long suggestionId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/bindings/suggestions/{suggestionId}/accept", MediaMindJsonContext.Default.FolderBinding, ct);

			public Task<OkResult> DismissAsync(string libraryId, long suggestionId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/bindings/suggestions/{suggestionId}/dismiss", MediaMindJsonContext.Default.OkResult, ct);

			public Task<BindingsListResult> ListAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/bindings", MediaMindJsonContext.Default.BindingsListResult, ct);

			public Task<OkResult> ReleaseAsync(string libraryId, long bindingId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/bindings/{bindingId}/release", MediaMindJsonContext.Default.OkResult, ct);

			public Task<FolderBinding> SetOutliersAsync(string libraryId, long bindingId, IReadOnlyList<long> fileIds, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/bindings/{bindingId}/outliers", new FileIdsBody(fileIds), MediaMindJsonContext.Default.FileIdsBody, MediaMindJsonContext.Default.FolderBinding, ct);

			public Task<SuggestionMergePreview> MergePreviewAsync(string libraryId, long suggestionId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/bindings/suggestions/{suggestionId}/merge/preview", MediaMindJsonContext.Default.SuggestionMergePreview, ct);

			public Task<ExecutionReport> MergeAsync(string libraryId, long suggestionId, SuggestionMergeBody? body = null, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/bindings/suggestions/{suggestionId}/merge", body ?? new SuggestionMergeBody(), MediaMindJsonContext.Default.SuggestionMergeBody, MediaMindJsonContext.Default.ExecutionReport, ct);
		}

		// -------------------------------------------------------------------
		// api.facesPrep
		// -------------------------------------------------------------------

		public sealed class FacesPrepApi(MediaMindApiClient c)
		{
			public Task<FacesPrep> GetAsync(string libraryId, CancellationToken ct = default)
				=> c.GetAsync($"/v1/libraries/{Q(libraryId)}/faces/prep", MediaMindJsonContext.Default.FacesPrep, ct);

			public Task<ExecutionReport> CreateUnsortedAsync(string libraryId, bool dryRun, CancellationToken ct = default)
				=> c.PostAsync($"/v1/libraries/{Q(libraryId)}/faces/prep/create-unsorted", new DryRunBody(dryRun), MediaMindJsonContext.Default.DryRunBody, MediaMindJsonContext.Default.ExecutionReport, ct);
		}

		// -------------------------------------------------------------------
		// api.globalPeople
		// -------------------------------------------------------------------

		// -------------------------------------------------------------------
		// api.peopleView — cross-library People overview, pins, collections
		// -------------------------------------------------------------------

		public sealed class PeopleViewApi(MediaMindApiClient c)
		{
			public Task<PeopleOverview> OverviewAsync(CancellationToken ct = default)
				=> c.GetAsync("/v1/people-view/overview", MediaMindJsonContext.Default.PeopleOverview, ct);

			public Task<OkResult> PinAsync(string key, CancellationToken ct = default)
				=> c.PostAsync("/v1/people-view/pins", new PeoplePinBody(key), MediaMindJsonContext.Default.PeoplePinBody, MediaMindJsonContext.Default.OkResult, ct);

			public Task<OkResult> UnpinAsync(IReadOnlyList<string> keys, CancellationToken ct = default)
				=> c.PostAsync("/v1/people-view/unpin", new PeopleKeysBody(keys), MediaMindJsonContext.Default.PeopleKeysBody, MediaMindJsonContext.Default.OkResult, ct);

			// The best croppable face of one person; 410 Gone means the engine found it is not a person at all.
			public Task<byte[]> PersonThumbnailAsync(string libraryId, long personId, int size = 160, CancellationToken ct = default)
				=> c.GetBytesAsync($"/v1/people-view/persons/{Q(libraryId)}/{personId}/thumbnail?size={size}", ct);

			// Background sweep: the engine checks these persons now and reports the ones that are not people.
			public Task<PeopleVerifyResult> VerifyAsync(IReadOnlyList<string> keys, CancellationToken ct = default)
				=> c.PostAsync("/v1/people-view/verify", new PeopleKeysBody(keys), MediaMindJsonContext.Default.PeopleKeysBody, MediaMindJsonContext.Default.PeopleVerifyResult, ct);

			public Task<OkResult> HideAsync(IReadOnlyList<string> keys, CancellationToken ct = default)
				=> c.PostAsync("/v1/people-view/hide", new PeopleKeysBody(keys), MediaMindJsonContext.Default.PeopleKeysBody, MediaMindJsonContext.Default.OkResult, ct);

			public Task<OkResult> UnhideAsync(IReadOnlyList<string> keys, CancellationToken ct = default)
				=> c.PostAsync("/v1/people-view/unhide", new PeopleKeysBody(keys), MediaMindJsonContext.Default.PeopleKeysBody, MediaMindJsonContext.Default.OkResult, ct);

			public Task<OkResult> MergeAsync(IReadOnlyList<string> sourceKeys, IReadOnlyList<string> targetKeys, CancellationToken ct = default)
				=> c.PostAsync("/v1/people-view/merge", new PeopleMergeBody(sourceKeys, targetKeys), MediaMindJsonContext.Default.PeopleMergeBody, MediaMindJsonContext.Default.OkResult, ct);

			public Task<PeopleCollection> CreateCollectionAsync(string name, CancellationToken ct = default)
				=> c.PostAsync("/v1/people-view/collections", new PeopleCollectionNameBody(name), MediaMindJsonContext.Default.PeopleCollectionNameBody, MediaMindJsonContext.Default.PeopleCollection, ct);

			public Task<OkResult> RenameCollectionAsync(string id, string name, CancellationToken ct = default)
				=> c.PatchAsync($"/v1/people-view/collections/{Q(id)}", new PeopleCollectionNameBody(name), MediaMindJsonContext.Default.PeopleCollectionNameBody, MediaMindJsonContext.Default.OkResult, ct);

			public Task<OkResult> DeleteCollectionAsync(string id, CancellationToken ct = default)
				=> c.DeleteAsync($"/v1/people-view/collections/{Q(id)}", MediaMindJsonContext.Default.OkResult, ct);

			public Task<OkResult> AddToCollectionAsync(string id, IReadOnlyList<string> keys, CancellationToken ct = default)
				=> c.PostAsync($"/v1/people-view/collections/{Q(id)}/members", new PeopleKeysBody(keys), MediaMindJsonContext.Default.PeopleKeysBody, MediaMindJsonContext.Default.OkResult, ct);

			public Task<OkResult> RemoveFromCollectionsAsync(IReadOnlyList<string> keys, CancellationToken ct = default)
				=> c.PostAsync("/v1/people-view/collections/remove-members", new PeopleKeysBody(keys), MediaMindJsonContext.Default.PeopleKeysBody, MediaMindJsonContext.Default.OkResult, ct);
		}

		public sealed class GlobalPeopleApi(MediaMindApiClient c)
		{
			public Task<List<GlobalPerson>> ListAsync(CancellationToken ct = default)
				=> c.GetAsync("/v1/global/people", MediaMindJsonContext.Default.ListGlobalPerson, ct);

			public Task<GlobalPerson> CreateAsync(string name, CancellationToken ct = default)
				=> c.PostAsync("/v1/global/people", new NameRequiredBody(name), MediaMindJsonContext.Default.NameRequiredBody, MediaMindJsonContext.Default.GlobalPerson, ct);

			public Task<OkResult> RenameAsync(long id, string name, CancellationToken ct = default)
				=> c.PatchAsync($"/v1/global/people/{id}", new NameRequiredBody(name), MediaMindJsonContext.Default.NameRequiredBody, MediaMindJsonContext.Default.OkResult, ct);

			public Task<OkResult> RemoveAsync(long id, CancellationToken ct = default)
				=> c.DeleteAsync($"/v1/global/people/{id}", MediaMindJsonContext.Default.OkResult, ct);

			public Task<PrimaryLocationResult> SetPrimaryLocationAsync(long id, string? path, CancellationToken ct = default)
				=> c.PutAsync($"/v1/global/people/{id}/primary-location", new NullablePathBody(path), MediaMindJsonContext.Default.NullablePathBody, MediaMindJsonContext.Default.PrimaryLocationResult, ct);

			public Task<OkResult> LinkAsync(long globalPersonId, string libraryId, long localPersonId, CancellationToken ct = default)
				=> c.PostAsync($"/v1/global/people/{globalPersonId}/link", new GlobalLinkBody(libraryId, localPersonId), MediaMindJsonContext.Default.GlobalLinkBody, MediaMindJsonContext.Default.OkResult, ct);

			public Task<OkResult> UnlinkAsync(string libraryId, long localPersonId, CancellationToken ct = default)
				=> c.PostAsync("/v1/global/people/unlink", new GlobalLinkBody(libraryId, localPersonId), MediaMindJsonContext.Default.GlobalLinkBody, MediaMindJsonContext.Default.OkResult, ct);

			public Task<List<GlobalLinkSuggestion>> LinkSuggestionsAsync(CancellationToken ct = default)
				=> c.GetAsync("/v1/global/link-suggestions", MediaMindJsonContext.Default.ListGlobalLinkSuggestion, ct);

			public Task<OkResult> AcceptLinkSuggestionAsync(GlobalLinkSuggestionPair pair, CancellationToken ct = default)
				=> c.PostAsync("/v1/global/link-suggestions/link", pair, MediaMindJsonContext.Default.GlobalLinkSuggestionPair, MediaMindJsonContext.Default.OkResult, ct);

			public Task<OkResult> DismissLinkSuggestionAsync(GlobalLinkSuggestionPair pair, CancellationToken ct = default)
				=> c.PostAsync("/v1/global/link-suggestions/dismiss", pair, MediaMindJsonContext.Default.GlobalLinkSuggestionPair, MediaMindJsonContext.Default.OkResult, ct);

			public Task<List<GlobalMoveSuggestionGroup>> MoveSuggestionsAsync(CancellationToken ct = default)
				=> c.GetAsync("/v1/global/move-suggestions", MediaMindJsonContext.Default.ListGlobalMoveSuggestionGroup, ct);

			public Task<OkResult> DismissMoveSuggestionAsync(GlobalMoveSuggestionDismiss body, CancellationToken ct = default)
				=> c.PostAsync("/v1/global/move-suggestions/dismiss", body, MediaMindJsonContext.Default.GlobalMoveSuggestionDismiss, MediaMindJsonContext.Default.OkResult, ct);

			public Task<GlobalMoveExecuteReport> ExecuteMoveAsync(GlobalMoveExecuteBody body, CancellationToken ct = default)
				=> c.PostAsync("/v1/global/move-suggestions/execute", body, MediaMindJsonContext.Default.GlobalMoveExecuteBody, MediaMindJsonContext.Default.GlobalMoveExecuteReport, ct);

			public Task<GlobalMoveUndoInfo> UndoableMoveAsync(CancellationToken ct = default)
				=> c.GetAsync("/v1/global/moves/undoable", MediaMindJsonContext.Default.GlobalMoveUndoInfo, ct);

			public Task<ExecutionReport> UndoMoveAsync(CancellationToken ct = default)
				=> c.PostAsync("/v1/global/moves/undo", MediaMindJsonContext.Default.ExecutionReport, ct);
		}
	}
}

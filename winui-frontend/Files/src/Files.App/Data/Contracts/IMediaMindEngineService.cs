// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Services.MediaMind;
using System.Net.Http;

namespace Files.App.Data.Contracts
{
	/// <summary>
	/// Spawns and talks to the MediaMind Python engine (localhost HTTP + WebSocket,
	/// token-authenticated), reproducing the Electron bridge in
	/// <c>app/src/main/backend.ts</c> / <c>app/src/renderer/src/api/{client,progress}.ts</c>.
	/// </summary>
	public interface IMediaMindEngineService
	{
		/// <summary>
		/// Gets the HTTP client bound to the running engine (base address + token header preset).
		/// Null until <see cref="EnsureStartedAsync"/> has completed successfully.
		/// </summary>
		HttpClient? Client { get; }

		/// <summary>
		/// Gets the typed API client wrapping <see cref="Client"/>. Null until
		/// <see cref="EnsureStartedAsync"/> has completed successfully.
		/// </summary>
		MediaMindApiClient? Api { get; }

		/// <summary>
		/// Raised for every <c>msg_type: "job"</c> broadcast on <c>WS /v1/progress</c> —
		/// scan/dedupe/organize job state, on the same connection for as long as the
		/// engine is running (auto-reconnects with backoff on drop).
		/// </summary>
		event EventHandler<JobSnapshot>? JobUpdated;

		/// <summary>
		/// Spawns the engine if it isn't already running, waits for it to report its port, and
		/// waits for its health check to pass. Safe to call more than once.
		/// </summary>
		/// <returns><see langword="true"/> if the engine is up and healthy.</returns>
		Task<bool> EnsureStartedAsync(CancellationToken cancellationToken);

		/// <summary>
		/// Force-kills the engine process tree, mirroring backend.ts's <c>taskkill /T /F</c> use
		/// (a lingering child would otherwise block the updater).
		/// </summary>
		void Stop();
	}
}

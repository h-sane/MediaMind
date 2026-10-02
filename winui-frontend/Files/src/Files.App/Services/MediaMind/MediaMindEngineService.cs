// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Microsoft.Extensions.Logging;
using System.Net.Http;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Files.App.Services.MediaMind
{
	/// <summary>
	/// Spawns the MediaMind engine (dev: venv <c>python -m mediamind</c>; packaged: the
	/// PyInstaller <c>mediamind.exe</c> shipped next to the app install dir) and exposes
	/// its HTTP + WS surface.
	/// </summary>
	internal sealed partial class MediaMindEngineService : IMediaMindEngineService
	{
		private const string TokenHeaderName = "X-MediaMind-Token";
		private static readonly TimeSpan StartupTimeout = TimeSpan.FromSeconds(30);
		private static readonly TimeSpan ProgressReconnectMinDelay = TimeSpan.FromMilliseconds(500);
		private static readonly TimeSpan ProgressReconnectMaxDelay = TimeSpan.FromSeconds(5);

		[GeneratedRegex(@"MEDIAMIND_PORT=(\d+)")]
		private static partial Regex PortLineRegex();

		private readonly ILogger<MediaMindEngineService> _logger;
		private readonly SemaphoreSlim _startLock = new(1, 1);
		private Process? _process;
		private CancellationTokenSource? _progressCts;

		public HttpClient? Client { get; private set; }

		public MediaMindApiClient? Api { get; private set; }

		public event EventHandler<JobSnapshot>? JobUpdated;

		public MediaMindEngineService(ILogger<MediaMindEngineService> logger)
		{
			_logger = logger;
		}

		public async Task<bool> EnsureStartedAsync(CancellationToken cancellationToken)
		{
			if (Client is not null)
				return true;

			await _startLock.WaitAsync(cancellationToken);
			try
			{
				if (Client is not null)
					return true;

				var token = RandomNumberGenerator.GetHexString(64);
				var (fileName, arguments) = ResolveEngineCommand();

				var startInfo = new ProcessStartInfo(fileName)
				{
					UseShellExecute = false,
					RedirectStandardOutput = true,
					RedirectStandardError = true,
					CreateNoWindow = true,
				};
				foreach (var arg in arguments)
					startInfo.ArgumentList.Add(arg);
				startInfo.EnvironmentVariables["MEDIAMIND_TOKEN"] = token;

				var process = new Process { StartInfo = startInfo };
				process.ErrorDataReceived += (_, e) =>
				{
					// Fires on a ThreadPool I/O thread; keep it exception-proof so a logging
					// hiccup can't escape into an unhandled-exception path.
					if (e.Data is not null)
						SafetyExtensions.IgnoreExceptions(() => _logger.LogInformation("[engine:stderr] {Line}", e.Data));
				};

				if (!process.Start())
				{
					_logger.LogError("Failed to start the MediaMind engine process.");
					return false;
				}

				process.BeginErrorReadLine();
				_process = process;

				var port = await ReadPortAsync(process, cancellationToken);
				if (port is null)
				{
					_logger.LogError("MediaMind engine did not report a port within {Timeout}.", StartupTimeout);
					return false;
				}

				// __main__.py starts uvicorn with its default 5s keep-alive timeout, but
				// SocketsHttpHandler's default pooled-connection idle timeout is much longer
				// (60s) — a request issued after 5-60s of client-side idle reuses a
				// connection the server already closed, surfacing as a SocketException(995)
				// "operation aborted" deep inside HttpClient.SendAsync (e.g. Scan for People
				// after sitting on a page for a minute). Evicting idle connections faster
				// than the server does removes the race instead of retrying around it.
				var handler = new SocketsHttpHandler { PooledConnectionIdleTimeout = TimeSpan.FromSeconds(3) };
				var client = new HttpClient(handler) { BaseAddress = new Uri($"http://127.0.0.1:{port}/") };
				client.DefaultRequestHeaders.Add(TokenHeaderName, token);

				if (!await WaitForHealthAsync(client, cancellationToken))
				{
					_logger.LogError("MediaMind engine health check timed out.");
					client.Dispose();
					return false;
				}

				Client = client;
				Api = new MediaMindApiClient(client);
				_logger.LogInformation("MediaMind engine ready on 127.0.0.1:{Port}.", port);

				_progressCts = new CancellationTokenSource();
				_ = Task.Run(() => RunProgressSocketAsync(port.Value, token, _progressCts.Token), CancellationToken.None);

				return true;
			}
			catch (Exception ex)
			{
				// This runs as a fire-and-forget startup task; an escaped exception here would
				// otherwise surface as an unobserved task exception.
				_logger.LogError(ex, "MediaMind engine failed to start.");
				return false;
			}
			finally
			{
				_startLock.Release();
			}
		}

		public void Stop()
		{
			SafetyExtensions.IgnoreExceptions(() => _progressCts?.Cancel());
			_progressCts?.Dispose();
			_progressCts = null;

			if (_process is { HasExited: false } process)
				SafetyExtensions.IgnoreExceptions(() => process.Kill(entireProcessTree: true));

			Api = null;
			Client?.Dispose();
			Client = null;
			_process = null;
		}

		/// <summary>
		/// Dev = venv <c>python -m mediamind</c> (via <c>MEDIAMIND_PYTHON</c>, falling back
		/// to <c>python</c> on PATH). Packaged = the PyInstaller one-folder exe shipped
		/// next to the app's install dir at <c>engine/mediamind.exe</c> (today
		/// electron-builder ships the same one-folder build to
		/// <c>resources/engine/mediamind.exe</c> — MSIX packaging carries it the same way,
		/// see BLOCK5_UI_BLUEPRINT.md §5 open question 1). The bundled exe wins when present
		/// so a packaged install never depends on the machine having a Python venv.
		/// </summary>
		private static (string FileName, string[] Arguments) ResolveEngineCommand()
		{
			var bundledExe = SystemIO.Path.Combine(AppContext.BaseDirectory, "engine", "mediamind.exe");
			if (SystemIO.File.Exists(bundledExe))
				return (bundledExe, Array.Empty<string>());

			var python = Environment.GetEnvironmentVariable("MEDIAMIND_PYTHON") ?? "python";
			return (python, new[] { "-m", "mediamind" });
		}

		private async Task<int?> ReadPortAsync(Process process, CancellationToken cancellationToken)
		{
			using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
			cts.CancelAfter(StartupTimeout);

			try
			{
				while (true)
				{
					var line = await process.StandardOutput.ReadLineAsync(cts.Token);
					// Null means stdout closed, i.e. the process exited before reporting a port.
					if (line is null)
						return null;

					var match = PortLineRegex().Match(line);
					if (match.Success)
						return int.Parse(match.Groups[1].Value);
				}
			}
			catch (OperationCanceledException)
			{
				return null;
			}
		}

		private static async Task<bool> WaitForHealthAsync(HttpClient client, CancellationToken cancellationToken)
		{
			using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
			cts.CancelAfter(StartupTimeout);

			while (!cts.IsCancellationRequested)
			{
				try
				{
					var response = await client.GetAsync("v1/health", cts.Token);
					if (response.IsSuccessStatusCode)
						return true;
				}
				catch (Exception) when (!cts.IsCancellationRequested)
				{
					// Not up yet.
				}

				try
				{
					await Task.Delay(250, cts.Token);
				}
				catch (OperationCanceledException)
				{
					break;
				}
			}

			return false;
		}

		/// <summary>
		/// Subscribes to <c>WS /v1/progress</c> and raises <see cref="JobUpdated"/> for every
		/// <c>msg_type: "job"</c> broadcast, auto-reconnecting with exponential backoff on
		/// drop. Mirrors <c>app/src/renderer/src/api/progress.ts</c>'s <c>useProgressSocket</c>.
		/// </summary>
		private async Task RunProgressSocketAsync(int port, string token, CancellationToken cancellationToken)
		{
			var attempt = 0;
			var uri = new Uri($"ws://127.0.0.1:{port}/v1/progress?token={Uri.EscapeDataString(token)}");

			while (!cancellationToken.IsCancellationRequested)
			{
				try
				{
					using var socket = new ClientWebSocket();
					await socket.ConnectAsync(uri, cancellationToken);
					attempt = 0;

					await ReceiveLoopAsync(socket, cancellationToken);
				}
				catch (Exception) when (!cancellationToken.IsCancellationRequested)
				{
					// Connection dropped or refused — fall through to reconnect with backoff,
					// same as progress.ts (the engine may be mid-restart).
				}

				if (cancellationToken.IsCancellationRequested)
					break;

				var delayMs = Math.Min(ProgressReconnectMinDelay.TotalMilliseconds * (1 << Math.Min(attempt, 4)), ProgressReconnectMaxDelay.TotalMilliseconds);
				attempt++;

				try
				{
					await Task.Delay(TimeSpan.FromMilliseconds(delayMs), cancellationToken);
				}
				catch (OperationCanceledException)
				{
					break;
				}
			}
		}

		private async Task ReceiveLoopAsync(ClientWebSocket socket, CancellationToken cancellationToken)
		{
			var buffer = new byte[16 * 1024];

			while (socket.State is WebSocketState.Open && !cancellationToken.IsCancellationRequested)
			{
				using var message = new SystemIO.MemoryStream();
				WebSocketReceiveResult result;
				do
				{
					result = await socket.ReceiveAsync(buffer, cancellationToken);
					if (result.MessageType is WebSocketMessageType.Close)
						return;

					message.Write(buffer, 0, result.Count);
				}
				while (!result.EndOfMessage);

				HandleProgressMessage(Encoding.UTF8.GetString(message.ToArray()));
			}
		}

		private void HandleProgressMessage(string json)
		{
			try
			{
				using var doc = JsonDocument.Parse(json);
				if (!doc.RootElement.TryGetProperty("msg_type", out var msgType) || msgType.GetString() is not "job")
					return;

				var snapshot = doc.RootElement.Deserialize(MediaMindJsonContext.Default.JobSnapshot);
				if (snapshot is not null)
					JobUpdated?.Invoke(this, snapshot);
			}
			catch (JsonException)
			{
				// Malformed message — ignore, mirrors progress.ts's try/catch.
			}
		}
	}
}

// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Data.Contracts;
using Files.App.Utils.StatusCenter;
using Files.App.ViewModels.UserControls;

namespace Files.App.Services.MediaMind
{
	/// <summary>
	/// Bridges MediaMind engine job progress (<see cref="IMediaMindEngineService.JobUpdated"/>,
	/// fed by WS /v1/progress) into Files' existing StatusCenter, so face scans, dedupe scans,
	/// and consolidations render in the same "ongoing operations" flyout as native file ops
	/// (BLOCK5_UI_BLUEPRINT.md §2) instead of a parallel progress UI.
	/// </summary>
	internal sealed class MediaMindJobStatusBridge
	{
		private readonly StatusCenterViewModel _statusCenter;

		public MediaMindJobStatusBridge(IMediaMindEngineService engine, StatusCenterViewModel statusCenter)
		{
			_statusCenter = statusCenter;
			engine.JobUpdated += (_, job) => MainWindow.Instance.DispatcherQueue.TryEnqueue(() => OnJobUpdated(job));
		}

		private void OnJobUpdated(JobSnapshot job)
		{
			// Live progress is shown by the scan strip (ScanActivityViewModel). The Status centre
			// card said "0 items/s, Discovering items…" while the engine was working, which read as
			// stalled, so it now only keeps the outcome as history.
			if (job.State is not ("succeeded" or "failed" or "cancelled"))
				return;
			// Working out a plan changes nothing: no history entry for it.
			if (job.Type == "people-move-plan")
				return;

			var finished = _statusCenter.AddItem(
				string.Empty,
				string.Empty,
				job.State switch
				{
					"succeeded" => ReturnResult.Success,
					"cancelled" => ReturnResult.Cancelled,
					_ => ReturnResult.Failed,
				},
				FileOperationType.MediaMindScan,
				source: null,
				destination: null,
				canProvideProgress: false,
				itemsCount: job.Total);
			finished.Header = JobTypeLabel(job.Type);
		}

		private static string JobTypeLabel(string jobType) => jobType switch
		{
			"faces" => Strings.MediaMind_JobType_Faces.GetLocalizedResource(),
			"dedupe" => Strings.MediaMind_JobType_Dedupe.GetLocalizedResource(),
			"organize-execute" => Strings.MediaMind_JobType_Organize.GetLocalizedResource(),
			"people-move" => Strings.MediaMind_JobType_PeopleMove.GetLocalizedResource(),
			"auto-file" => Strings.MediaMind_JobType_AutoFile.GetLocalizedResource(),
			"teach-sort" => Strings.MediaMind_JobType_Sort.GetLocalizedResource(),
			"dedupe-execute" => Strings.MediaMind_JobType_RemoveCopies.GetLocalizedResource(),
			_ => Strings.MediaMind_JobType_Other.GetLocalizedResource(),
		};
	}
}

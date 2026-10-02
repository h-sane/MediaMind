// Copyright (c) Files Community
// Licensed under the MIT License.

using System.Text.Json.Serialization;

namespace Files.App.Services.MediaMind
{
	// Mirrors app/src/renderer/src/api/client.ts verbatim (same order, same section
	// comments) so the two can be diffed side by side. That file is the spec —
	// update this one to match it, not the other way around.

	// ---------------------------------------------------------------------------
	// Shared types
	// ---------------------------------------------------------------------------

	public sealed record Health(
		[property: JsonPropertyName("status")] string Status,
		[property: JsonPropertyName("version")] string Version);

	public sealed record Library(
		[property: JsonPropertyName("id")] string Id,
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("name")] string Name);

	public sealed record JobSnapshot(
		[property: JsonPropertyName("id")] string Id,
		[property: JsonPropertyName("library_id")] string LibraryId,
		[property: JsonPropertyName("type")] string Type,
		[property: JsonPropertyName("state")] string State,
		[property: JsonPropertyName("phase")] string Phase,
		[property: JsonPropertyName("done")] long Done,
		[property: JsonPropertyName("total")] long Total,
		[property: JsonPropertyName("error")] string Error,
		[property: JsonPropertyName("result")] Dictionary<string, object>? Result,
		[property: JsonPropertyName("created_at")] double CreatedAt,
		[property: JsonPropertyName("finished_at")] double? FinishedAt,
		[property: JsonPropertyName("triggered_by")] string TriggeredBy,
		// What the engine is working on right now (a file name) and running counters;
		// absent from an older engine.
		[property: JsonPropertyName("detail")] string? Detail = null,
		[property: JsonPropertyName("stats")] Dictionary<string, long>? Stats = null);

	public sealed record DuplicateFile(
		[property: JsonPropertyName("id")] long Id,
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("size")] long Size,
		[property: JsonPropertyName("mtime")] double Mtime,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("width")] int Width,
		[property: JsonPropertyName("height")] int Height,
		[property: JsonPropertyName("suggested_keep")] bool SuggestedKeep,
		[property: JsonPropertyName("resolution")] string? Resolution);

	public sealed record DuplicateGroup(
		[property: JsonPropertyName("id")] long Id,
		[property: JsonPropertyName("match")] string Match,
		[property: JsonPropertyName("files")] IReadOnlyList<DuplicateFile> Files);

	public sealed record DuplicatesSummary(
		[property: JsonPropertyName("groups")] int Groups,
		[property: JsonPropertyName("files")] int Files,
		[property: JsonPropertyName("reclaimable_bytes")] long ReclaimableBytes);

	public sealed record DuplicatesOut(
		[property: JsonPropertyName("scan_id")] string ScanId,
		[property: JsonPropertyName("scanned_at")] double? ScannedAt,
		[property: JsonPropertyName("summary")] DuplicatesSummary Summary,
		[property: JsonPropertyName("groups")] IReadOnlyList<DuplicateGroup> Groups);

	public sealed record ManifestEntry(
		[property: JsonPropertyName("source")] string Source,
		[property: JsonPropertyName("action")] string Action,
		[property: JsonPropertyName("destination")] string Destination,
		[property: JsonPropertyName("error")] string Error);

	public sealed record ExecutionReport(
		[property: JsonPropertyName("planned")] int Planned,
		[property: JsonPropertyName("handled")] int Handled,
		[property: JsonPropertyName("ok")] bool Ok,
		[property: JsonPropertyName("dry_run")] bool DryRun,
		[property: JsonPropertyName("manifest_path")] string? ManifestPath,
		[property: JsonPropertyName("entries")] IReadOnlyList<ManifestEntry> Entries);

	// ---------------------------------------------------------------------------
	// Duplicate flag types (Performance & Ingest V4 Phase 3 — incremental,
	// advisory notices raised during ingest; independent of the manual dedupe
	// scan's DuplicatesOut above)
	// ---------------------------------------------------------------------------

	public sealed record DuplicateFlag(
		[property: JsonPropertyName("id")] long Id,
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("match_path")] string MatchPath,
		[property: JsonPropertyName("match_type")] string MatchType,
		[property: JsonPropertyName("flagged_at")] double FlaggedAt);

	public sealed record DuplicateLocation(
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("is_source")] bool IsSource);

	public sealed record DuplicateLocationGroup(
		[property: JsonPropertyName("source")] string Source,
		[property: JsonPropertyName("locations")] IReadOnlyList<DuplicateLocation> Locations);

	// ---------------------------------------------------------------------------
	// Library file browser types (live, filesystem-first)
	// ---------------------------------------------------------------------------

	public sealed record FileEntry(
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("size")] long Size,
		[property: JsonPropertyName("mtime")] double Mtime);

	public sealed record LibraryFiles(
		[property: JsonPropertyName("library_id")] string LibraryId,
		[property: JsonPropertyName("root")] string Root,
		[property: JsonPropertyName("total")] int Total,
		[property: JsonPropertyName("files")] IReadOnlyList<FileEntry> Files);

	// ---------------------------------------------------------------------------
	// Explorer shell (whole-filesystem browsing, library-free)
	// ---------------------------------------------------------------------------

	public sealed record Drive(
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("label")] string Label);

	public sealed record BrowseFolder(
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("has_media")] bool? HasMedia,
		[property: JsonPropertyName("mtime")] double Mtime,
		[property: JsonPropertyName("created")] double? Created,
		[property: JsonPropertyName("accessed")] double? Accessed,
		[property: JsonPropertyName("read_only")] bool? ReadOnly,
		[property: JsonPropertyName("hidden")] bool? Hidden,
		[property: JsonPropertyName("system")] bool? System);

	public sealed record BrowseFile(
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("size")] long Size,
		[property: JsonPropertyName("mtime")] double Mtime,
		[property: JsonPropertyName("created")] double? Created,
		[property: JsonPropertyName("accessed")] double? Accessed,
		[property: JsonPropertyName("read_only")] bool? ReadOnly,
		[property: JsonPropertyName("hidden")] bool? Hidden,
		[property: JsonPropertyName("system")] bool? System);

	public sealed record BrowseDir(
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("folders")] IReadOnlyList<BrowseFolder> Folders,
		[property: JsonPropertyName("files")] IReadOnlyList<BrowseFile> Files);

	// ---------------------------------------------------------------------------
	// Explorer shell — file operations (M12 Phase B)
	// ---------------------------------------------------------------------------

	public sealed record FsUndoResult(
		[property: JsonPropertyName("ok")] bool Ok,
		[property: JsonPropertyName("kind")] string? Kind,
		[property: JsonPropertyName("message")] string Message);

	public sealed record FsRedoResult(
		[property: JsonPropertyName("ok")] bool Ok,
		[property: JsonPropertyName("kind")] string? Kind,
		[property: JsonPropertyName("message")] string Message);

	// ---------------------------------------------------------------------------
	// Explorer shell — metadata + Quick Access (M12 Phase C)
	// ---------------------------------------------------------------------------

	public sealed record BrowseMetadata(
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("size")] long Size,
		[property: JsonPropertyName("mtime")] double Mtime,
		[property: JsonPropertyName("width")] int? Width,
		[property: JsonPropertyName("height")] int? Height,
		[property: JsonPropertyName("duration_seconds")] double? DurationSeconds,
		[property: JsonPropertyName("created")] double? Created,
		[property: JsonPropertyName("accessed")] double? Accessed,
		[property: JsonPropertyName("read_only")] bool? ReadOnly,
		[property: JsonPropertyName("hidden")] bool? Hidden,
		[property: JsonPropertyName("system")] bool? System,
		[property: JsonPropertyName("owner")] string? Owner);

	public sealed record FolderStats(
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("item_count")] int? ItemCount,
		[property: JsonPropertyName("total_bytes")] long? TotalBytes);

	public sealed record FolderPerson(
		[property: JsonPropertyName("person_id")] long PersonId,
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("sample_face_id")] long SampleFaceId);

	public sealed record FolderFaces(
		[property: JsonPropertyName("library_id")] string? LibraryId,
		[property: JsonPropertyName("persons")] IReadOnlyList<FolderPerson> Persons,
		[property: JsonPropertyName("total_persons")] int TotalPersons);

	public sealed record DiskUsage(
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("total_bytes")] long TotalBytes,
		[property: JsonPropertyName("used_bytes")] long UsedBytes,
		[property: JsonPropertyName("free_bytes")] long FreeBytes);

	public sealed record QuickAccessEntry(
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("name")] string Name);

	public sealed record QuickAccessList(
		[property: JsonPropertyName("pins")] IReadOnlyList<QuickAccessEntry> Pins);

	public sealed record RecentFile(
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("size")] long Size,
		[property: JsonPropertyName("mtime")] double Mtime,
		[property: JsonPropertyName("opened_at")] double OpenedAt);

	public sealed record RecentFilesList(
		[property: JsonPropertyName("files")] IReadOnlyList<RecentFile> Files);

	public sealed record MediaMindSettings(
		[property: JsonPropertyName("recent_files_enabled")] bool RecentFilesEnabled,
		[property: JsonPropertyName("auto_scan_enabled")] bool AutoScanEnabled,
		[property: JsonPropertyName("auto_scan_mode")] string AutoScanMode);

	public sealed record MediaMindSettingsPatch(
		[property: JsonPropertyName("recent_files_enabled")] bool? RecentFilesEnabled = null,
		[property: JsonPropertyName("auto_scan_enabled")] bool? AutoScanEnabled = null,
		[property: JsonPropertyName("auto_scan_mode")] string? AutoScanMode = null);

	// ---------------------------------------------------------------------------
	// Discovery suggestions (auto_scan_mode: 'system' — folders with new media
	// found outside any registered library)
	// ---------------------------------------------------------------------------

	public sealed record DiscoverySuggestion(
		[property: JsonPropertyName("folder")] string Folder,
		[property: JsonPropertyName("media_count")] int MediaCount,
		[property: JsonPropertyName("first_seen")] double FirstSeen,
		[property: JsonPropertyName("last_seen")] double LastSeen);

	// ---------------------------------------------------------------------------
	// Provider types (M5)
	// ---------------------------------------------------------------------------

	public sealed record License(
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("url")] string Url,
		[property: JsonPropertyName("commercial_use")] bool CommercialUse,
		[property: JsonPropertyName("summary")] string Summary);

	public sealed record Provider(
		[property: JsonPropertyName("id")] string Id,
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("description")] string Description,
		[property: JsonPropertyName("guidance")] string Guidance,
		[property: JsonPropertyName("license")] License License,
		[property: JsonPropertyName("installed")] bool Installed,
		[property: JsonPropertyName("size_bytes")] long SizeBytes,
		[property: JsonPropertyName("embedding_dim")] int EmbeddingDim);

	// ---------------------------------------------------------------------------
	// Person types (M5)
	// ---------------------------------------------------------------------------

	public sealed record Person(
		[property: JsonPropertyName("id")] long Id,
		[property: JsonPropertyName("auto_label")] string AutoLabel,
		[property: JsonPropertyName("name")] string? Name,
		[property: JsonPropertyName("face_count")] int FaceCount,
		[property: JsonPropertyName("media_count")] int MediaCount,
		[property: JsonPropertyName("sample_face_ids")] IReadOnlyList<long> SampleFaceIds,
		[property: JsonPropertyName("primary_folder_path")] string? PrimaryFolderPath);

	/// <summary>
	/// ADR-0001 recurring-unnamed-faces browse surface. <see cref="TotalUnnamed"/>
	/// counts every unnamed cluster regardless of the floor, so the UI can offer a
	/// "show all" hatch below <see cref="MinAppearances"/>.
	/// </summary>
	public sealed record RecurringUnnamed(
		[property: JsonPropertyName("persons")] IReadOnlyList<Person> Persons,
		[property: JsonPropertyName("min_appearances")] int MinAppearances,
		[property: JsonPropertyName("total_unnamed")] int TotalUnnamed);

	// ---------------------------------------------------------------------------
	// Global (cross-library) people
	// ---------------------------------------------------------------------------

	public sealed record GlobalPersonMember(
		[property: JsonPropertyName("library_id")] string LibraryId,
		[property: JsonPropertyName("library_name")] string LibraryName,
		[property: JsonPropertyName("library_path")] string LibraryPath,
		[property: JsonPropertyName("local_person_id")] long LocalPersonId,
		[property: JsonPropertyName("provider_id")] string ProviderId,
		[property: JsonPropertyName("name")] string? Name,
		[property: JsonPropertyName("face_count")] int FaceCount,
		[property: JsonPropertyName("media_count")] int MediaCount,
		[property: JsonPropertyName("sample_face_ids")] IReadOnlyList<long> SampleFaceIds);

	public sealed record GlobalPerson(
		[property: JsonPropertyName("id")] long Id,
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("primary_location")] string? PrimaryLocation,
		[property: JsonPropertyName("media_count")] int MediaCount,
		[property: JsonPropertyName("members")] IReadOnlyList<GlobalPersonMember> Members);

	public sealed record GlobalLinkSuggestion(
		[property: JsonPropertyName("library_id_a")] string LibraryIdA,
		[property: JsonPropertyName("local_person_id_a")] long LocalPersonIdA,
		[property: JsonPropertyName("library_id_b")] string LibraryIdB,
		[property: JsonPropertyName("local_person_id_b")] long LocalPersonIdB,
		[property: JsonPropertyName("similarity")] double Similarity);

	public sealed record GlobalLinkSuggestionPair(
		[property: JsonPropertyName("library_id_a")] string LibraryIdA,
		[property: JsonPropertyName("local_person_id_a")] long LocalPersonIdA,
		[property: JsonPropertyName("library_id_b")] string LibraryIdB,
		[property: JsonPropertyName("local_person_id_b")] long LocalPersonIdB);

	public sealed record GlobalMoveSuggestionItem(
		[property: JsonPropertyName("library_id")] string LibraryId,
		[property: JsonPropertyName("file_id")] long FileId,
		[property: JsonPropertyName("abs_path")] string AbsPath,
		[property: JsonPropertyName("content_hash")] string? ContentHash);

	public sealed record GlobalMoveSuggestionGroup(
		[property: JsonPropertyName("global_person_id")] long GlobalPersonId,
		[property: JsonPropertyName("global_person_name")] string GlobalPersonName,
		[property: JsonPropertyName("primary_location")] string PrimaryLocation,
		[property: JsonPropertyName("items")] IReadOnlyList<GlobalMoveSuggestionItem> Items);

	public sealed record GlobalMoveSuggestionDismiss(
		[property: JsonPropertyName("global_person_id")] long GlobalPersonId,
		[property: JsonPropertyName("content_hash")] string ContentHash);

	public sealed record GlobalMoveExecuteItem(
		[property: JsonPropertyName("global_person_id")] long GlobalPersonId,
		[property: JsonPropertyName("library_id")] string LibraryId,
		[property: JsonPropertyName("file_id")] long FileId);

	public sealed record GlobalMoveExecuteBody(
		[property: JsonPropertyName("items")] IReadOnlyList<GlobalMoveExecuteItem> Items,
		[property: JsonPropertyName("dry_run")] bool? DryRun = null,
		[property: JsonPropertyName("expected_count")] int? ExpectedCount = null,
		[property: JsonPropertyName("expected_plan_hash")] string? ExpectedPlanHash = null);

	public sealed record GlobalMoveExecuteReport(
		[property: JsonPropertyName("planned")] int Planned,
		[property: JsonPropertyName("handled")] int Handled,
		[property: JsonPropertyName("ok")] bool Ok,
		[property: JsonPropertyName("dry_run")] bool DryRun,
		[property: JsonPropertyName("manifest_path")] string? ManifestPath,
		[property: JsonPropertyName("entries")] IReadOnlyList<ManifestEntry> Entries,
		[property: JsonPropertyName("plan_hash")] string PlanHash);

	public sealed record GlobalMoveUndoInfo(
		[property: JsonPropertyName("available")] bool Available,
		[property: JsonPropertyName("file_count")] int FileCount,
		[property: JsonPropertyName("destinations")] IReadOnlyList<string> Destinations);

	public sealed record PersonsOut(
		[property: JsonPropertyName("scan_id")] string ScanId,
		[property: JsonPropertyName("scanned_at")] double? ScannedAt,
		[property: JsonPropertyName("provider_id")] string ProviderId,
		[property: JsonPropertyName("persons")] IReadOnlyList<Person> Persons,
		[property: JsonPropertyName("unassigned_faces")] int UnassignedFaces,
		[property: JsonPropertyName("no_face_files")] int NoFaceFiles,
		[property: JsonPropertyName("unreadable_files")] int UnreadableFiles,
		[property: JsonPropertyName("pending_count")] int PendingCount,
		[property: JsonPropertyName("multi_person_count")] int MultiPersonCount);

	// People tree (ADR-0007/0008): person-centric projection. Groups mirror folder
	// nesting and hold only sub-Groups and Persons — never media directly.
	public sealed record PeopleGroup(
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("subgroups")] IReadOnlyList<PeopleGroup> Subgroups,
		[property: JsonPropertyName("persons")] IReadOnlyList<Person> Persons,
		[property: JsonPropertyName("total_persons")] int TotalPersons);

	public sealed record PeopleTreeOut(
		[property: JsonPropertyName("scan_id")] string ScanId,
		[property: JsonPropertyName("scanned_at")] double? ScannedAt,
		[property: JsonPropertyName("root")] PeopleGroup Root);

	public sealed record PersonMediaItem(
		[property: JsonPropertyName("file_id")] long FileId,
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("abs_path")] string AbsPath,
		[property: JsonPropertyName("kind")] string Kind,
		// Placement-attributed files (ADR-0010) carry no matching face for this
		// person — FaceId/Bbox are null and ViaPlacement is true.
		[property: JsonPropertyName("face_id")] long? FaceId,
		[property: JsonPropertyName("bbox")] IReadOnlyList<double>? Bbox,
		[property: JsonPropertyName("via_placement")] bool? ViaPlacement,
		[property: JsonPropertyName("via_manual")] bool? ViaManual = null);

	// A file the last scan could not process, kept with the reason (the folder view's "Not scanned" pane).
	public sealed record UnprocessedFile(
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("abs_path")] string AbsPath,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("size")] long Size,
		[property: JsonPropertyName("reason")] string Reason,
		[property: JsonPropertyName("message")] string Message,
		[property: JsonPropertyName("attempts")] int Attempts,
		[property: JsonPropertyName("failed_at")] double FailedAt,
		[property: JsonPropertyName("person_ids")] IReadOnlyList<long> PersonIds);

	public sealed record UnprocessedTagBody(
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("person_id")] long PersonId);

	// Teach who's who (backend api/routes/teach.py): one detected face to pick as an example.
	public sealed record TeachFace(
		[property: JsonPropertyName("face_id")] long FaceId,
		[property: JsonPropertyName("file_id")] long FileId,
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("abs_path")] string AbsPath,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("frame_no")] int FrameNo,
		[property: JsonPropertyName("width")] double Width,
		[property: JsonPropertyName("person_id")] long? PersonId,
		[property: JsonPropertyName("person_name")] string? PersonName,
		[property: JsonPropertyName("is_example")] bool IsExample,
		[property: JsonPropertyName("background")] bool Background);

	public sealed record TeachFacesResult(
		[property: JsonPropertyName("total")] int Total,
		[property: JsonPropertyName("faces")] IReadOnlyList<TeachFace> Faces);

	// PersonId is null for someone named only in another library so far.
	public sealed record TeachPerson(
		[property: JsonPropertyName("person_id")] long? PersonId,
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("examples_here")] int ExamplesHere,
		[property: JsonPropertyName("examples_elsewhere")] int ExamplesElsewhere,
		[property: JsonPropertyName("files")] int Files,
		// Only in a few pictures here (or named only elsewhere): listed apart, without a 1-9 key.
		[property: JsonPropertyName("guest")] bool Guest = false,
		// This person's physical folder (absolute, may be in another library); null until chosen.
		[property: JsonPropertyName("primary_location")] string? PrimaryLocation = null);

	// Files, not faces: sorted = someone in it is named; unsorted = faces, nobody named yet.
	public sealed record TeachStats(
		[property: JsonPropertyName("total")] int Total,
		[property: JsonPropertyName("sorted")] int Sorted,
		[property: JsonPropertyName("unsorted")] int Unsorted,
		[property: JsonPropertyName("no_faces")] int NoFaces);

	public sealed record PrimaryLocationBody(
		[property: JsonPropertyName("path")] string? Path);

	public sealed record PersonMovePlan(
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("primary_location")] string PrimaryLocation,
		[property: JsonPropertyName("moves")] int Moves,
		[property: JsonPropertyName("to_group_folders")] int ToGroupFolders,
		[property: JsonPropertyName("groups_waiting")] int GroupsWaiting,
		[property: JsonPropertyName("plan_hash")] string PlanHash,
		// Identical copies already in the folder: left where they are, not copied again.
		[property: JsonPropertyName("already_there")] int AlreadyThere = 0);

	public sealed record PersonMoveBody(
		[property: JsonPropertyName("expected_plan_hash")] string ExpectedPlanHash);

	public sealed record GroupFolderOption(
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("path")] string Path);

	// A picture with two or more named people: it can only go one place, so it waits for a choice.
	public sealed record GroupQuestion(
		[property: JsonPropertyName("library_id")] string LibraryId,
		[property: JsonPropertyName("file_id")] long FileId,
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("abs_path")] string AbsPath,
		[property: JsonPropertyName("people")] IReadOnlyList<string> People,
		[property: JsonPropertyName("folders")] IReadOnlyList<GroupFolderOption> Folders,
		[property: JsonPropertyName("new_folder_parent")] string NewFolderParent,
		// "image" or "video", and the folders already under NewFolderParent (an OT4 made earlier).
		[property: JsonPropertyName("kind")] string Kind = "image",
		[property: JsonPropertyName("existing_folders")] IReadOnlyList<string>? ExistingFolders = null);

	// A picture or video in which the scan found no face.
	public sealed record NoFaceFile(
		[property: JsonPropertyName("file_id")] long FileId,
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("abs_path")] string AbsPath,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("size")] long Size);

	public sealed record GroupPlaceBody(
		[property: JsonPropertyName("file_id")] long FileId,
		[property: JsonPropertyName("choice")] string Choice,
		[property: JsonPropertyName("person")] string? Person,
		[property: JsonPropertyName("folder_name")] string? FolderName,
		[property: JsonPropertyName("remember")] bool Remember,
		// For "existing": a folder that is already there.
		[property: JsonPropertyName("folder_path")] string? FolderPath = null);

	public sealed record GroupPlaceResult(
		[property: JsonPropertyName("moved")] int Moved,
		[property: JsonPropertyName("remembered")] bool Remembered);

	public sealed record AutoFileLibraries(
		[property: JsonPropertyName("library_ids")] IReadOnlyList<string> LibraryIds);

	public sealed record AutoFileBody(
		[property: JsonPropertyName("enabled")] bool Enabled);

	public sealed record TeachMembershipBody(
		[property: JsonPropertyName("membership")] string? Membership);

	public sealed record TeachMembershipResult(
		[property: JsonPropertyName("person_id")] long PersonId,
		[property: JsonPropertyName("membership")] string? Membership);

	public sealed record TeachExamplesBody(
		[property: JsonPropertyName("face_ids")] IReadOnlyList<long> FaceIds,
		[property: JsonPropertyName("person_id")] long? PersonId,
		[property: JsonPropertyName("name")] string? Name);

	public sealed record TeachExamplesResult(
		[property: JsonPropertyName("person_id")] long PersonId,
		[property: JsonPropertyName("added")] int Added);

	public sealed record TeachRemoveBody(
		[property: JsonPropertyName("face_ids")] IReadOnlyList<long> FaceIds);

	public sealed record TeachRemoveResult(
		[property: JsonPropertyName("removed")] int Removed);

	public sealed record TeachApplyPerson(
		[property: JsonPropertyName("person_id")] long PersonId,
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("files")] int Files,
		[property: JsonPropertyName("examples")] int Examples);

	public sealed record TeachApplyResult(
		[property: JsonPropertyName("people")] IReadOnlyList<TeachApplyPerson> People,
		[property: JsonPropertyName("attached")] int Attached,
		[property: JsonPropertyName("pending")] int Pending,
		[property: JsonPropertyName("detached")] int Detached);

	public sealed record ForgetMissingResult(
		[property: JsonPropertyName("removed")] int Removed);

	// The ignored face and the same face in the file's other frames.
	public sealed record RejectFaceResult(
		[property: JsonPropertyName("face_ids")] IReadOnlyList<long> FaceIds);

	public sealed record MergeSuggestion(
		[property: JsonPropertyName("person_a")] long PersonA,
		[property: JsonPropertyName("person_b")] long PersonB,
		[property: JsonPropertyName("similarity")] double Similarity);

	// ---------------------------------------------------------------------------
	// Multi-person types (M6 remainder)
	// ---------------------------------------------------------------------------

	public sealed record PersonOption(
		[property: JsonPropertyName("person_id")] long PersonId,
		[property: JsonPropertyName("person_name")] string PersonName,
		[property: JsonPropertyName("face_count")] int FaceCount,
		[property: JsonPropertyName("sample_face_id")] long SampleFaceId);

	public sealed record MultiPersonFile(
		[property: JsonPropertyName("file_id")] long FileId,
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("persons")] IReadOnlyList<PersonOption> Persons,
		[property: JsonPropertyName("current_choice")] long? CurrentChoice);

	// ---------------------------------------------------------------------------
	// Organize types (M6)
	// ---------------------------------------------------------------------------

	public sealed record PlannedMove(
		[property: JsonPropertyName("source_rel")] string SourceRel,
		[property: JsonPropertyName("dest_folder_rel")] string DestFolderRel,
		[property: JsonPropertyName("person_id")] long? PersonId,
		[property: JsonPropertyName("person_name")] string? PersonName,
		[property: JsonPropertyName("reason")] string Reason);

	public sealed record OrganizePreview(
		[property: JsonPropertyName("planned")] int Planned,
		[property: JsonPropertyName("by_person")] Dictionary<string, int> ByPerson,
		[property: JsonPropertyName("moves")] IReadOnlyList<PlannedMove> Moves,
		[property: JsonPropertyName("plan_hash")] string PlanHash,
		[property: JsonPropertyName("stayed_unrecognized")] int StayedUnrecognized);

	public sealed record OrganizeAction(
		[property: JsonPropertyName("id")] long Id,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("created_at")] double CreatedAt,
		[property: JsonPropertyName("planned")] int Planned,
		[property: JsonPropertyName("handled")] int Handled,
		[property: JsonPropertyName("ok")] bool Ok,
		[property: JsonPropertyName("dry_run")] bool DryRun,
		[property: JsonPropertyName("undone")] bool Undone);

	public sealed record OrganizeUndoResult(
		[property: JsonPropertyName("ok")] bool Ok,
		[property: JsonPropertyName("handled")] int Handled,
		[property: JsonPropertyName("planned")] int Planned,
		[property: JsonPropertyName("errors")] int Errors,
		[property: JsonPropertyName("kind")] string Kind);

	// ---------------------------------------------------------------------------
	// Pending match types (M6)
	// ---------------------------------------------------------------------------

	public sealed record PendingMatch(
		[property: JsonPropertyName("id")] long Id,
		[property: JsonPropertyName("face_id")] long FaceId,
		[property: JsonPropertyName("person_id")] long PersonId,
		[property: JsonPropertyName("person_name")] string PersonName,
		[property: JsonPropertyName("confidence")] double Confidence,
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("abs_path")] string AbsPath,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("folded_face_ids")] List<long>? FoldedFaceIds = null);

	public sealed record PendingDecisionItem(
		[property: JsonPropertyName("pending_id")] long PendingId,
		[property: JsonPropertyName("decision")] string Decision,
		[property: JsonPropertyName("reassign_to_person_id")] long? ReassignToPersonId = null);

	// ---------------------------------------------------------------------------
	// Folder binding types (Phase B — respect pre-existing person/group folders)
	// ---------------------------------------------------------------------------

	public sealed record BindingSuggestion(
		[property: JsonPropertyName("id")] long Id,
		[property: JsonPropertyName("folder_rel")] string FolderRel,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("file_count")] int FileCount,
		[property: JsonPropertyName("coverage")] double Coverage,
		[property: JsonPropertyName("person_ids")] IReadOnlyList<long> PersonIds,
		[property: JsonPropertyName("person_names")] IReadOnlyList<string> PersonNames,
		[property: JsonPropertyName("outlier_file_ids")] IReadOnlyList<long> OutlierFileIds,
		[property: JsonPropertyName("move_count")] int MoveCount,
		[property: JsonPropertyName("status")] string Status,
		[property: JsonPropertyName("created_at")] double CreatedAt);

	public sealed record RefreshSuggestionsResult(
		[property: JsonPropertyName("suggested")] int Suggested,
		[property: JsonPropertyName("removed_stale")] int RemovedStale);

	public sealed record OutlierFile(
		[property: JsonPropertyName("file_id")] long FileId,
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("accepted")] bool Accepted,
		[property: JsonPropertyName("likely_person_name")] string? LikelyPersonName);

	public sealed record FolderBinding(
		[property: JsonPropertyName("id")] long Id,
		[property: JsonPropertyName("folder_rel")] string FolderRel,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("person_ids")] IReadOnlyList<long> PersonIds,
		[property: JsonPropertyName("person_names")] IReadOnlyList<string> PersonNames,
		[property: JsonPropertyName("accepted_outlier_file_ids")] IReadOnlyList<long> AcceptedOutlierFileIds,
		[property: JsonPropertyName("outliers")] IReadOnlyList<OutlierFile> Outliers,
		[property: JsonPropertyName("created_at")] double CreatedAt);

	public sealed record MovePreviewItem(
		[property: JsonPropertyName("file_id")] long FileId,
		[property: JsonPropertyName("source_rel")] string SourceRel,
		[property: JsonPropertyName("dest_folder_rel")] string DestFolderRel,
		[property: JsonPropertyName("kind")] string Kind);

	public sealed record SuggestionMergePreview(
		[property: JsonPropertyName("suggestion_id")] long SuggestionId,
		[property: JsonPropertyName("folder_rel")] string FolderRel,
		[property: JsonPropertyName("person_names")] IReadOnlyList<string> PersonNames,
		[property: JsonPropertyName("leaf_name")] string LeafName,
		[property: JsonPropertyName("move_count")] int MoveCount,
		[property: JsonPropertyName("moves")] IReadOnlyList<MovePreviewItem> Moves,
		[property: JsonPropertyName("folder_outliers")] IReadOnlyList<OutlierFile> FolderOutliers,
		[property: JsonPropertyName("duplicate_file_ids")] IReadOnlyList<long> DuplicateFileIds);

	public sealed record ReassignItem(
		[property: JsonPropertyName("file_id")] long FileId,
		[property: JsonPropertyName("dest_folder_rel")] string DestFolderRel);

	public sealed record SuggestionMergeBody(
		[property: JsonPropertyName("dry_run")] bool? DryRun = null,
		[property: JsonPropertyName("expected_move_count")] int? ExpectedMoveCount = null,
		[property: JsonPropertyName("excluded_file_ids")] IReadOnlyList<long>? ExcludedFileIds = null,
		[property: JsonPropertyName("reassignments")] IReadOnlyList<ReassignItem>? Reassignments = null,
		[property: JsonPropertyName("confirmed_outlier_file_ids")] IReadOnlyList<long>? ConfirmedOutlierFileIds = null,
		[property: JsonPropertyName("rejected_outlier_file_ids")] IReadOnlyList<long>? RejectedOutlierFileIds = null);

	public sealed record FacesPrep(
		[property: JsonPropertyName("has_subfolders")] bool HasSubfolders,
		[property: JsonPropertyName("top_level_loose_count")] int TopLevelLooseCount,
		[property: JsonPropertyName("named_subfolder_count")] int NamedSubfolderCount,
		[property: JsonPropertyName("already_has_unsorted")] bool AlreadyHasUnsorted,
		[property: JsonPropertyName("recommend_unsorted")] bool RecommendUnsorted);

	public sealed record MaterializeCandidate(
		[property: JsonPropertyName("file_id")] long FileId,
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("kind")] string Kind);

	public sealed record MaterializePreview(
		[property: JsonPropertyName("person_id")] long PersonId,
		[property: JsonPropertyName("candidates")] IReadOnlyList<MaterializeCandidate> Candidates);

	public sealed record MaterializeBody(
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("dry_run")] bool? DryRun = null,
		[property: JsonPropertyName("expected_move_count")] int? ExpectedMoveCount = null,
		[property: JsonPropertyName("excluded_file_ids")] IReadOnlyList<long>? ExcludedFileIds = null,
		[property: JsonPropertyName("reassignments")] IReadOnlyList<ReassignItem>? Reassignments = null);

	// ---------------------------------------------------------------------------
	// Small anonymous-shaped response records (client.ts inlines these as object
	// literal types; named here since C# needs a declared type)
	// ---------------------------------------------------------------------------

	public sealed record OkResult([property: JsonPropertyName("ok")] bool Ok);

	public sealed record PathResult([property: JsonPropertyName("path")] string Path);

	public sealed record StatusResult([property: JsonPropertyName("status")] string Status);

	public sealed record HasMediaResult(
		[property: JsonPropertyName("statuses")] Dictionary<string, bool?> Statuses,
		[property: JsonPropertyName("junk")] IReadOnlyList<string> Junk);

	public sealed record RecycleBinCheckResult(
		[property: JsonPropertyName("recycle_bin_supported")] bool RecycleBinSupported);

	public sealed record UpdatedCountResult([property: JsonPropertyName("updated")] int Updated);

	public sealed record DuplicatesConfirmResult(
		[property: JsonPropertyName("confirmed_groups")] int ConfirmedGroups,
		[property: JsonPropertyName("skipped_pending")] int SkippedPending);

	public sealed record DuplicatesResetDismissalsResult(
		[property: JsonPropertyName("cleared_dismissals")] int ClearedDismissals,
		[property: JsonPropertyName("restored_groups")] int RestoredGroups);

	public sealed record PrimaryFolderResult(
		[property: JsonPropertyName("ok")] bool Ok,
		[property: JsonPropertyName("primary_folder_path")] string? PrimaryFolderPath);

	public sealed record PrimaryLocationResult(
		[property: JsonPropertyName("ok")] bool Ok,
		[property: JsonPropertyName("primary_location")] string? PrimaryLocation);

	public sealed record DuplicateResolution(
		[property: JsonPropertyName("file_id")] long FileId,
		[property: JsonPropertyName("action")] string Action);

	public sealed record RouteChoice(
		[property: JsonPropertyName("file_id")] long FileId,
		[property: JsonPropertyName("person_id")] long PersonId);

	public sealed record BindingsSuggestionsResult(
		[property: JsonPropertyName("provider_id")] string ProviderId,
		[property: JsonPropertyName("suggestions")] IReadOnlyList<BindingSuggestion> Suggestions);

	public sealed record BindingsListResult(
		[property: JsonPropertyName("provider_id")] string ProviderId,
		[property: JsonPropertyName("bindings")] IReadOnlyList<FolderBinding> Bindings);

	// ---------------------------------------------------------------------------
	// Request bodies (client.ts passes inline object literals; named here since
	// C# needs a declared type for each)
	// ---------------------------------------------------------------------------

	public sealed record PathBody([property: JsonPropertyName("path")] string Path);

	public sealed record NullablePathBody([property: JsonPropertyName("path")] string? Path);

	public sealed record PathsBody([property: JsonPropertyName("paths")] IReadOnlyList<string> Paths);

	public sealed record FolderBody([property: JsonPropertyName("folder")] string Folder);

	public sealed record NewFolderBody(
		[property: JsonPropertyName("parent")] string Parent,
		[property: JsonPropertyName("name")] string? Name);

	public sealed record RenameBody(
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("new_name")] string NewName);

	public sealed record DeletePathsBody(
		[property: JsonPropertyName("paths")] IReadOnlyList<string> Paths,
		[property: JsonPropertyName("permanent")] bool Permanent);

	public sealed record MoveCopyBody(
		[property: JsonPropertyName("sources")] IReadOnlyList<string> Sources,
		[property: JsonPropertyName("dest")] string Dest);

	public sealed record CreateShortcutBody(
		[property: JsonPropertyName("target")] string Target,
		[property: JsonPropertyName("dest_folder")] string DestFolder,
		[property: JsonPropertyName("name")] string? Name);

	public sealed record ScanStartBody(
		[property: JsonPropertyName("type")] string Type,
		[property: JsonPropertyName("near_threshold")] double NearThreshold,
		[property: JsonPropertyName("provider_id")] string? ProviderId,
		[property: JsonPropertyName("with_duplicates")] bool WithDuplicates = false);

	public sealed record DuplicatesResolveBody(
		[property: JsonPropertyName("resolutions")] IReadOnlyList<DuplicateResolution> Resolutions);

	public sealed record DuplicatesExecuteBody(
		[property: JsonPropertyName("dry_run")] bool DryRun,
		[property: JsonPropertyName("expected_trash_count")] int ExpectedTrashCount,
		[property: JsonPropertyName("permanent")] bool Permanent);

	public sealed record DuplicatesExecuteJobBody(
		[property: JsonPropertyName("expected_trash_count")] int ExpectedTrashCount,
		[property: JsonPropertyName("permanent")] bool Permanent);

	public sealed record LicenseAcceptedBody(
		[property: JsonPropertyName("license_accepted")] bool LicenseAccepted);

	public sealed record OrganizeExecuteBody(
		[property: JsonPropertyName("dry_run")] bool DryRun,
		[property: JsonPropertyName("expected_planned")] int? ExpectedPlanned,
		[property: JsonPropertyName("expected_plan_hash")] string? ExpectedPlanHash,
		[property: JsonPropertyName("excluded_sources")] IReadOnlyList<string> ExcludedSources,
		[property: JsonPropertyName("mode")] string Mode,
		[property: JsonPropertyName("group_scope")] string GroupScope,
		[property: JsonPropertyName("person_id")] long? PersonId);

	public sealed record PruneDuplicateLocationsBody(
		[property: JsonPropertyName("paths")] IReadOnlyList<string> Paths,
		[property: JsonPropertyName("dry_run")] bool DryRun,
		[property: JsonPropertyName("permanent")] bool Permanent);

	public sealed record PendingDecideBody(
		[property: JsonPropertyName("decisions")] IReadOnlyList<PendingDecisionItem> Decisions);

	public sealed record RouteChoicesBody(
		[property: JsonPropertyName("choices")] IReadOnlyList<RouteChoice> Choices);

	public sealed record NameBody([property: JsonPropertyName("name")] string? Name);

	public sealed record NameRequiredBody([property: JsonPropertyName("name")] string Name);

	public sealed record PersonMergeBody(
		[property: JsonPropertyName("source_id")] long SourceId,
		[property: JsonPropertyName("target_id")] long TargetId);

	public sealed record PersonMergeDismissBody(
		[property: JsonPropertyName("person_a_id")] long PersonAId,
		[property: JsonPropertyName("person_b_id")] long PersonBId);

	public sealed record PersonIdBody([property: JsonPropertyName("person_id")] long PersonId);

	public sealed record FileIdsBody([property: JsonPropertyName("file_ids")] IReadOnlyList<long> FileIds);

	public sealed record DryRunBody([property: JsonPropertyName("dry_run")] bool DryRun);

	public sealed record GlobalLinkBody(
		[property: JsonPropertyName("library_id")] string LibraryId,
		[property: JsonPropertyName("local_person_id")] long LocalPersonId);

	// ---------------------------------------------------------------------------
	// People view (docs/PEOPLE_VIEW_V2_DESIGN.md): cross-library overview, pins, collections
	// ---------------------------------------------------------------------------

	public sealed record PeopleMember(
		[property: JsonPropertyName("library_id")] string LibraryId,
		[property: JsonPropertyName("library_name")] string LibraryName,
		[property: JsonPropertyName("local_person_id")] long LocalPersonId,
		[property: JsonPropertyName("sample_face_ids")] IReadOnlyList<long> SampleFaceIds);

	public sealed record PeopleDuplicate(
		[property: JsonPropertyName("entry_id")] string EntryId,
		[property: JsonPropertyName("similarity")] double Similarity);

	public sealed record PeopleEntry(
		[property: JsonPropertyName("id")] string Id,
		[property: JsonPropertyName("name")] string? Name,
		[property: JsonPropertyName("auto_label")] string AutoLabel,
		[property: JsonPropertyName("face_count")] int FaceCount,
		[property: JsonPropertyName("media_count")] int MediaCount,
		[property: JsonPropertyName("members")] IReadOnlyList<PeopleMember> Members,
		[property: JsonPropertyName("keys")] IReadOnlyList<string> Keys,
		[property: JsonPropertyName("folder_path")] string FolderPath,
		[property: JsonPropertyName("pinned")] bool Pinned,
		[property: JsonPropertyName("collection_id")] string? CollectionId,
		[property: JsonPropertyName("duplicates")] IReadOnlyList<PeopleDuplicate> Duplicates);

	public sealed record PeopleNode(
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("id")] string Id,
		[property: JsonPropertyName("path")] string Path,
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("person_ids")] IReadOnlyList<string> PersonIds,
		[property: JsonPropertyName("subgroups")] IReadOnlyList<PeopleNode> Subgroups,
		[property: JsonPropertyName("total_persons")] int TotalPersons,
		[property: JsonPropertyName("pinned")] bool Pinned);

	public sealed record PeoplePin(
		[property: JsonPropertyName("key")] string Key,
		[property: JsonPropertyName("kind")] string Kind,
		[property: JsonPropertyName("ref_id")] string? RefId,
		[property: JsonPropertyName("label")] string? Label,
		[property: JsonPropertyName("available")] bool Available);

	public sealed record PeopleCollection(
		[property: JsonPropertyName("id")] string Id,
		[property: JsonPropertyName("name")] string Name,
		[property: JsonPropertyName("members")] IReadOnlyList<string> Members);

	public sealed record PeopleOverview(
		[property: JsonPropertyName("entries")] IReadOnlyList<PeopleEntry> Entries,
		[property: JsonPropertyName("tree")] IReadOnlyList<PeopleNode> Tree,
		[property: JsonPropertyName("collections")] IReadOnlyList<PeopleCollection> Collections,
		[property: JsonPropertyName("pins")] IReadOnlyList<PeoplePin> Pins,
			[property: JsonPropertyName("hidden")] IReadOnlyList<PeopleEntry>? Hidden = null);

	public sealed record PeoplePinBody([property: JsonPropertyName("key")] string Key);

	public sealed record PeopleVerifyResult([property: JsonPropertyName("unusable")] IReadOnlyList<string> Unusable);

	public sealed record PeopleKeysBody([property: JsonPropertyName("keys")] IReadOnlyList<string> Keys);

	public sealed record PeopleMergeBody(
		[property: JsonPropertyName("source_keys")] IReadOnlyList<string> SourceKeys,
		[property: JsonPropertyName("target_keys")] IReadOnlyList<string> TargetKeys);

	public sealed record PeopleCollectionNameBody([property: JsonPropertyName("name")] string Name);
}

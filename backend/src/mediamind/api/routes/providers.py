"""Provider catalog + download routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from mediamind.api.models import (
    JobSnapshot,
    LicenseOut,
    ProviderDownloadIn,
    ProviderOut,
)
from mediamind.providers.downloads import make_download_runner
from mediamind.providers.manager import ProviderManager

router = APIRouter(tags=["providers"])

DOWNLOAD_LIBRARY_ID = "__app__"


def _pm(request: Request) -> ProviderManager:
    return request.app.state.providers


def _snapshot(job) -> JobSnapshot:
    return JobSnapshot(
        id=job.id,
        library_id=job.library_id,
        type=job.type,
        state=job.state,
        phase=job.phase,
        done=job.done,
        total=job.total,
        error=job.error,
        result=job.result,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


@router.get("/providers", response_model=list[ProviderOut])
def list_providers(request: Request):
    pm = _pm(request)
    out = []
    for entry in pm.entries():
        size_bytes = sum(dl.size_bytes for dl in entry.downloads)
        out.append(
            ProviderOut(
                id=entry.id,
                name=entry.name,
                description=entry.description,
                license=LicenseOut(
                    name=entry.license.name,
                    url=entry.license.url,
                    commercial_use=entry.license.commercial_use,
                    summary=entry.license.summary,
                ),
                installed=pm.is_installed(entry.id),
                size_bytes=size_bytes,
                embedding_dim=entry.embedding_dim,
            )
        )
    return out


@router.post("/providers/{provider_id}/download", response_model=JobSnapshot, status_code=202)
def download_provider(provider_id: str, body: ProviderDownloadIn, request: Request):
    pm = _pm(request)
    entry = pm.get_entry(provider_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")
    if pm.is_installed(provider_id):
        raise HTTPException(status_code=409, detail="Provider already installed")
    if not body.license_accepted:
        raise HTTPException(
            status_code=400,
            detail="You must accept the model license before downloading",
        )
    if not entry.downloads:
        raise HTTPException(status_code=422, detail="Provider has no download URL")

    jm = request.app.state.job_manager
    if jm.running_for(DOWNLOAD_LIBRARY_ID) is not None:
        raise HTTPException(
            status_code=409, detail="A download is already in progress"
        )

    runner = make_download_runner(entry, pm)
    job = jm.start(DOWNLOAD_LIBRARY_ID, "provider-download", runner)
    return _snapshot(job)


@router.get("/jobs/{job_id}", response_model=JobSnapshot)
def get_job(job_id: str, request: Request):
    jm = request.app.state.job_manager
    job = jm.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    return _snapshot(job)


@router.delete("/jobs/{job_id}", status_code=202)
def cancel_job(job_id: str, request: Request):
    jm = request.app.state.job_manager
    job = jm.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    jm.cancel(job_id)
    return {"status": "cancelling"}

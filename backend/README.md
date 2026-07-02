# mediamind (backend engine)

The Python engine behind MediaMind: media scanning, duplicate detection, face
recognition (pluggable ONNX providers), and safe file organization, exposed as
a localhost-only FastAPI service consumed by the Electron app.

## Development

```
# from backend/, inside the project venv
pip install -e ".[dev]"
python -m mediamind            # starts on 127.0.0.1, prints MEDIAMIND_PORT=<port>
pytest                         # model-free test suite
pytest -m integration          # tests that need a real face model (optional)
```

Auth: if the `MEDIAMIND_TOKEN` env var is set, every request must carry it in
the `X-MediaMind-Token` header. The Electron main process handles this
automatically; bare dev runs without the variable skip auth.

See `docs/IMPLEMENTATION_PLAN.md` at the repo root for architecture.

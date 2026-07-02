/// <reference types="electron-vite/node" />

interface ImportMetaEnv {
  /** Python interpreter with the mediamind package (dev only; see .env.example). */
  readonly MAIN_VITE_PYTHON?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

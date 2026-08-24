; Auto-included by electron-builder (buildResources/installer.nsh).
;
; MediaMind's Python engine runs as a separate process that PyInstaller names
; mediamind.exe — which collides case-insensitively with the app's own
; MediaMind.exe. During an auto-update the engine is often still alive when the
; new installer runs, and it locks the file the installer must replace/remove,
; producing the "MediaMind cannot be closed. Please close it manually and click
; Retry" dialog that can never clear on its own.
;
; Force-kill the engine (and the app — same image name, and it is quitting for
; the update anyway) before any file operation, in both the installer and the
; uninstaller. This runs from the NEW package, so it fixes updates arriving from
; older builds whose engine is still named mediamind.exe and left running.
!macro killEngine
  nsExec::Exec 'taskkill /f /t /im mediamind.exe'
  Sleep 300
!macroend

!macro customInit
  !insertmacro killEngine
!macroend

!macro customUnInit
  !insertmacro killEngine
!macroend

# Run this in an ELEVATED PowerShell window.
# Adds the Windows 11 SDK (10.0.26100.0) component to the existing VS 2022 Build Tools
# install. This is the component missing its x64 desktop libs (dbghelp.lib etc.), which
# blocks Native AOT compilation for a real signed MSIX package.

$ErrorActionPreference = "Stop"
$installer = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vs_installer.exe"
$installPath = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"

$proc = Start-Process -FilePath $installer -ArgumentList @(
    "modify",
    "--installPath", "`"$installPath`"",
    "--add", "Microsoft.VisualStudio.Component.Windows11SDK.26100",
    "--quiet", "--norestart"
) -PassThru -Wait

Write-Host "Exit code: $($proc.ExitCode)"

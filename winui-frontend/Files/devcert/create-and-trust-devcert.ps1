# Run this in an ELEVATED PowerShell window.
# Creates a self-signed code-signing cert matching Files' package Publisher (CN=Files),
# exports it, and trusts it so Add-AppxPackage will accept MSIX packages signed with it.

$ErrorActionPreference = "Stop"
$outDir = $PSScriptRoot
$pfxPath = Join-Path $outDir "mediamind-dev.pfx"
$cerPath = Join-Path $outDir "mediamind-dev.cer"
$password = ConvertTo-SecureString -String "mediamind-dev" -Force -AsPlainText

$cert = New-SelfSignedCertificate `
    -Type Custom `
    -Subject "CN=Files" `
    -KeyUsage DigitalSignature `
    -FriendlyName "MediaMind Files Dev Cert" `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")

Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $password | Out-Null
Export-Certificate -Cert $cert -FilePath $cerPath | Out-Null

Import-Certificate -FilePath $cerPath -CertStoreLocation "Cert:\LocalMachine\Root" | Out-Null
Import-Certificate -FilePath $cerPath -CertStoreLocation "Cert:\LocalMachine\TrustedPeople" | Out-Null

Write-Host "Done. Cert thumbprint: $($cert.Thumbprint)"
Write-Host "PFX: $pfxPath"
Write-Host "CER: $cerPath"

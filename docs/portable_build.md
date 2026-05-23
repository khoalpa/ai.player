# Portable Build

The restored repository includes a minimal portable build script.

```powershell
.\scripts\build_portable.ps1
```

The output is written to `dist\portable\AI Player Lite`. The Lite package does not bundle local model folders.
When run from `Run AI Player.bat`, runtime data and optional `models\` / `tools\` folders are resolved relative to the `AI Player Lite` folder.

On Windows machines that enforce enterprise code integrity policies, build with an Authenticode code-signing certificate:

```powershell
.\scripts\build_portable.ps1 -RequireSignature
```

If exactly one code-signing certificate exists in the local certificate stores, the script uses it automatically. To list available code-signing certificates:

```powershell
.\scripts\build_portable.ps1 -ListCodeSigningCerts
```

If multiple certificates are available, pass the selected thumbprint explicitly:

```powershell
.\scripts\build_portable.ps1 -CodeSigningCertThumbprint "<real-thumbprint>" -RequireSignature
```

If IT provides a `.pfx` or `.p12` certificate file instead of installing it in the Windows certificate store, pass it directly:

```powershell
$certPassword = Read-Host -AsSecureString "PFX password"
.\scripts\build_portable.ps1 -CodeSigningPfxPath "C:\path\to\certificate.pfx" -CodeSigningPfxPassword $certPassword -RequireSignature
```

The certificate must be available in `Cert:\CurrentUser\My`, `Cert:\LocalMachine\My`, or passed with `-CodeSigningPfxPath`. The script signs the PyInstaller executable before copying it into the portable folder and verifies the portable executable when `-RequireSignature` is used. Machines with enterprise Code Integrity or WDAC policies usually require a certificate approved by that policy; a random local test certificate will not satisfy that requirement.

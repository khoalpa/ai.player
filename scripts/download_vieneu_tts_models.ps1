param(
    [string]$Python = "",
    [switch]$IncludeCommunityOnnx
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Python) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $VenvPython) { $VenvPython } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
}

$StandardTarget = Join-Path $ProjectRoot "models\tts\vieneu\standard"
$StandardCodecTarget = Join-Path $StandardTarget "distill-neucodec"
$TurboTarget = Join-Path $ProjectRoot "models\tts\vieneu\turbo"
New-Item -ItemType Directory -Force -Path $StandardTarget, $StandardCodecTarget, $TurboTarget | Out-Null

& $Python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='pnnbao-ump/VieNeu-TTS-0.3B-q4-gguf', local_dir=r'$StandardTarget', allow_patterns=['VieNeu-TTS-0_3B-Q4_0.gguf','voices.json'], local_dir_use_symlinks=False)"
& $Python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='neuphonic/distill-neucodec', local_dir=r'$StandardCodecTarget', allow_patterns=['pytorch_model.bin','meta.yaml','README.md'], local_dir_use_symlinks=False)"
& $Python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF', local_dir=r'$TurboTarget', allow_patterns=['vieneu-tts-v2-turbo.gguf','voices.json'], local_dir_use_symlinks=False)"

if ($IncludeCommunityOnnx) {
    $OnnxTarget = Join-Path $TurboTarget "community-onnx"
    New-Item -ItemType Directory -Force -Path $OnnxTarget | Out-Null
    & $Python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='toan5ks1/vieneu-tts-onnx', local_dir=r'$OnnxTarget', allow_patterns=['onnx/model_quantized.onnx','neucodec-onnx-decoder/model.onnx'], local_dir_use_symlinks=False)"
    Write-Host "Community ONNX files ready: $OnnxTarget"
}

Write-Host "VieNeu standard ready: $StandardTarget"
Write-Host "VieNeu turbo ready: $TurboTarget"

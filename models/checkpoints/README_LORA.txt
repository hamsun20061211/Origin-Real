LoRA for building/car (TripoSR):

1. After training (training/triposr_finetune), copy these two files HERE:
   - triposr_lora.safetensors
   - triposr_lora_adapter_config.json

2. Restart start-engine.ps1. Logs should show "LoRA loaded" and /status -> lora_loaded: true.

3. If files live elsewhere, set in PowerShell before starting the engine:
   $env:TRIPOSR_LORA_SAFETENSORS = "C:\full\path\triposr_lora.safetensors"
   $env:TRIPOSR_LORA_CONFIG = "C:\full\path\triposr_lora_adapter_config.json"

4. To use base TripoSR only: $env:TRIPOSR_SKIP_LORA = "1"

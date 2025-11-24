#!/usr/bin/env pwsh
# Test capabilities implementation (moved under tests/)
Write-Host "Testing Capabilities Implementation" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan

# Test best models endpoint
Write-Host "`n1. Testing /api/models/downloadable?category=best" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:5000/api/models/downloadable?category=best" -UseBasicParsing
    $json = $response.Content | ConvertFrom-Json

    Write-Host "   Total models returned: $($json.models.Count)" -ForegroundColor Green

    # Check llava model
    $llava = $json.models | Where-Object { $_.name -eq 'llava' }
    if ($llava) {
        Write-Host "`n   Llava model found:" -ForegroundColor Green
        Write-Host "   - Name: $($llava.name)"
        Write-Host "   - has_vision: $($llava.has_vision)" -ForegroundColor $(if ($llava.has_vision) { "Green" } else { "Red" })
        Write-Host "   - has_tools: $($llava.has_tools)"
        Write-Host "   - has_reasoning: $($llava.has_reasoning)"
    } else {
        Write-Host "   ERROR: Llava model not found!" -ForegroundColor Red
    }
} catch {
    Write-Host "   ERROR: $_" -ForegroundColor Red
}

# Test extended models endpoint
Write-Host "`n2. Testing /api/models/downloadable?category=all" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:5000/api/models/downloadable?category=all" -UseBasicParsing
    $json = $response.Content | ConvertFrom-Json

    Write-Host "   Total models returned: $($json.models.Count)" -ForegroundColor Green

    # Check vision models
    $visionModels = $json.models | Where-Object { $_.has_vision -eq $true }
    Write-Host "   Vision models found: $($visionModels.Count)" -ForegroundColor Green

    foreach ($model in $visionModels) {
        Write-Host "   - $($model.name) (has_vision: $($model.has_vision))"
    }
} catch {
    Write-Host "   ERROR: $_" -ForegroundColor Red
}

# Test running models endpoint (if any models are running)
Write-Host "`n3. Testing /api/models/running" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:5000/api/models/running" -UseBasicParsing
    $json = $response.Content | ConvertFrom-Json

    if ($json -and $json.Count -gt 0) {
        Write-Host "   Running models: $($json.Count)" -ForegroundColor Green
        foreach ($model in $json) {
            Write-Host "   - $($model.name)"
            Write-Host "     has_vision: $($model.has_vision)"
            Write-Host "     has_tools: $($model.has_tools)"
            Write-Host "     has_reasoning: $($model.has_reasoning)"
        }
    } else {
        Write-Host "   No running models" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ERROR: $_" -ForegroundColor Red
}

# Test available models endpoint
Write-Host "`n4. Testing /api/models/available" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:5000/api/models/available" -UseBasicParsing
    $json = $response.Content | ConvertFrom-Json

    if ($json.models -and $json.models.Count -gt 0) {
        Write-Host "   Available models: $($json.models.Count)" -ForegroundColor Green

        # Check for vision capabilities
        $visionModels = $json.models | Where-Object { $_.has_vision -eq $true }
        if ($visionModels) {
            Write-Host "   Vision-capable models:" -ForegroundColor Green
            foreach ($model in $visionModels) {
                Write-Host "   - $($model.name) (has_vision: $($model.has_vision))"
            }
        } else {
            Write-Host "   No vision-capable models in available models" -ForegroundColor Yellow
        }
    } else {
        Write-Host "   No available models" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ERROR: $_" -ForegroundColor Red
}

Write-Host "`n=================================" -ForegroundColor Cyan
Write-Host "Testing Complete!" -ForegroundColor Cyan

#requires -Version 5.1

BeforeAll {
  $repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
  $sanitizer=Join-Path $repoRoot 'src\Sanitizer\Sanitize-OPNsenseConfig.ps1'
  $fixture=Join-Path $repoRoot 'tests\Fixtures\Sanitizer\secrets.xml'
}

Describe 'Sanitize-OPNsenseConfig.ps1' {
  BeforeEach {
    $caseDir=Join-Path $TestDrive ([Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $caseDir -Force | Out-Null
    $inputPath=Join-Path $caseDir 'config.xml'; Copy-Item -LiteralPath $fixture -Destination $inputPath
    $output=Join-Path $caseDir 'generated\config.sanitized.xml'
    $reportPath=Join-Path $caseDir 'generated\sanitization-report.json'
  }

  It 'never modifies the source config.xml' {
    $before=(Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash
    & $sanitizer -InputPath $inputPath -OutputPath $output -ReportPath $reportPath
    (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash | Should -BeExactly $before
  }

  It 'creates relative nested output directories' {
    Push-Location $caseDir
    try { & $sanitizer -InputPath '.\config.xml' -OutputPath '.\generated\config.sanitized.xml' -ReportPath '.\generated\sanitization-report.json' }
    finally { Pop-Location }
    Test-Path -LiteralPath $output -PathType Leaf | Should -BeTrue
    Test-Path -LiteralPath $reportPath -PathType Leaf | Should -BeTrue
  }

  It 'redacts secrets and preserves network structure' {
    & $sanitizer -InputPath $inputPath -OutputPath $output -ReportPath $reportPath
    [xml]$xml=Get-Content -LiteralPath $output -Raw
    $xml.opnsense.system.root.password | Should -BeExactly '[REDACTED]'
    $xml.opnsense.system.root.otp_seed | Should -BeExactly '[REDACTED]'
    $xml.opnsense.system.firmware.subscription | Should -BeExactly '[REDACTED]'
    $xml.opnsense.snmpd.rocommunity | Should -BeExactly '[REDACTED]'
    $xml.opnsense.ipsec.phase1.'pre-shared-key' | Should -BeExactly '[REDACTED]'
    $xml.opnsense.cert.prv | Should -BeExactly '[REDACTED]'
    $xml.opnsense.plugin.api_key | Should -BeExactly '[REDACTED]'
    $xml.opnsense.plugin.provider.client_secret | Should -BeExactly '[REDACTED]'
    $xml.opnsense.plugin.provider.dns_cf_token | Should -BeExactly '[REDACTED]'
    $xml.opnsense.plugin.provider.customPassword | Should -BeExactly '[REDACTED]'
    $xml.opnsense.plugin.url | Should -BeExactly 'https://testuser:[REDACTED]@example.invalid/api'
    $xml.opnsense.plugin.arguments | Should -BeExactly '--password [REDACTED] --mode read'
    $xml.opnsense.interfaces.lan.if | Should -BeExactly 'igc0'
    $xml.opnsense.interfaces.lan.ipaddr | Should -BeExactly '192.168.50.1'
    $xml.opnsense.interfaces.lan.subnet | Should -BeExactly '24'
    $xml.opnsense.cert.crt | Should -BeExactly 'PUBLIC-CERTIFICATE-DATA-MAY-REMAIN'
  }

  It 'removes created updated and revision audit metadata' {
    & $sanitizer -InputPath $inputPath -OutputPath $output -ReportPath $reportPath
    [xml]$xml=Get-Content -LiteralPath $output -Raw
    $xml.SelectNodes("//*[local-name()='created']").Count | Should -Be 0
    $xml.SelectNodes("//*[local-name()='updated']").Count | Should -Be 0
    $xml.SelectNodes("/*[local-name()='opnsense']/*[local-name()='revision']").Count | Should -Be 0
  }

  It 'writes a clean report without local fullPath properties' {
    & $sanitizer -InputPath $inputPath -OutputPath $output -ReportPath $reportPath
    $report=Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    $report.schemaVersion | Should -BeExactly '1.0.0'
    $report.sanitizerVersion | Should -BeExactly '1.1.0'
    $report.status | Should -BeExactly 'Clean'
    @($report.residualFindings).Count | Should -Be 0
    $report.source.PSObject.Properties.Name | Should -Not -Contain 'fullPath'
    $report.output.PSObject.Properties.Name | Should -Not -Contain 'fullPath'
    $report.redactionSummary.elementValues | Should -BeGreaterThan 0
    $report.redactionSummary.attributeValues | Should -BeGreaterThan 0
    $report.redactionSummary.embeddedPatterns | Should -BeGreaterThan 0
    $report.redactionSummary.removedAuditNodes | Should -Be 3
  }

  It 'keeps the PowerShell 5.1 generic-list regression fix in place' {
    $source=Get-Content -LiteralPath $sanitizer -Raw
    $source | Should -Match '\.ToArray\(\)'
    $source | Should -Not -Match '\[System\.IO\.Directory\]::CreateDirectory'
  }
}

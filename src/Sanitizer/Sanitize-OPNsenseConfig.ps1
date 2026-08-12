<#
.SYNOPSIS
  Creates a sanitized OPNsense configuration copy for deterministic documentation processing.
.DESCRIPTION
  Never modifies the input XML. Secrets are redacted, operational audit metadata is removed,
  network-relevant structure is retained and a JSON sanitization report is emitted.
  Designed for Windows PowerShell 5.1 and PowerShell 7+.
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$InputPath,
  [string]$OutputPath,
  [string]$ReportPath,
  [ValidateNotNullOrEmpty()][string]$RedactionText='[REDACTED]',
  [bool]$FailOnResidualSecrets=$true
)

Set-StrictMode -Version 2.0
$ErrorActionPreference='Stop'
$SanitizerVersion='1.1.0'
$ReportSchemaVersion='1.0.0'

function Get-NormalizedName([string]$Name) {
  if ([string]::IsNullOrWhiteSpace($Name)) { return '' }
  return [regex]::Replace($Name.ToLowerInvariant(),'[^a-z0-9]','')
}

function Test-SensitiveName([string]$Name) {
  $n=Get-NormalizedName $Name
  if ([string]::IsNullOrWhiteSpace($n)) { return $false }
  $exact=@('password','passwd','passphrase','pwd','secret','sharedsecret','clientsecret','authsecret','psk','presharedkey','privatekey','privkey','prv','apikey','apikeys','accesskey','secretkey','token','accesstoken','refreshtoken','authtoken','bearertoken','authorizedkeys','sshkeys','bindpw','bindpassword','community','communitystring','rocommunity','authpass','privpass','snmpauthpass','snmpprivpass','otpseed','totpseed','hotpseed','tlsauthkey','tlscryptkey','statickey','recoverycode','recoverycodes','bcrypthash','passwordhash','activationkey','licensekey','subscriptionkey')
  if ($exact -contains $n) { return $true }
  $suffixes=@('password','passwd','passphrase','secret','sharedsecret','clientsecret','presharedkey','privatekey','privkey','apikey','token','accesstoken','refreshtoken','authtoken','bearertoken','bindpassword','bindpw','authpass','privpass','community','communitystring','otpseed','totpseed','hotpseed','tlsauthkey','tlscryptkey','recoverycode','recoverycodes','passwordhash','bcrypthash')
  foreach($suffix in $suffixes) { if ($n.EndsWith($suffix,[StringComparison]::OrdinalIgnoreCase)) { return $true } }
  if ($n.EndsWith('key',[StringComparison]::OrdinalIgnoreCase)) {
    $safe=@('pubkey','publickey','sshpublickey','keyid','keytype','keysize','keylength','keyalgorithm','keyexchange','prefetchkey')
    if (-not ($safe -contains $n)) { return $true }
  }
  return $false
}

function Test-SensitiveElement([System.Xml.XmlElement]$Element) {
  if ($null -eq $Element) { return $false }
  if (Test-SensitiveName $Element.Name) { return $true }
  if ((Get-NormalizedName $Element.Name) -eq 'subscription') {
    $p=$Element.ParentNode; $g=if($null -ne $p){$p.ParentNode}else{$null}
    if ($null -ne $p -and $null -ne $g -and (Get-NormalizedName $p.Name) -eq 'firmware' -and (Get-NormalizedName $g.Name) -eq 'system') { return $true }
  }
  return $false
}

function Resolve-FileSystemPath([string]$Path) {
  try { return $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path) }
  catch { throw "Could not resolve filesystem path '$Path': $($_.Exception.Message)" }
}

function Ensure-ParentDirectory([string]$FilePath) {
  $dir=Split-Path -Parent $FilePath
  if ([string]::IsNullOrWhiteSpace($dir)) { return }
  if (Test-Path -LiteralPath $dir) {
    if (-not (Test-Path -LiteralPath $dir -PathType Container)) { throw "Expected directory path exists as a file: $dir" }
    return
  }
  New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

function Get-XmlNodePath([System.Xml.XmlNode]$Node) {
  if ($null -eq $Node) { return '/' }
  $parts=New-Object 'System.Collections.Generic.List[string]'
  $cur=$Node
  while($null -ne $cur -and $cur.NodeType -ne [System.Xml.XmlNodeType]::Document) {
    if ($cur.NodeType -eq [System.Xml.XmlNodeType]::Element) {
      $index=1; $s=$cur.PreviousSibling
      while($null -ne $s) { if ($s.NodeType -eq [System.Xml.XmlNodeType]::Element -and $s.Name -eq $cur.Name) { $index++ }; $s=$s.PreviousSibling }
      $parts.Add(('{0}[{1}]' -f $cur.Name,$index)) | Out-Null
    }
    $cur=$cur.ParentNode
  }
  $a=$parts.ToArray(); [array]::Reverse($a); return '/' + ($a -join '/')
}

function Add-Event([System.Collections.Generic.List[object]]$Events,[string]$Kind,[string]$Path,[string]$Rule) {
  $Events.Add([pscustomobject]@{kind=$Kind;path=$Path;rule=$Rule}) | Out-Null
}

function Protect-EmbeddedSecretText([string]$Text,[string]$Replacement) {
  if ([string]::IsNullOrEmpty($Text)) { return [pscustomobject]@{Text=$Text;Count=0;Rules=@()} }
  $result=$Text; $count=0; $rules=New-Object 'System.Collections.Generic.List[string]'
  $patterns=@(
    @{Name='PEM private key';Pattern='(?is)-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----.*?-----END(?: [A-Z0-9]+)? PRIVATE KEY-----';Replace=$Replacement},
    @{Name='Credential in URL';Pattern='(?i)(\b[a-z][a-z0-9+.-]*://[^\s/:@]+:)([^\s/@]+)(@)';Replace=('$1'+$Replacement+'$3')},
    @{Name='Embedded credential assignment';Pattern='(?im)(\b(?:password|passwd|passphrase|pwd|secret|shared[_-]?secret|client[_-]?secret|api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|bearer[_-]?token|private[_-]?key|privkey|psk|pre[_-]?shared[_-]?key|bind[_-]?(?:pw|password)|community|authpass|privpass|otp[_-]?seed|totp[_-]?seed)\b\s*[:=]\s*)("[^"]*"|[^\s;,\r\n<]+)';Replace=('$1'+$Replacement)},
    @{Name='Embedded credential argument';Pattern='(?im)(--?(?:password|passwd|passphrase|secret|client-secret|api-key|token|access-token|refresh-token|private-key|psk|community)\s*(?:=|\s)\s*)("[^"]*"|[^\s;,\r\n<]+)';Replace=('$1'+$Replacement)}
  )
  foreach($p in $patterns) {
    $m=[regex]::Matches($result,$p.Pattern)
    if ($m.Count -gt 0) { $count+=$m.Count; $rules.Add($p.Name)|Out-Null; $result=[regex]::Replace($result,$p.Pattern,$p.Replace) }
  }
  return [pscustomobject]@{Text=$result;Count=$count;Rules=$rules.ToArray()}
}

function Remove-AuditMetadata([System.Xml.XmlDocument]$Document,[System.Collections.Generic.List[object]]$Events) {
  $removed=0
  $sets=@(
    $Document.SelectNodes("//*[local-name()='created'][*[local-name()='username'] and *[local-name()='time']]"),
    $Document.SelectNodes("//*[local-name()='updated'][*[local-name()='username'] and *[local-name()='time']]"),
    $Document.SelectNodes("/*[local-name()='opnsense']/*[local-name()='revision']")
  )
  foreach($set in $sets) { foreach($node in @($set)) {
    if ($null -eq $node -or $null -eq $node.ParentNode) { continue }
    $path=Get-XmlNodePath $node; $node.ParentNode.RemoveChild($node)|Out-Null; $removed++
    Add-Event $Events 'removed-node' $path 'Operational audit metadata removed'
  }}
  return $removed
}

function Get-ResidualFindings([System.Xml.XmlDocument]$Document,[string]$Replacement) {
  $findings=New-Object 'System.Collections.Generic.List[object]'
  foreach($e in @($Document.SelectNodes('//*'))) {
    if ((Test-SensitiveElement $e) -and -not [string]::IsNullOrWhiteSpace($e.InnerText) -and $e.InnerText -ne $Replacement) {
      $findings.Add([pscustomobject]@{severity='high';path=(Get-XmlNodePath $e);reason='Sensitive element still contains a value'})|Out-Null
    }
    foreach($a in @($e.Attributes)) { if ((Test-SensitiveName $a.Name) -and -not [string]::IsNullOrWhiteSpace($a.Value) -and $a.Value -ne $Replacement) {
      $findings.Add([pscustomobject]@{severity='high';path=((Get-XmlNodePath $e)+'/@'+$a.Name);reason='Sensitive attribute still contains a value'})|Out-Null
    }}
  }

  $checks=@(
    @{Name='Private key marker';Pattern='(?i)-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----'},
    @{Name='bcrypt password hash';Pattern='(?i)\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}'},
    @{Name='SHA-crypt password hash';Pattern='(?i)\$[56]\$[^\s$]+\$[./A-Za-z0-9]{20,}'}
  )
  $basicAuthPattern='(?i)\b[a-z][a-z0-9+.-]*://[^\s/:@]+:([^\s/@]+)@'

  foreach($n in @($Document.SelectNodes('//text() | //comment() | //processing-instruction()'))) {
    if ([string]::IsNullOrWhiteSpace($n.Value)) { continue }
    $owner=$n.ParentNode; $path=if($null -ne $owner){Get-XmlNodePath $owner}else{'/'}

    foreach($c in $checks) { if ([regex]::IsMatch($n.Value,$c.Pattern)) {
      $findings.Add([pscustomobject]@{severity='high';path=$path;reason=$c.Name})|Out-Null
    }}

    foreach($m in [regex]::Matches($n.Value,$basicAuthPattern)) {
      if ($m.Groups.Count -gt 1 -and $m.Groups[1].Value -ne $Replacement) {
        $findings.Add([pscustomobject]@{severity='high';path=$path;reason='Basic-auth style URL'})|Out-Null
      }
    }
  }
  return $findings.ToArray()
}

try {
  if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf)) { throw "Input file not found: $InputPath" }
  $resolvedInput=(Resolve-Path -LiteralPath $InputPath).Path
  if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath=Join-Path ([IO.Path]::GetDirectoryName($resolvedInput)) (([IO.Path]::GetFileNameWithoutExtension($resolvedInput))+'.sanitized.xml')
  }
  $fullOutput=Resolve-FileSystemPath $OutputPath
  if ([string]::Equals($resolvedInput,$fullOutput,[StringComparison]::OrdinalIgnoreCase)) { throw 'OutputPath must not be the same file as InputPath.' }
  if ([string]::IsNullOrWhiteSpace($ReportPath)) {
    $ReportPath=Join-Path ([IO.Path]::GetDirectoryName($fullOutput)) (([IO.Path]::GetFileNameWithoutExtension($fullOutput))+'.sanitization-report.json')
  }
  $fullReport=Resolve-FileSystemPath $ReportPath
  Ensure-ParentDirectory $fullOutput; Ensure-ParentDirectory $fullReport

  $settings=New-Object System.Xml.XmlReaderSettings; $settings.DtdProcessing=[System.Xml.DtdProcessing]::Prohibit; $settings.XmlResolver=$null
  $doc=New-Object System.Xml.XmlDocument; $doc.PreserveWhitespace=$false; $doc.XmlResolver=$null
  $reader=$null
  try { $reader=[System.Xml.XmlReader]::Create($resolvedInput,$settings); $doc.Load($reader) } finally { if($null -ne $reader){$reader.Dispose()} }
  if ($null -eq $doc.DocumentElement) { throw 'Input does not contain a valid XML document element.' }

  $events=New-Object 'System.Collections.Generic.List[object]'; $elementCount=0; $attributeCount=0; $embeddedCount=0
  foreach($e in @($doc.SelectNodes('//*'))) {
    if ($e -ne $doc.DocumentElement -and $null -eq $e.ParentNode) { continue }
    if (Test-SensitiveElement $e) {
      if (-not [string]::IsNullOrWhiteSpace($e.InnerText) -or $e.HasChildNodes) {
        $path=Get-XmlNodePath $e; $name=$e.Name; $e.RemoveAll(); $e.InnerText=$RedactionText; $elementCount++; Add-Event $events 'element' $path ('Sensitive field name: '+$name)
      }
      continue
    }
    foreach($a in @($e.Attributes)) { if ((Test-SensitiveName $a.Name) -and -not [string]::IsNullOrWhiteSpace($a.Value)) {
      $path=(Get-XmlNodePath $e)+'/@'+$a.Name; $name=$a.Name; $a.Value=$RedactionText; $attributeCount++; Add-Event $events 'attribute' $path ('Sensitive attribute name: '+$name)
    }}
  }
  $removedAudit=Remove-AuditMetadata $doc $events
  foreach($n in @($doc.SelectNodes('//text() | //comment() | //processing-instruction()'))) {
    if ([string]::IsNullOrEmpty($n.Value) -or $n.Value -eq $RedactionText) { continue }
    $p=Protect-EmbeddedSecretText $n.Value $RedactionText
    if ($p.Count -gt 0) { $owner=$n.ParentNode; $path=if($null -ne $owner){Get-XmlNodePath $owner}else{'/'}; $n.Value=$p.Text; $embeddedCount+=$p.Count; foreach($r in $p.Rules){Add-Event $events 'embedded-content' $path $r} }
  }

  $residual=@(Get-ResidualFindings $doc $RedactionText); $status=if($residual.Count -eq 0){'Clean'}else{'RequiresReview'}
  $utf8=New-Object System.Text.UTF8Encoding($false); $ws=New-Object System.Xml.XmlWriterSettings; $ws.Encoding=$utf8; $ws.Indent=$true; $ws.IndentChars='  '; $ws.NewLineChars="`n"; $ws.NewLineHandling=[System.Xml.NewLineHandling]::Replace
  $writer=$null; try { $writer=[System.Xml.XmlWriter]::Create($fullOutput,$ws); $doc.Save($writer) } finally { if($null -ne $writer){$writer.Dispose()} }

  $inputInfo=Get-Item -LiteralPath $resolvedInput; $outputInfo=Get-Item -LiteralPath $fullOutput
  $orderedRedactions=@($events.ToArray() | Sort-Object path,kind,rule); $orderedResidual=@($residual | Sort-Object path,reason)
  $report=[ordered]@{
    schemaVersion=$ReportSchemaVersion; sanitizerVersion=$SanitizerVersion; generatedUtc=[DateTime]::UtcNow.ToString('o'); status=$status
    source=[ordered]@{fileName=$inputInfo.Name;sizeBytes=$inputInfo.Length;sha256=(Get-FileHash -LiteralPath $resolvedInput -Algorithm SHA256).Hash}
    output=[ordered]@{fileName=$outputInfo.Name;sizeBytes=$outputInfo.Length;sha256=(Get-FileHash -LiteralPath $fullOutput -Algorithm SHA256).Hash}
    redactionSummary=[ordered]@{elementValues=$elementCount;attributeValues=$attributeCount;embeddedPatterns=$embeddedCount;removedAuditNodes=$removedAudit;total=($elementCount+$attributeCount+$embeddedCount+$removedAudit)}
    redactions=$orderedRedactions; residualFindings=$orderedResidual
    notes=@('No original secret values or local full paths are written to this report.','Clean means no known residual secrets; it does not mean anonymized.','Network-relevant values are intentionally preserved.','Unknown third-party plugin formats can require additional rules.')
  }
  [IO.File]::WriteAllText($fullReport,($report|ConvertTo-Json -Depth 8),$utf8)
  Write-Host "Sanitizer status: $status"
  Write-Host "Sanitized XML: $fullOutput"
  Write-Host "Report: $fullReport"
  if ($residual.Count -gt 0 -and $FailOnResidualSecrets) { throw 'Residual secret scan failed. Output requires review.' }
}
catch {
  Write-Error ("Sanitizer failed: {0}" -f $_.Exception.Message)
  if ($_.ScriptStackTrace) { Write-Host ('Stack trace: '+$_.ScriptStackTrace) }
  exit 1
}

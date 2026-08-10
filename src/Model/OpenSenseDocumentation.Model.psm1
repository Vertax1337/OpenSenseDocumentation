Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function ConvertTo-StableIdToken {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [ValidateNotNullOrEmpty()]
        [string]$Value
    )

    $token = $Value.Trim().ToLowerInvariant()
    $token = [regex]::Replace($token, '[^a-z0-9._~-]+', '-')
    $token = [regex]::Replace($token, '-{2,}', '-')
    $token = $token.Trim('-')

    if ([string]::IsNullOrWhiteSpace($token)) {
        throw 'Stable ID token is empty after normalization.'
    }

    return $token
}

function New-StableModelId {
    <#
    .SYNOPSIS
      Creates deterministic namespaced IDs for Canonical Infrastructure Model objects.

    .DESCRIPTION
      Prefer -NaturalId when OPNsense exposes a stable UUID/key/name.
      Use -IdentityParts only when no stable natural identifier exists.

      IdentityParts are encoded with length prefixes before hashing so values such as
      ('ab','c') and ('a','bc') cannot produce the same preimage.
    #>
    [CmdletBinding(DefaultParameterSetName='Natural')]
    param(
        [Parameter(Mandatory=$true)]
        [ValidatePattern('^[A-Za-z][A-Za-z0-9-]*$')]
        [string]$Namespace,

        [Parameter(Mandatory=$true, ParameterSetName='Natural')]
        [ValidateNotNullOrEmpty()]
        [string]$NaturalId,

        [Parameter(Mandatory=$true, ParameterSetName='Hash')]
        [ValidateNotNullOrEmpty()]
        [string[]]$IdentityParts
    )

    $ns = ConvertTo-StableIdToken -Value $Namespace

    if ($PSCmdlet.ParameterSetName -eq 'Natural') {
        $token = ConvertTo-StableIdToken -Value $NaturalId
        return ('{0}:{1}' -f $ns, $token)
    }

    $encoded = New-Object System.Collections.Generic.List[string]
    foreach ($part in $IdentityParts) {
        if ($null -eq $part) {
            throw 'IdentityParts must not contain null values.'
        }

        $value = [string]$part
        $encoded.Add(('{0}:{1}' -f $value.Length, $value)) | Out-Null
    }

    $preimage = $encoded.ToArray() -join '|'
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($preimage)
        $hash = $sha.ComputeHash($bytes)
    }
    finally {
        $sha.Dispose()
    }

    $hex = -join ($hash | ForEach-Object { $_.ToString('x2') })
    return ('{0}:sha256:{1}' -f $ns, $hex.Substring(0,24))
}

Export-ModuleMember -Function ConvertTo-StableIdToken, New-StableModelId

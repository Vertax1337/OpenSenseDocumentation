$modulePath = Join-Path $PSScriptRoot '..\..\src\Model\OpenSenseDocumentation.Model.psm1'
Import-Module $modulePath -Force

Describe 'Canonical Model stable IDs' {
    It 'normalizes natural IDs deterministically' {
        New-StableModelId -Namespace 'Interface' -NaturalId ' LAN ' |
            Should -Be 'interface:lan'
    }

    It 'creates the same hash ID for the same identity tuple' {
        $a = New-StableModelId -Namespace 'Asset' -IdentityParts @('02:00:00:00:00:60','192.0.2.60')
        $b = New-StableModelId -Namespace 'Asset' -IdentityParts @('02:00:00:00:00:60','192.0.2.60')
        $a | Should -Be $b
        $a | Should -Be 'asset:sha256:612f197baa4b231e592d4c87'
    }

    It 'creates different IDs when identity tuple order changes' {
        $a = New-StableModelId -Namespace 'Asset' -IdentityParts @('A','BC')
        $b = New-StableModelId -Namespace 'Asset' -IdentityParts @('BC','A')
        $a | Should -Not -Be $b
    }

    It 'uses length-prefix encoding to avoid tuple delimiter ambiguity' {
        $a = New-StableModelId -Namespace 'Test' -IdentityParts @('ab','c')
        $b = New-StableModelId -Namespace 'Test' -IdentityParts @('a','bc')
        $a | Should -Not -Be $b
    }

    It 'matches the schema stable ID syntax' {
        $id = New-StableModelId -Namespace 'Route' -NaturalId 'BD8BE173-BAD5-47C0-9702-386EF25F8114'
        $id | Should -Match '^[a-z][a-z0-9-]*:[A-Za-z0-9][A-Za-z0-9._~:/-]*$'
    }
}

function Get-Widget {
    param([string]$Name)
    Write-Output "widget $Name"
}

function Set-Widget {
    param([string]$Name, [int]$Size)
    Write-Output "$Name $Size"
}

class Widget {
    [string]$Name
    Widget([string]$n) { $this.Name = $n }
    [string] Describe() { return $this.Name }
}

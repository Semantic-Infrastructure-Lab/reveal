"""Tests for PowerShell analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.powershell import PowerShellAnalyzer


class TestPowerShellAnalyzer(unittest.TestCase):
    """Test PowerShell script analysis."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_ps1_file(self, content: str, name: str = "test.ps1") -> str:
        """Helper: Create PowerShell file with given content."""
        path = os.path.join(self.temp_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_basic_function_definition(self):
        """Test basic PowerShell function extraction."""
        content = """
function Get-UserInfo {
    param($Username)
    Write-Host "Getting info for $Username"
}

function Set-Configuration {
    param($ConfigPath)
    Write-Host "Setting config from $ConfigPath"
}
"""

        path = self.create_ps1_file(content)
        analyzer = PowerShellAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertIn('functions', structure)
        self.assertEqual(len(structure['functions']), 2)

        func_names = [f['name'] for f in structure['functions']]
        self.assertIn('Get-UserInfo', func_names)
        self.assertIn('Set-Configuration', func_names)

    def test_function_with_parameters(self):
        """Test function with parameter block."""
        content = """
function Deploy-Application {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string]$AppName,

        [Parameter(Mandatory=$false)]
        [string]$Environment = "Production"
    )

    Write-Host "Deploying $AppName to $Environment"
}
"""

        path = self.create_ps1_file(content)
        analyzer = PowerShellAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertIn('functions', structure)
        self.assertEqual(len(structure['functions']), 1)
        self.assertEqual(structure['functions'][0]['name'], 'Deploy-Application')

    def test_filter_statement(self):
        """Test PowerShell filter extraction."""
        content = """
filter Select-Even {
    if ($_ % 2 -eq 0) {
        $_
    }
}
"""

        path = self.create_ps1_file(content)
        analyzer = PowerShellAnalyzer(path)
        structure = analyzer.get_structure()

        # Filters should be extracted as functions
        self.assertIn('functions', structure)
        func_names = [f['name'] for f in structure['functions']]
        self.assertIn('Select-Even', func_names)

    def test_workflow_statement(self):
        """Test PowerShell workflow extraction."""
        content = """
workflow Test-Workflow {
    param($ComputerName)

    InlineScript {
        Write-Host "Running on $using:ComputerName"
    }
}
"""

        path = self.create_ps1_file(content)
        analyzer = PowerShellAnalyzer(path)
        structure = analyzer.get_structure()

        # Workflows should be extracted as functions
        self.assertIn('functions', structure)
        func_names = [f['name'] for f in structure['functions']]
        self.assertIn('Test-Workflow', func_names)

    def test_class_definition(self):
        """Test PowerShell class parsing (PowerShell 5.0+).

        Note: Tree-sitter PowerShell parser may not fully support class extraction yet.
        This test verifies the file can be parsed without errors.
        """
        content = """
class DatabaseConnection {
    [string]$Server
    [int]$Port
    [string]$Database

    DatabaseConnection([string]$server, [int]$port) {
        $this.Server = $server
        $this.Port = $port
    }

    [void]Connect() {
        Write-Host "Connecting to $($this.Server):$($this.Port)"
    }
}
"""

        path = self.create_ps1_file(content)
        analyzer = PowerShellAnalyzer(path)
        structure = analyzer.get_structure()

        # Verify file parsed successfully (may not extract classes yet)
        self.assertIsInstance(structure, dict)

    def test_multiple_functions(self):
        """Test extraction of multiple functions."""
        content = """
function Initialize-Application {
    param($ConfigPath)
    $config = Get-Content $ConfigPath | ConvertFrom-Json
    return $config
}

function Start-Service {
    param($ServiceName)
    Start-Service -Name $ServiceName
}

function Stop-Service {
    param($ServiceName)
    Stop-Service -Name $ServiceName
}
"""

        path = self.create_ps1_file(content)
        analyzer = PowerShellAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertIn('functions', structure)
        self.assertEqual(len(structure['functions']), 3)

        func_names = [f['name'] for f in structure['functions']]
        self.assertIn('Initialize-Application', func_names)
        self.assertIn('Start-Service', func_names)
        self.assertIn('Stop-Service', func_names)

    def test_advanced_function_with_cmdletbinding(self):
        """Test advanced function with CmdletBinding attribute."""
        content = """
function Get-ProcessInfo {
    [CmdletBinding(SupportsShouldProcess=$true)]
    param(
        [Parameter(Mandatory=$true, ValueFromPipeline=$true)]
        [string[]]$ProcessName,

        [ValidateSet('Low', 'Normal', 'High')]
        [string]$Priority = 'Normal'
    )

    begin {
        Write-Verbose "Starting process info retrieval"
    }

    process {
        foreach ($name in $ProcessName) {
            Get-Process -Name $name
        }
    }

    end {
        Write-Verbose "Completed process info retrieval"
    }
}
"""

        path = self.create_ps1_file(content)
        analyzer = PowerShellAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertIn('functions', structure)
        self.assertEqual(len(structure['functions']), 1)
        self.assertEqual(structure['functions'][0]['name'], 'Get-ProcessInfo')

    def test_head_filtering(self):
        """Test head parameter for filtering functions."""
        content = """
function Func1 { Write-Host "1" }
function Func2 { Write-Host "2" }
function Func3 { Write-Host "3" }
function Func4 { Write-Host "4" }
function Func5 { Write-Host "5" }
"""

        path = self.create_ps1_file(content)
        analyzer = PowerShellAnalyzer(path)
        structure = analyzer.get_structure(head=3)

        self.assertIn('functions', structure)
        self.assertEqual(len(structure['functions']), 3)
        func_names = [f['name'] for f in structure['functions']]
        self.assertIn('Func1', func_names)
        self.assertIn('Func2', func_names)
        self.assertIn('Func3', func_names)
        self.assertNotIn('Func4', func_names)

    def test_tail_filtering(self):
        """Test tail parameter for filtering functions."""
        content = """
function Func1 { Write-Host "1" }
function Func2 { Write-Host "2" }
function Func3 { Write-Host "3" }
function Func4 { Write-Host "4" }
function Func5 { Write-Host "5" }
"""

        path = self.create_ps1_file(content)
        analyzer = PowerShellAnalyzer(path)
        structure = analyzer.get_structure(tail=2)

        self.assertIn('functions', structure)
        self.assertEqual(len(structure['functions']), 2)
        func_names = [f['name'] for f in structure['functions']]
        self.assertIn('Func4', func_names)
        self.assertIn('Func5', func_names)

    def test_range_filtering(self):
        """Test range parameter for filtering functions."""
        content = """
function Func1 { Write-Host "1" }
function Func2 { Write-Host "2" }
function Func3 { Write-Host "3" }
function Func4 { Write-Host "4" }
function Func5 { Write-Host "5" }
"""

        path = self.create_ps1_file(content)
        analyzer = PowerShellAnalyzer(path)
        structure = analyzer.get_structure(range=(2, 4))

        self.assertIn('functions', structure)
        self.assertEqual(len(structure['functions']), 3)
        func_names = [f['name'] for f in structure['functions']]
        self.assertIn('Func2', func_names)
        self.assertIn('Func3', func_names)
        self.assertIn('Func4', func_names)

    def test_real_world_deployment_script(self):
        """Test real-world PowerShell deployment script."""
        content = """
# Azure Web App Deployment Script

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory=$true)]
    [string]$WebAppName,

    [Parameter(Mandatory=$false)]
    [string]$Location = "East US"
)

function Test-Prerequisites {
    [CmdletBinding()]
    param()

    Write-Host "Checking Azure CLI..."
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        throw "Azure CLI not found"
    }
}

function New-ResourceGroupIfNotExists {
    [CmdletBinding()]
    param(
        [string]$Name,
        [string]$Location
    )

    $rg = az group show --name $Name 2>$null
    if (-not $rg) {
        Write-Host "Creating resource group $Name..."
        az group create --name $Name --location $Location
    }
}

function Deploy-WebApp {
    [CmdletBinding()]
    param(
        [string]$ResourceGroup,
        [string]$WebAppName
    )

    Write-Host "Deploying web app $WebAppName..."
    az webapp create --resource-group $ResourceGroup --name $WebAppName
}

# Main execution
Test-Prerequisites
New-ResourceGroupIfNotExists -Name $ResourceGroup -Location $Location
Deploy-WebApp -ResourceGroup $ResourceGroup -WebAppName $WebAppName
"""

        path = self.create_ps1_file(content, 'deploy.ps1')
        analyzer = PowerShellAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertIn('functions', structure)
        self.assertEqual(len(structure['functions']), 3)

        func_names = [f['name'] for f in structure['functions']]
        self.assertIn('Test-Prerequisites', func_names)
        self.assertIn('New-ResourceGroupIfNotExists', func_names)
        self.assertIn('Deploy-WebApp', func_names)

    def test_empty_file(self):
        """Test handling of empty PowerShell file."""
        content = ""

        path = self.create_ps1_file(content)
        analyzer = PowerShellAnalyzer(path)
        structure = analyzer.get_structure()

        # Should return empty dict or dict with empty lists
        self.assertIsInstance(structure, dict)

    def test_comments_only(self):
        """Test file with only comments."""
        content = """
# This is a comment
# Another comment

<#
Multi-line comment
block
#>
"""

        path = self.create_ps1_file(content)
        analyzer = PowerShellAnalyzer(path)
        structure = analyzer.get_structure()

        # Should not extract anything
        self.assertEqual(len(structure.get('functions', [])), 0)

    def test_module_file_extension(self):
        """Test .psm1 (PowerShell module) file extension."""
        content = """
function Export-ModuleFunction {
    param($Data)
    Write-Host "Exporting $Data"
}

Export-ModuleMember -Function Export-ModuleFunction
"""

        path = self.create_ps1_file(content, 'test.psm1')
        analyzer = PowerShellAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertIn('functions', structure)
        func_names = [f['name'] for f in structure['functions']]
        self.assertIn('Export-ModuleFunction', func_names)


if __name__ == '__main__':
    unittest.main()

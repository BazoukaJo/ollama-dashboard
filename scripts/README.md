# 🚀 Ollama Dashboard Auto-Start Scripts

> These scripts automatically start and stop the Ollama Dashboard based on Ollama's status.

## 📁 Files

- **`ollama-dashboard-monitor.ps1`** - Advanced service monitor with install/uninstall capabilities
- **`start-with-ollama.ps1`** - PowerShell script with monitoring features
- **`start-with-ollama.bat`** - Simple batch file with basic monitoring

## ⚡ Quick Start

### 🔄 Automatic Management (Recommended)
```powershell
# Install as a service (runs automatically with Windows)
.\scripts\ollama-dashboard-monitor.ps1 -Install

# Check status
.\scripts\ollama-dashboard-monitor.ps1 -Status
```

### 👥 Manual Monitoring
```powershell
# PowerShell monitor
.\scripts\start-with-ollama.ps1 -Monitor

# Batch monitor
scripts\start-with-ollama.bat
```

## ✨ Features

### 🔧 Service Monitor (`ollama-dashboard-monitor.ps1`)
- ✅ **Automatic installation** as Windows scheduled task
- ✅ **Service management** (install/uninstall/start/stop/status)
- ✅ **Background monitoring** with logging
- ✅ **Automatic start/stop** based on Ollama status
- ✅ **Process cleanup** and error handling
- ✅ **Status reporting** and health checks

### 🐚 PowerShell Script (`start-with-ollama.ps1`)
- ✅ **Advanced monitoring** with continuous checks
- ✅ **Automatic lifecycle management**
- ✅ **Colored output** and detailed logging
- ✅ **Configurable check intervals**
- ✅ **Process cleanup** to prevent duplicates

### 📜 Batch File (`start-with-ollama.bat`)
- ✅ **Simple monitoring loop**
- ✅ **Automatic start/stop** based on Ollama status
- ✅ **Minimal dependencies**
- ✅ **Continuous monitoring** until manually stopped

## 📖 Usage

### 🔧 Service Monitor (Recommended for permanent setup)

##### Install the service
```powershell
# Run as Administrator
.\scripts\ollama-dashboard-monitor.ps1 -Install
```

##### Manage the service
```powershell
# Check status
.\scripts\ollama-dashboard-monitor.ps1 -Status

# Start monitoring
.\scripts\ollama-dashboard-monitor.ps1 -Start

# Stop monitoring
.\scripts\ollama-dashboard-monitor.ps1 -Stop

# Uninstall service
.\scripts\ollama-dashboard-monitor.ps1 -Uninstall
```

### 🐚 PowerShell Script

##### One-time start
```powershell
.\scripts\start-with-ollama.ps1
```

##### Monitor mode
```powershell
.\scripts\start-with-ollama.ps1 -Monitor
```

##### Custom check interval
```powershell
.\scripts\start-with-ollama.ps1 -Monitor -CheckInterval 5
```

### 📜 Batch File

##### Start monitoring
```cmd
scripts\start-with-ollama.bat
```

## 📋 Requirements

- **Windows PowerShell** (for `.ps1` scripts)
- **Python** installed and in PATH
- **Ollama Dashboard dependencies** installed (`pip install -r requirements.txt`)
- **Administrator privileges** (for service installation)

## 🔄 How It Works

1. **🔍 Process Detection**: Monitors for running `ollama.exe` process
2. **⚙️ Automatic Management**: Starts/stops dashboard based on Ollama status
3. **🔄 Lifecycle Control**: Ensures only one dashboard instance runs
4. **🌐 Background Operation**: Service monitor runs continuously in background

## 💡 Examples

### 🔧 Service Installation (Recommended)
```powershell
# Install as automatic service
.\scripts\ollama-dashboard-monitor.ps1 -Install

# Check everything is working
.\scripts\ollama-dashboard-monitor.ps1 -Status
```

### 👥 Manual Monitoring
```powershell
# PowerShell monitor
.\scripts\start-with-ollama.ps1 -Monitor

# Batch monitor
scripts\start-with-ollama.bat
```

## 🔗 Integration Options

### 📂 Windows Startup Folder
1. Press `Win + R`, type `shell:startup`
2. Create shortcut to `scripts\start-with-ollama.ps1 -Monitor`

### ⏰ Task Scheduler
1. Create new task with "At startup" trigger
2. Action: `powershell.exe -ExecutionPolicy Bypass -File "C:\path\to\scripts\start-with-ollama.ps1" -Monitor`

### 📜 Startup Script
Add to your PowerShell profile or batch startup script.

## 🛠️ Troubleshooting

- **🔒 Permission denied**: Run PowerShell as Administrator for service operations
- **🚫 Script won't run**: Set execution policy: `Set-ExecutionPolicy RemoteSigned`
- **🔍 Ollama not detected**: Ensure Ollama is fully started (`ollama serve`)
- **🚫 Dashboard won't start**: Check Python path and dependencies
- **⚙️ Service won't install**: Run as Administrator and check Task Scheduler permissions

## 📝 Logs

Service monitor logs to: `%TEMP%\ollama-dashboard-monitor.log`

---

<div align="center">

**Made with ❤️ for Ollama Dashboard**

</div>

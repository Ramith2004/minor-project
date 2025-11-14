"""
Smart Meter System Launcher - Windows Version
Starts all services with organized logging and proper dependency order
"""

import subprocess
import time
import os
import sys
import signal
from pathlib import Path
from typing import List
import platform

# Verify we're on Windows
if platform.system() != "Windows":
    print("ERROR: This script is for Windows only. Use run.py on Linux/Mac.")
    sys.exit(1)

# ANSI colors for Windows terminal (requires Windows 10+)
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

# Enable ANSI colors on Windows
os.system('')

class ServiceManager:
    def __init__(self):
        self.processes = {}
        self.project_dir = Path(__file__).parent
        self.log_dir = self.project_dir / "logs"
        self.log_dir.mkdir(exist_ok=True)
        # Windows uses Scripts folder instead of bin
        self.venv_python = self.project_dir / "venv" / "Scripts" / "python.exe"
        
    def print_header(self, text):
        print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"{Colors.HEADER}{Colors.BOLD}{text:^60}{Colors.END}")
        print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.END}\n")
    
    def print_status(self, service, status, message=""):
        symbols = {"starting": "🚀", "running": "✅", "error": "❌", "stopped": "🛑", "checking": "🔍", "waiting": "⏳"}
        colors = {"starting": Colors.BLUE, "running": Colors.GREEN, "error": Colors.RED, "stopped": Colors.YELLOW, "checking": Colors.BLUE, "waiting": Colors.YELLOW}
        
        print(f"{colors.get(status, '')}{symbols.get(status, '•')} {service:20} {status.upper():10} {message}{Colors.END}")
    
    def check_venv(self):
        """Check if virtual environment exists"""
        self.print_status("Virtual Env", "checking", f"Looking for venv at {self.venv_python}")
        
        if not self.venv_python.exists():
            self.print_status("Virtual Env", "error", "venv not found! Run: python -m venv venv")
            return False
        
        self.print_status("Virtual Env", "running", "Found ✓")
        return True
    
    def check_ganache(self):
        """Check if Ganache CLI is installed"""
        try:
            # Try both ganache.cmd and ganache-cli.cmd
            for cmd in ["ganache.cmd", "ganache-cli.cmd", "ganache"]:
                try:
                    result = subprocess.run([cmd, "--version"], 
                                          capture_output=True, text=True, timeout=5, shell=True)
                    if result.returncode == 0:
                        self.print_status("Ganache Check", "running", "Installed ✓")
                        return True
                except:
                    continue
            
            self.print_status("Ganache Check", "error", "Not found! Run: npm install -g ganache")
            return False
        except:
            self.print_status("Ganache Check", "error", "Not found! Run: npm install -g ganache")
            return False
    
    def check_mosquitto(self):
        """Check if Mosquitto MQTT broker is running (Windows)"""
        try:
            # Check if mosquitto service is running on Windows
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq mosquitto.exe'],
                capture_output=True, text=True, timeout=5, shell=True
            )
            
            if "mosquitto.exe" in result.stdout:
                self.print_status("MQTT Broker", "running", "Mosquitto running ✓")
                return True
            else:
                self.print_status("MQTT Broker", "error", "Mosquitto not running! Start from Services or run: net start mosquitto")
                return False
        except Exception as e:
            self.print_status("MQTT Broker", "error", f"Could not check Mosquitto status: {e}")
            return False
    
    def start_service(self, name, command, cwd=None, env=None, shell=False):
        """Start a service with logging (Windows)"""
        log_file = self.log_dir / f"{name}.log"
        
        try:
            self.print_status(name, "starting", f"(log: logs\\{name}.log)")
            
            with open(log_file, 'w') as log:
                log.write(f"=== {name} started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
            
            process_env = os.environ.copy()
            if env:
                process_env.update(env)
            
            with open(log_file, 'a') as log:
                # Windows-specific: Use CREATE_NEW_PROCESS_GROUP instead of Unix signals
                process = subprocess.Popen(
                    command,
                    cwd=cwd or self.project_dir,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=process_env,
                    bufsize=1,
                    universal_newlines=True,
                    shell=shell,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') else 0
                )
            
            self.processes[name] = {"process": process, "log": log_file}
            time.sleep(1)
            
            if process.poll() is None:
                self.print_status(name, "running", f"PID: {process.pid}")
                return True
            else:
                self.print_status(name, "error", "Failed to start")
                return False
                
        except Exception as e:
            self.print_status(name, "error", str(e))
            return False
    
    def check_service(self, name, url, max_retries=10):
        """Check if service is responding"""
        import urllib.request
        
        for i in range(max_retries):
            try:
                urllib.request.urlopen(url, timeout=1)
                return True
            except:
                time.sleep(1)
        return False
    
    def check_port(self, port, max_retries=10):
        """Check if a port is listening"""
        import socket
        
        for i in range(max_retries):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', port))
                sock.close()
                if result == 0:
                    return True
            except:
                pass
            time.sleep(1)
        return False
    
    def deploy_contracts(self):
        """Deploy smart contracts automatically"""
        self.print_status("Contracts", "starting", "Deploying smart contracts...")
        
        deploy_script = self.project_dir / "scripts" / "deploy.py"
        
        try:
            result = subprocess.run(
                [str(self.venv_python), str(deploy_script)],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=60,
                encoding='utf-8',  # Force UTF-8 encoding
                errors='replace'   # Replace invalid characters instead of failing
            )
            
            if result.returncode == 0:
                self.print_status("Contracts", "running", "Deployment successful ✓")
                
                # Parse contract addresses from output
                output = result.stdout
                if output and "MeterRegistry:" in output:
                    for line in output.split('\n'):
                        if "MeterRegistry:" in line:
                            addr = line.split(':')[1].strip()
                            print(f"   {Colors.GREEN}MeterRegistry: {addr}{Colors.END}")
                        elif "Consensus:" in line and "MeterRegistry" not in line:
                            addr = line.split(':')[1].strip()
                            print(f"   {Colors.GREEN}Consensus: {addr}{Colors.END}")
                        elif "MeterStore:" in line:
                            addr = line.split(':')[1].strip()
                            print(f"   {Colors.GREEN}MeterStore: {addr}{Colors.END}")
                
                return True
            else:
                self.print_status("Contracts", "error", "Deployment failed")
                print(f"{Colors.RED}Error output:{Colors.END}\n{result.stderr}")
                return False
                
        except Exception as e:
            self.print_status("Contracts", "error", str(e))
            return False
    
    def ensure_meter_keys(self, meter_ids: List[str]):
        """Ensure keys exist for all meters, create if missing"""
        import json
        
        self.print_status("Meter Keys", "checking", f"Checking keys for {len(meter_ids)} meters...")
        
        try:
            # Check which meters need keys
            keys_dir = self.project_dir / ".keys"
            keys_dir.mkdir(exist_ok=True)
            
            missing_keys = []
            existing_keys = []
            
            for meter_id in meter_ids:
                keyfile = keys_dir / f"keys_{meter_id}.json"
                if keyfile.exists():
                    existing_keys.append(meter_id)
                else:
                    missing_keys.append(meter_id)
            
            if existing_keys:
                self.print_status("Meter Keys", "running", f"Found keys for {len(existing_keys)} meters ✓")
                for meter_id in existing_keys:
                    keyfile = keys_dir / f"keys_{meter_id}.json"
                    with open(keyfile, 'r') as f:
                        key_data = json.load(f)
                        print(f"   {Colors.GREEN}{meter_id}: {key_data.get('address', 'N/A')}{Colors.END}")
            
            if missing_keys:
                self.print_status("Meter Keys", "starting", f"Creating keys for {len(missing_keys)} new meters...")
                
                # Import key generation
                from eth_account import Account
                
                registry_path = keys_dir / "registry.json"
                registry = {}
                if registry_path.exists():
                    with open(registry_path, 'r') as f:
                        registry = json.load(f)
                
                for meter_id in missing_keys:
                    # Generate new keypair
                    acct = Account.create()
                    priv = acct.key.hex()
                    if not priv.startswith("0x"):
                        priv = "0x" + priv
                    
                    key_data = {
                        "meter_id": meter_id,
                        "address": acct.address,
                        "private_key": priv
                    }
                    
                    # Save keyfile
                    keyfile = keys_dir / f"keys_{meter_id}.json"
                    with open(keyfile, 'w') as f:
                        json.dump(key_data, f, indent=2)
                    
                    # Update registry
                    registry[meter_id] = {
                        "address": acct.address,
                        "created_at": time.time(),
                        "active": True
                    }
                    
                    print(f"   {Colors.GREEN}{meter_id}: {acct.address}{Colors.END}")
                
                # Save registry
                with open(registry_path, 'w') as f:
                    json.dump(registry, f, indent=2)
                
                self.print_status("Meter Keys", "running", f"Created {len(missing_keys)} meter keys ✓")
            
            return True
            
        except Exception as e:
            self.print_status("Meter Keys", "error", str(e))
            import traceback
            traceback.print_exc()
            return False
    
    def start_all(self):
        """Start all services in correct dependency order"""
        self.print_header("SMART METER SYSTEM LAUNCHER (WINDOWS)")
        
        print(f"{Colors.BOLD}Project Directory:{Colors.END} {self.project_dir}")
        print(f"{Colors.BOLD}Log Directory:{Colors.END} {self.log_dir}\n")
        
        # 0. Check virtual environment
        if not self.check_venv():
            sys.exit(1)
        
        # 1. Check Ganache CLI availability
        if not self.check_ganache():
            print(f"\n{Colors.YELLOW}⚠️  Ganache not required but recommended for blockchain features{Colors.END}")
        
        # 2. Check MQTT Broker (Mosquitto)
        if not self.check_mosquitto():
            print(f"\n{Colors.RED}❌ MQTT Broker required! Start Mosquitto service from Windows Services or run: net start mosquitto{Colors.END}")
            sys.exit(1)
        
        # 3. Start Ganache (Blockchain) - Windows uses ganache.cmd or just ganache
        self.print_status("Ganache", "starting", "Starting local blockchain...")
        
        # Fixed mnemonic ensures same accounts every time
        MNEMONIC = "test test test test test test test test test test test junk"
        
        ganache_started = self.start_service(
            "Ganache",
            ["ganache", 
             "--port", "8545",
             "--chain.networkId", "1337",
             "--chain.chainId", "1337",
             "--miner.blockGasLimit", "0x1fffffffffffff",
             "--miner.defaultGasPrice", "20000000000",
             "--wallet.mnemonic", MNEMONIC,
             "--wallet.totalAccounts", "10",
             "--wallet.defaultBalance", "1000000"],
            shell=True  # Windows needs shell=True for npm packages
        )
        
        # ✅ AUTO-DEPLOY CONTRACTS
        if ganache_started:
            self.print_status("Ganache", "waiting", "Waiting for blockchain to be ready...")
            if self.check_port(8545, max_retries=15):
                self.print_status("Ganache", "running", "Blockchain ready on port 8545 ✓")
                
                print(f"\n{Colors.BOLD}📜 Deploying Smart Contracts...{Colors.END}\n")
                if self.deploy_contracts():
                    print(f"\n{Colors.GREEN}✅ Blockchain features enabled{Colors.END}")
                else:
                    print(f"\n{Colors.RED}❌ Contract deployment failed{Colors.END}")
                    print(f"{Colors.YELLOW}⚠️  Continuing without blockchain features{Colors.END}")
            else:
                self.print_status("Ganache", "error", "Blockchain not responding")
        else:
            print(f"\n{Colors.YELLOW}⚠️  Continuing without Ganache (blockchain features disabled){Colors.END}")
        
        # 4. Start IDS Service
        ids_started = self.start_service(
            "IDS",
            [str(self.venv_python), str(self.project_dir / "ids" / "ids_service.py")],
            env={"PYTHONUNBUFFERED": "1"}
        )
        
        if ids_started:
            self.print_status("IDS", "waiting", "Waiting for IDS to initialize...")
            if self.check_service("IDS", "http://127.0.0.1:5100/health", max_retries=15):
                self.print_status("IDS", "running", "Health check passed ✓")
            else:
                self.print_status("IDS", "error", "Health check failed")
                print(f"\n{Colors.RED}❌ IDS failed to start. Check logs\\IDS.log{Colors.END}")
                self.stop_all()
                sys.exit(1)
        else:
            print(f"\n{Colors.RED}❌ Failed to start IDS{Colors.END}")
            self.stop_all()
            sys.exit(1)
        
        # 5. Start Backend
        backend_started = self.start_service(
            "Backend",
            [str(self.venv_python), str(self.project_dir / "backend" / "app.py")],
            env={
                "PYTHONUNBUFFERED": "1",
                "IDS_URL": "http://127.0.0.1:5100/check",
                "BLOCKCHAIN_ENABLED": "true" if ganache_started else "false"
            }
        )
        
        if backend_started:
            self.print_status("Backend", "waiting", "Waiting for backend to initialize...")
            if self.check_service("Backend", "http://127.0.0.1:5000/health", max_retries=15):
                self.print_status("Backend", "running", "Health check passed ✓")
            else:
                self.print_status("Backend", "error", "Health check failed")
                print(f"\n{Colors.RED}❌ Backend failed to start. Check logs\\Backend.log{Colors.END}")
                self.stop_all()
                sys.exit(1)
        else:
            print(f"\n{Colors.RED}❌ Failed to start Backend{Colors.END}")
            self.stop_all()
            sys.exit(1)
        
        # 6. Start Forwarder (MQTT to Backend bridge)
        forwarder_started = self.start_service(
            "Forwarder",
            [str(self.venv_python), str(self.project_dir / "concentrator" / "forwarder.py")],
            env={"PYTHONUNBUFFERED": "1"}
        )
        
        if forwarder_started:
            time.sleep(2)
            self.print_status("Forwarder", "running", "MQTT bridge active ✓")
        else:
            print(f"\n{Colors.RED}❌ Failed to start Forwarder{Colors.END}")
            self.stop_all()
            sys.exit(1)
        
        # 7. Start Meter Simulators (optional, can be started manually)
        print(f"\n{Colors.BOLD}📊 Starting Meter Simulators...{Colors.END}\n")
        
        # ✅ ENSURE METER KEYS EXIST
        meter_ids = ["meter1", "meter2"]
        if not self.ensure_meter_keys(meter_ids):
            print(f"\n{Colors.YELLOW}⚠️  Failed to ensure meter keys. Skipping meter simulators.{Colors.END}")
            print(f"   You can create keys manually: python meters\\key_manager.py init --meters meter1,meter2")
        else:
            print()  # Add spacing
            
            # Start meter1 (residential)
            meter1_started = self.start_service(
                "Meter1",
                [str(self.venv_python), str(self.project_dir / "meters" / "meter_sim.py"),
                 "--meter-id", "meter1",
                 "--meter-type", "residential",
                 "--interval", "10.0"],
                env={"PYTHONUNBUFFERED": "1"}
            )
            if meter1_started:
                time.sleep(1)
                self.print_status("Meter1", "running", "Residential meter active ✓")
            
            # Start meter2 (commercial) 
            meter2_started = self.start_service(
                "Meter2",
                [str(self.venv_python), str(self.project_dir / "meters" / "meter_sim.py"),
                 "--meter-id", "meter2", 
                 "--meter-type", "commercial",
                 "--interval", "20.0"],
                env={"PYTHONUNBUFFERED": "1"}
            )
            if meter2_started:
                time.sleep(1)
                self.print_status("Meter2", "running", "Commercial meter active ✓")
        
        # 8. Start Dashboard (dev server) - npm works on Windows
        dashboard_started = self.start_service(
            "Dashboard",
            ["npm", "run", "dev"],
            cwd=self.project_dir / "dashboard",
            shell=True  # Windows needs shell=True for npm commands
        )
        
        if dashboard_started:
            self.print_status("Dashboard", "waiting", "Waiting for Vite dev server...")
            time.sleep(5)
            if self.check_service("Dashboard", "http://localhost:5173", max_retries=20):
                self.print_status("Dashboard", "running", "Dev server ready ✓")
            else:
                self.print_status("Dashboard", "error", "Dev server not responding")
        
        self.print_summary()
    
    def print_summary(self):
        """Print service URLs and controls (Windows version)"""
        print(f"\n{Colors.GREEN}{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"{Colors.GREEN}{Colors.BOLD}{'ALL SERVICES STARTED':^60}{Colors.END}")
        print(f"{Colors.GREEN}{Colors.BOLD}{'='*60}{Colors.END}\n")
        
        print(f"{Colors.BOLD}📡 Service URLs:{Colors.END}")
        print(f"   Ganache:    http://127.0.0.1:8545")
        print(f"   IDS:        http://127.0.0.1:5100")
        print(f"   Backend:    http://127.0.0.1:5000")
        print(f"   Dashboard:  http://localhost:5173")
        print(f"   MQTT:       mqtt://localhost:1883 (topic: grid/readings)")
        
        print(f"\n{Colors.BOLD}📋 View Logs (PowerShell):{Colors.END}")
        print(f"   Get-Content logs\\Ganache.log -Wait")
        print(f"   Get-Content logs\\IDS.log -Wait")
        print(f"   Get-Content logs\\Backend.log -Wait")
        print(f"   Get-Content logs\\Forwarder.log -Wait")
        print(f"   Get-Content logs\\Meter1.log -Wait")
        print(f"   Get-Content logs\\Meter2.log -Wait")
        print(f"   Get-Content logs\\Dashboard.log -Wait")
        
        print(f"\n{Colors.BOLD}📋 View Logs (CMD):{Colors.END}")
        print(f"   type logs\\Ganache.log")
        print(f"   type logs\\IDS.log")
        
        print(f"\n{Colors.BOLD}🔧 Manual Commands:{Colors.END}")
        print(f"   Start meter manually:")
        print(f"   {Colors.YELLOW}venv\\Scripts\\activate{Colors.END}")
        print(f"   {Colors.YELLOW}python meters\\meter_sim.py --meter-id meter3 --meter-type industrial{Colors.END}")
        
        print(f"\n{Colors.BOLD}⚙️  Controls:{Colors.END}")
        print(f"   Press {Colors.YELLOW}Ctrl+C{Colors.END} to stop all services")
        print(f"   Or run: {Colors.YELLOW}python run_windows.py --stop{Colors.END}")
        print(f"   View all logs: {Colors.YELLOW}python run_windows.py --logs{Colors.END}")
        print()
    
    def stop_all(self):
        """Stop all services (Windows version)"""
        self.print_header("STOPPING ALL SERVICES")
        
        # Stop in reverse order
        stop_order = ["Dashboard", "Meter2", "Meter1", "Forwarder", "Backend", "IDS", "Ganache"]
        
        for name in stop_order:
            if name in self.processes:
                try:
                    process = self.processes[name]["process"]
                    if process.poll() is None:
                        self.print_status(name, "stopped", f"PID: {process.pid}")
                        
                        # Windows-specific: Use taskkill for graceful shutdown
                        try:
                            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                         capture_output=True, timeout=5)
                        except:
                            process.terminate()
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                self.print_status(name, "error", "Force killing...")
                                process.kill()
                except Exception as e:
                    self.print_status(name, "error", str(e))
        
        print(f"\n{Colors.GREEN}✅ All services stopped{Colors.END}\n")
    
    def tail_logs(self):
        """Show combined logs from all services (Windows version)"""
        print(f"\n{Colors.BOLD}Available logs:{Colors.END}\n")
        
        log_files = [
            "Ganache.log", "IDS.log", "Backend.log", "Forwarder.log",
            "Meter1.log", "Meter2.log", "Dashboard.log"
        ]
        
        existing_logs = []
        for idx, log_name in enumerate(log_files, 1):
            log_path = self.log_dir / log_name
            if log_path.exists():
                print(f"   [{idx}] {log_name}")
                existing_logs.append(log_name)
        
        if not existing_logs:
            print(f"{Colors.RED}No log files found{Colors.END}")
            return
        
        print(f"\n{Colors.BOLD}To view a log file (PowerShell):{Colors.END}")
        print(f"   {Colors.YELLOW}Get-Content logs\\<logfile> -Wait{Colors.END}")
        
        print(f"\n{Colors.BOLD}To view a log file (CMD):{Colors.END}")
        print(f"   {Colors.YELLOW}type logs\\<logfile>{Colors.END}")
        
        print(f"\n{Colors.BOLD}Opening all logs in Notepad...{Colors.END}")
        for log_name in existing_logs:
            try:
                subprocess.Popen(['notepad', str(self.log_dir / log_name)])
            except:
                pass

def main():
    manager = ServiceManager()
    
    def signal_handler(sig, frame):
        print(f"\n\n{Colors.YELLOW}Shutting down...{Colors.END}")
        manager.stop_all()
        sys.exit(0)
    
    # Windows signal handling
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGBREAK'):  # Windows-specific
        signal.signal(signal.SIGBREAK, signal_handler)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--stop":
        manager.stop_all()
        return
    
    if len(sys.argv) > 1 and sys.argv[1] == "--logs":
        manager.tail_logs()
        return
    
    try:
        manager.start_all()
        
        # Keep running and monitor processes
        print(f"\n{Colors.BOLD}Monitoring services... Press Ctrl+C to stop{Colors.END}\n")
        while True:
            time.sleep(5)
            dead_services = []
            for name, info in manager.processes.items():
                if info["process"].poll() is not None:
                    manager.print_status(name, "error", "Process died unexpectedly!")
                    dead_services.append(name)
            
            if dead_services:
                print(f"\n{Colors.RED}Critical services died: {', '.join(dead_services)}{Colors.END}")
                print(f"Check logs for details: {Colors.YELLOW}python run_windows.py --logs{Colors.END}\n")
                manager.stop_all()
                sys.exit(1)
                    
    except KeyboardInterrupt:
        manager.stop_all()

if __name__ == "__main__":
    main()
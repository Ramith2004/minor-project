#!/usr/bin/env python3
"""
Smart Meter System Launcher
Starts all services with organized logging and proper dependency order
"""

import subprocess
import time
import os
import signal
import sys
from pathlib import Path
from typing import List

# ANSI colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

class ServiceManager:
    def __init__(self):
        self.processes = {}
        self.project_dir = Path(__file__).parent
        self.log_dir = self.project_dir / "logs"
        self.log_dir.mkdir(exist_ok=True)
        self.venv_python = self.project_dir / "venv" / "bin" / "python3"
        
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
            self.print_status("Virtual Env", "error", "venv not found! Run: python3 -m venv venv")
            return False
        
        self.print_status("Virtual Env", "running", "Found ✓")
        return True
    
    def check_ganache(self):
        """Check if Ganache CLI is installed"""
        try:
            result = subprocess.run(["ganache-cli", "--version"], 
                                   capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.print_status("Ganache Check", "running", "Installed ✓")
                return True
            else:
                self.print_status("Ganache Check", "error", "Not found! Run: npm install -g ganache-cli")
                return False
        except:
            self.print_status("Ganache Check", "error", "Not found! Run: npm install -g ganache-cli")
            return False
    
    def check_mosquitto(self):
        """Check if Mosquitto MQTT broker is running"""
        try:
            result = subprocess.run(["pgrep", "-x", "mosquitto"], 
                                   capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                self.print_status("MQTT Broker", "running", "Mosquitto running ✓")
                return True
            else:
                self.print_status("MQTT Broker", "error", "Mosquitto not running! Start: sudo systemctl start mosquitto")
                return False
        except:
            self.print_status("MQTT Broker", "error", "Could not check Mosquitto status")
            return False
    
    def start_service(self, name, command, cwd=None, env=None, shell=False):
        """Start a service with logging"""
        log_file = self.log_dir / f"{name}.log"
        
        try:
            self.print_status(name, "starting", f"(log: logs/{name}.log)")
            
            with open(log_file, 'w') as log:
                log.write(f"=== {name} started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
            
            process_env = os.environ.copy()
            if env:
                process_env.update(env)
            
            with open(log_file, 'a') as log:
                process = subprocess.Popen(
                    command,
                    cwd=cwd or self.project_dir,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=process_env,
                    bufsize=1,
                    universal_newlines=True,
                    shell=shell
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
                timeout=60
            )
            
            if result.returncode == 0:
                self.print_status("Contracts", "running", "Deployment successful ✓")
                
                # Parse contract addresses from output
                output = result.stdout
                if "MeterRegistry:" in output:
                    for line in output.split('\n'):
                        if "MeterRegistry:" in line:
                            addr = line.split(':')[1].strip()
                            print(f"   {Colors.GREEN}MeterRegistry: {addr}{Colors.END}")
                        elif "Consensus:" in line:
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
        self.print_header("SMART METER SYSTEM LAUNCHER")
        
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
            print(f"\n{Colors.RED}❌ MQTT Broker required! Start with: sudo systemctl start mosquitto{Colors.END}")
            sys.exit(1)
        
        # 3. Start Ganache (Blockchain)
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
            shell=False
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
            [str(self.venv_python), "ids/ids_service.py"],
            env={"PYTHONUNBUFFERED": "1"}
        )
        
        if ids_started:
            self.print_status("IDS", "waiting", "Waiting for IDS to initialize...")
            if self.check_service("IDS", "http://127.0.0.1:5100/health", max_retries=15):
                self.print_status("IDS", "running", "Health check passed ✓")
            else:
                self.print_status("IDS", "error", "Health check failed")
                print(f"\n{Colors.RED}❌ IDS failed to start. Check logs/IDS.log{Colors.END}")
                self.stop_all()
                sys.exit(1)
        else:
            print(f"\n{Colors.RED}❌ Failed to start IDS{Colors.END}")
            self.stop_all()
            sys.exit(1)
        
        # 5. Start Backend
        backend_started = self.start_service(
            "Backend",
            [str(self.venv_python), "backend/app.py"],
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
                print(f"\n{Colors.RED}❌ Backend failed to start. Check logs/Backend.log{Colors.END}")
                self.stop_all()
                sys.exit(1)
        else:
            print(f"\n{Colors.RED}❌ Failed to start Backend{Colors.END}")
            self.stop_all()
            sys.exit(1)
        
        # 6. Start Forwarder (MQTT to Backend bridge)
        forwarder_started = self.start_service(
            "Forwarder",
            [str(self.venv_python), "concentrator/forwarder.py"],
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
            print(f"   You can create keys manually: python3 meters/key_manager.py init --meters meter1,meter2")
        else:
            print()  # Add spacing
            
            # Start meter1 (residential)
            meter1_started = self.start_service(
                "Meter1",
                [str(self.venv_python), "meters/meter_sim.py", 
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
                [str(self.venv_python), "meters/meter_sim.py",
                 "--meter-id", "meter2", 
                 "--meter-type", "commercial",
                 "--interval", "20.0"],
                env={"PYTHONUNBUFFERED": "1"}
            )
            if meter2_started:
                time.sleep(1)
                self.print_status("Meter2", "running", "Commercial meter active ✓")
        
        # 8. Start Dashboard (dev server)
        dashboard_started = self.start_service(
            "Dashboard",
            ["npm", "run", "dev"],
            cwd=self.project_dir / "dashboard"
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
        """Print service URLs and controls"""
        print(f"\n{Colors.GREEN}{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"{Colors.GREEN}{Colors.BOLD}{'ALL SERVICES STARTED':^60}{Colors.END}")
        print(f"{Colors.GREEN}{Colors.BOLD}{'='*60}{Colors.END}\n")
        
        print(f"{Colors.BOLD}📡 Service URLs:{Colors.END}")
        print(f"   Ganache:    http://127.0.0.1:8545")
        print(f"   IDS:        http://127.0.0.1:5100")
        print(f"   Backend:    http://127.0.0.1:5000")
        print(f"   Dashboard:  http://localhost:5173")
        print(f"   MQTT:       mqtt://localhost:1883 (topic: grid/readings)")
        
        print(f"\n{Colors.BOLD}📋 View Logs:{Colors.END}")
        print(f"   tail -f logs/Ganache.log")
        print(f"   tail -f logs/IDS.log")
        print(f"   tail -f logs/Backend.log")
        print(f"   tail -f logs/Forwarder.log")
        print(f"   tail -f logs/Meter1.log")
        print(f"   tail -f logs/Meter2.log")
        print(f"   tail -f logs/Dashboard.log")
        
        print(f"\n{Colors.BOLD}🔧 Manual Commands:{Colors.END}")
        print(f"   Start meter manually:")
        print(f"   {Colors.YELLOW}source venv/bin/activate{Colors.END}")
        print(f"   {Colors.YELLOW}python3 meters/meter_sim.py --meter-id meter3 --meter-type industrial{Colors.END}")
        
        print(f"\n{Colors.BOLD}⚙️  Controls:{Colors.END}")
        print(f"   Press {Colors.YELLOW}Ctrl+C{Colors.END} to stop all services")
        print(f"   Or run: {Colors.YELLOW}python3 run.py --stop{Colors.END}")
        print(f"   View all logs: {Colors.YELLOW}python3 run.py --logs{Colors.END}")
        print()
    
    def stop_all(self):
        """Stop all services"""
        self.print_header("STOPPING ALL SERVICES")
        
        # Stop in reverse order
        stop_order = ["Dashboard", "Meter2", "Meter1", "Forwarder", "Backend", "IDS", "Ganache"]
        
        for name in stop_order:
            if name in self.processes:
                try:
                    process = self.processes[name]["process"]
                    if process.poll() is None:
                        self.print_status(name, "stopped", f"PID: {process.pid}")
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
        """Show combined logs from all services"""
        try:
            log_files = [
                str(self.log_dir / "Ganache.log"),
                str(self.log_dir / "IDS.log"),
                str(self.log_dir / "Backend.log"),
                str(self.log_dir / "Forwarder.log"),
                str(self.log_dir / "Meter1.log"),
                str(self.log_dir / "Meter2.log"),
                str(self.log_dir / "Dashboard.log")
            ]
            
            # Only include existing logs
            existing_logs = [f for f in log_files if Path(f).exists()]
            
            if existing_logs:
                subprocess.run(["tail", "-f"] + existing_logs)
            else:
                print(f"{Colors.RED}No log files found{Colors.END}")
        except KeyboardInterrupt:
            pass

def main():
    manager = ServiceManager()
    
    def signal_handler(sig, frame):
        print(f"\n\n{Colors.YELLOW}Shutting down...{Colors.END}")
        manager.stop_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
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
                print(f"Check logs for details: {Colors.YELLOW}python3 run.py --logs{Colors.END}\n")
                manager.stop_all()
                sys.exit(1)
                    
    except KeyboardInterrupt:
        manager.stop_all()

if __name__ == "__main__":
    main()
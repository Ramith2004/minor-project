#!/usr/bin/env python3
"""
Deploy smart contracts to Ganache (Deterministic)
"""
from web3 import Web3
import json
import os
import sys

# Get project root
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)

# Load environment variables from .env
def load_env():
    """Load .env file"""
    env_file = os.path.join(project_root, '.env')
    env_vars = {}
    
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and 'export' in line:
                    # Parse: export KEY=value
                    line = line.replace('export ', '')
                    if '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
    
    return env_vars

env_vars = load_env()

print("="*70)
print("SMART CONTRACT DEPLOYMENT TO GANACHE (DETERMINISTIC)")
print("="*70)

# Connect to Ganache
RPC_URL = env_vars.get('RPC_URL', 'http://127.0.0.1:8545')
PRIVATE_KEY = env_vars.get('PRIVATE_KEY', '0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d')

# Remove quotes if present
PRIVATE_KEY = PRIVATE_KEY.strip('"').strip("'")
RPC_URL = RPC_URL.strip('"').strip("'")

w3 = Web3(Web3.HTTPProvider(RPC_URL))

print(f"\n✅ Checking Ganache connection...")
if not w3.is_connected():
    print("❌ Error: Cannot connect to Ganache!")
    print("   Make sure Ganache is running on port 8545")
    sys.exit(1)

print(f"✅ Connected to Ganache")
print(f"   Chain ID: {w3.eth.chain_id}")
print(f"   Latest Block: {w3.eth.block_number}")

# Account details
account = w3.eth.account.from_key(PRIVATE_KEY)
print(f"\n✅ Deploying from account: {account.address}")
print(f"   Balance: {w3.from_wei(w3.eth.get_balance(account.address), 'ether')} ETH")


def load_contract_data(contract_name):
    """Load compiled contract bytecode and ABI"""
    
    artifacts_file = os.path.join(project_root, "artifacts", "contracts", f"{contract_name}.sol", f"{contract_name}.json")
    
    try:
        with open(artifacts_file, 'r') as f:
            artifact = json.load(f)
        
        abi = artifact['abi']
        bytecode = artifact['bytecode']
        
        if not bytecode.startswith('0x'):
            bytecode = '0x' + bytecode
        
        print(f"✅ Loaded {contract_name}")
        return abi, bytecode
        
    except FileNotFoundError as e:
        print(f"❌ Error loading {contract_name}: {e}")
        print(f"   Expected file: {artifacts_file}")
        print(f"   Make sure you've run: npx hardhat compile")
        sys.exit(1)
    except KeyError as e:
        print(f"❌ Error parsing {contract_name} artifact: {e}")
        sys.exit(1)


def deploy_contract(name, abi, bytecode, constructor_args=None):
    """Deploy a contract to Ganache"""
    print(f"\n{'='*70}")
    print(f"DEPLOYING {name}")
    print(f"{'='*70}")
    
    try:
        # Create contract instance
        Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
        
        # Build constructor transaction
        if constructor_args:
            constructor = Contract.constructor(*constructor_args)
        else:
            constructor = Contract.constructor()
        
        # Estimate gas
        gas_estimate = constructor.estimate_gas({'from': account.address})
        print(f"📊 Estimated gas: {gas_estimate:,}")
        
        # Build transaction
        tx = constructor.build_transaction({
            'from': account.address,
            'gas': gas_estimate + 100000,  # Add buffer
            'gasPrice': w3.eth.gas_price,
            'nonce': w3.eth.get_transaction_count(account.address)
        })
        
        print(f"📝 Signing transaction...")
        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        
        print(f"📤 Sending transaction...")
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print(f"   Transaction hash: {tx_hash.hex()}")
        
        print(f"⏳ Waiting for confirmation...")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        if receipt.status == 1:
            print(f"✅ {name} deployed successfully!")
            print(f"   Contract address: {receipt.contractAddress}")
            print(f"   Block number: {receipt.blockNumber}")
            print(f"   Gas used: {receipt.gasUsed:,}")
            
            # Calculate cost
            cost_wei = receipt.gasUsed * w3.eth.gas_price
            cost_eth = w3.from_wei(cost_wei, 'ether')
            print(f"   Cost: {cost_eth} ETH")
            
            return receipt.contractAddress
        else:
            print(f"❌ {name} deployment failed!")
            return None
            
    except Exception as e:
        print(f"❌ Deployment error: {e}")
        import traceback
        traceback.print_exc()
        return None


def update_env_file(addresses):
    """Update .env file with contract addresses"""
    env_file = os.path.join(project_root, '.env')
    
    # Read existing content
    lines = []
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            lines = f.readlines()
    
    # Update contract addresses
    updated_lines = []
    keys_to_update = {
        'METER_STORE_ADDRESS': addresses['MeterStore'],
        'METER_REGISTRY_ADDRESS': addresses['MeterRegistry'],
        'CONSENSUS_ADDRESS': addresses['Consensus']
    }
    
    # Track which keys we've updated
    updated_keys = set()
    
    for line in lines:
        updated = False
        for key, value in keys_to_update.items():
            if f'export {key}=' in line or f'{key}=' in line:
                updated_lines.append(f'export {key}={value}\n')
                updated_keys.add(key)
                updated = True
                break
        
        if not updated:
            updated_lines.append(line)
    
    # Add any missing keys
    for key, value in keys_to_update.items():
        if key not in updated_keys:
            updated_lines.append(f'export {key}={value}\n')
    
    # Write back
    with open(env_file, 'w') as f:
        f.writelines(updated_lines)
    
    print(f"✅ Updated .env file with contract addresses")


def save_contracts_info(addresses, abis):
    """Save contract information to JSON file"""
    contracts_info = {
        "network": "ganache",
        "chainId": w3.eth.chain_id,
        "deployer": account.address,
        "deploymentTime": w3.eth.get_block('latest')['timestamp'],
        "contracts": {
            "MeterRegistry": {
                "address": addresses['MeterRegistry'],
                "abi": abis['MeterRegistry']
            },
            "Consensus": {
                "address": addresses['Consensus'],
                "abi": abis['Consensus']
            },
            "MeterStore": {
                "address": addresses['MeterStore'],
                "abi": abis['MeterStore']
            }
        }
    }
    
    info_file = os.path.join(project_root, "contracts_info.json")
    with open(info_file, 'w') as f:
        json.dump(contracts_info, f, indent=2)
    
    print(f"✅ Created contracts_info.json")


def main():
    print(f"\n{'='*70}")
    print("STEP 1: LOADING CONTRACTS")
    print(f"{'='*70}")
    
    # Record initial balance for cost calculation
    initial_balance = w3.eth.get_balance(account.address)
    print(f"\n💰 Initial balance: {w3.from_wei(initial_balance, 'ether')} ETH")
    
    # Load contract data
    meter_registry_abi, meter_registry_bytecode = load_contract_data("MeterRegistry")
    consensus_abi, consensus_bytecode = load_contract_data("Consensus")
    meter_store_abi, meter_store_bytecode = load_contract_data("MeterStore")
    
    print(f"\n{'='*70}")
    print("STEP 2: DEPLOYING CONTRACTS")
    print(f"{'='*70}")
    
    # Deploy MeterRegistry first (no dependencies)
    print("\n🚀 Deploying MeterRegistry...")
    meter_registry_address = deploy_contract(
        "MeterRegistry",
        meter_registry_abi,
        meter_registry_bytecode
    )
    
    if not meter_registry_address:
        print("\n❌ Failed to deploy MeterRegistry. Aborting.")
        sys.exit(1)
    
    # Deploy Consensus (no dependencies)
    print("\n🚀 Deploying Consensus...")
    consensus_address = deploy_contract(
        "Consensus",
        consensus_abi,
        consensus_bytecode
    )
    
    if not consensus_address:
        print("\n❌ Failed to deploy Consensus. Aborting.")
        sys.exit(1)
    
    # Deploy MeterStore (depends on MeterRegistry and Consensus)
    print("\n🚀 Deploying MeterStore...")
    # MeterStore constructor requires 3 addresses:
    # constructor(address _meterRegistry, address _consensus, address _idsService)
    ids_service_address = account.address  # Use deployer account as IDS service for now
    
    meter_store_address = deploy_contract(
        "MeterStore",
        meter_store_abi,
        meter_store_bytecode,
        constructor_args=[
            meter_registry_address,
            consensus_address,
            ids_service_address
        ]
    )
    
    if not meter_store_address:
        print("\n❌ Failed to deploy MeterStore. Aborting.")
        sys.exit(1)
    
    # Calculate total cost
    final_balance = w3.eth.get_balance(account.address)
    total_cost_wei = initial_balance - final_balance
    total_cost = w3.from_wei(total_cost_wei, 'ether')
    
    # Prepare data for saving
    addresses = {
        'MeterRegistry': meter_registry_address,
        'Consensus': consensus_address,
        'MeterStore': meter_store_address
    }
    
    abis = {
        'MeterRegistry': meter_registry_abi,
        'Consensus': consensus_abi,
        'MeterStore': meter_store_abi
    }
    
    print(f"\n{'='*70}")
    print("STEP 3: SAVING DEPLOYMENT INFO")
    print(f"{'='*70}")
    
    # Update .env file
    update_env_file(addresses)
    
    # Save contracts info
    save_contracts_info(addresses, abis)
    
    # Print summary
    print(f"\n{'='*70}")
    print("✅ DEPLOYMENT COMPLETE!")
    print(f"{'='*70}")
    
    print("\n📝 Contract Addresses:")
    print(f"   MeterRegistry:  {meter_registry_address}")
    print(f"   Consensus:      {consensus_address}")
    print(f"   MeterStore:     {meter_store_address}")
    
    print(f"\n💰 Deployment Cost:")
    print(f"   Total cost: {total_cost} ETH")
    print(f"   Remaining balance: {w3.from_wei(final_balance, 'ether')} ETH")
    
    print(f"\n✅ Contracts deployed and .env updated!")
    print(f"   Blockchain features are now enabled")
    
    print(f"\n{'='*70}")
    print("🎉 ALL DONE!")
    print(f"{'='*70}")
    print("\n📌 Next Steps:")
    print("   1. Contracts are ready to use")
    print("   2. Backend will load addresses from .env automatically")
    print("   3. Test with: curl -X POST http://localhost:5000/submitReading ...")


if __name__ == "__main__":
    main()
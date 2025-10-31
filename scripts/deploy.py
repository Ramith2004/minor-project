#!/usr/bin/env python3
"""
Deploy smart contracts to Ganache
"""
from web3 import Web3
import json
import os
import sys

print("="*70)
print("SMART CONTRACT DEPLOYMENT TO GANACHE")
print("="*70)

# Connect to Ganache
RPC_URL = "http://127.0.0.1:8545"
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
PRIVATE_KEY = "0xcce3f069de3707f0d7376fb023ff2b181d66191d6d49b6ee0636750b6088d40f"  # Account (0)
account = w3.eth.account.from_key(PRIVATE_KEY)
print(f"\n✅ Deploying from account: {account.address}")
print(f"   Balance: {w3.from_wei(w3.eth.get_balance(account.address), 'ether')} ETH")

def load_contract_data(contract_name):
    """Load compiled contract bytecode and ABI"""
    
    # Get the absolute path to the project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
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

# Main deployment process
def main():
    print(f"\n{'='*70}")
    print("STEP 1: LOADING CONTRACTS")
    print(f"{'='*70}")
    
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
    
    # Print summary
    print(f"\n{'='*70}")
    print("✅ DEPLOYMENT COMPLETE!")
    print(f"{'='*70}")
    
    print("\n📝 Contract Addresses:")
    print(f"   MeterRegistry:  {meter_registry_address}")
    print(f"   Consensus:      {consensus_address}")
    print(f"   MeterStore:     {meter_store_address}")
    
    # Calculate total cost
    final_balance = w3.eth.get_balance(account.address)
    initial_balance = w3.to_wei(1000, 'ether')  # Started with 100 ETH
    total_cost = w3.from_wei(initial_balance - final_balance, 'ether')
    print(f"\n💰 Total deployment cost: {total_cost} ETH")
    print(f"   Remaining balance: {w3.from_wei(final_balance, 'ether')} ETH")
    
    # Save to .env file
    print(f"\n{'='*70}")
    print("STEP 3: UPDATING .env FILE")
    print(f"{'='*70}")
    
    env_content = f"""# Smart Contract Addresses (Generated by deploy_contracts.py)
export METER_STORE_ADDRESS={meter_store_address}
export METER_REGISTRY_ADDRESS={meter_registry_address}
export CONSENSUS_ADDRESS={consensus_address}

# Ganache Configuration
export RPC_URL=http://127.0.0.1:8545
export PRIVATE_KEY={PRIVATE_KEY}

# Other Settings
export BLOCKCHAIN_ENABLED=true
export RATE_LIMIT_ENABLED=true
export FORENSICS_ENABLED=true
export IDS_URL=http://127.0.0.1:5100/check
"""
    
    env_file_path = "../.env"
    with open(env_file_path, 'w') as f:
        f.write(env_content)
    
    print(f"✅ Updated {env_file_path}")
    
    # Also create a contracts_info.json for easy reference
    contracts_info = {
        "network": "ganache",
        "chainId": w3.eth.chain_id,
        "deployer": account.address,
        "deploymentTime": w3.eth.get_block('latest')['timestamp'],
        "contracts": {
            "MeterRegistry": {
                "address": meter_registry_address,
                "abi": meter_registry_abi
            },
            "Consensus": {
                "address": consensus_address,
                "abi": consensus_abi
            },
            "MeterStore": {
                "address": meter_store_address,
                "abi": meter_store_abi
            }
        }
    }
    
    with open("contracts_info.json", 'w') as f:
        json.dump(contracts_info, f, indent=2)
    
    print(f"✅ Created contracts_info.json")
    
    print(f"\n{'='*70}")
    print("🎉 ALL DONE!")
    print(f"{'='*70}")
    print("\nNext steps:")
    print("1. Source the .env file: source ../.env")
    print("2. Start your backend: python3 app.py")
    print("3. Test with: curl -X POST http://localhost:5000/submitReading ...")
    
if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Blockchain Integration Module
Handles interaction with smart contracts for meter reading storage and verification
"""
import json
import time
import logging
from typing import Optional, Dict, Any, List
from web3 import Web3
from eth_account import Account
import requests

class BlockchainIntegration:
    def __init__(self, rpc_url: str, private_key: str, meter_store_address: str, 
                 meter_registry_address: str, consensus_address: str):
        self.rpc_url = rpc_url
        self.private_key = private_key
        self.meter_store_address = meter_store_address
        self.meter_registry_address = meter_registry_address
        self.consensus_address = consensus_address
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise Exception("Failed to connect to blockchain network")
        
        # Initialize account
        self.account = self.w3.eth.account.from_key(private_key)
        
        # Load contract ABIs
        self.meter_store_abi = self._load_abi("MeterStore")
        self.meter_registry_abi = self._load_abi("MeterRegistry")
        self.consensus_abi = self._load_abi("Consensus")
        
        # Initialize contracts
        self.meter_store = self.w3.eth.contract(
            address=meter_store_address,
            abi=self.meter_store_abi
        )
        
        self.meter_registry = self.w3.eth.contract(
            address=meter_registry_address,
            abi=self.meter_registry_abi
        )
        
        self.consensus = self.w3.eth.contract(
            address=consensus_address,
            abi=self.consensus_abi
        )
        
        # Transaction tracking
        self.pending_transactions = {}
        self.failed_transactions = []
        
        logging.info(f"Blockchain integration initialized for account {self.account.address}")
    
    def _load_abi(self, contract_name: str) -> List[Dict]:
        """Load contract ABI from file"""
        try:
            # Correct path to compiled artifacts
            import os
            from pathlib import Path
            artifacts_path = Path(__file__).parent.parent / "artifacts" / "contracts" / f"{contract_name}.sol" / f"{contract_name}.json"
            
            if not artifacts_path.exists():
                logging.warning(f"ABI file not found at {artifacts_path}, using fallback")
                return self._get_fallback_abi(contract_name)
            
            with open(artifacts_path, 'r') as f:
                artifact = json.load(f)
                return artifact.get('abi', [])
        except Exception as e:
            logging.error(f"Failed to load ABI for {contract_name}: {e}")
            return self._get_fallback_abi(contract_name)
    
    def _get_fallback_abi(self, contract_name: str) -> List[Dict]:
        """Fallback ABI for testing"""
        if contract_name == "MeterStore":
            return [
                {
                    "inputs": [
                        {"name": "meterId", "type": "address"},
                        {"name": "sequence", "type": "uint256"},
                        {"name": "timestamp", "type": "uint256"},
                        {"name": "value", "type": "uint256"},
                        {"name": "signature", "type": "bytes32"},
                        {"name": "suspiciousScore", "type": "uint256"},
                        {"name": "reasons", "type": "string[]"}
                    ],
                    "name": "storeReading",
                    "outputs": [{"name": "", "type": "bool"}],
                    "stateMutability": "nonpayable",
                    "type": "function"
                }
            ]
        return []
    
    def is_healthy(self) -> bool:
        """Check if blockchain connection is healthy"""
        try:
            latest_block = self.w3.eth.get_block('latest')
            return latest_block is not None
        except Exception as e:
            logging.error(f"Blockchain health check failed: {e}")
            return False
    
    def get_gas_price(self) -> int:
        """Get current gas price"""
        try:
            return self.w3.eth.gas_price
        except Exception:
            return 20000000000  # 20 gwei fallback
    
    def get_nonce(self) -> int:
        """Get current nonce for account"""
        try:
            return self.w3.eth.get_transaction_count(self.account.address)
        except Exception as e:
            logging.error(f"Failed to get nonce: {e}")
            return 0
    
    def store_reading_on_chain(self, meter_id: str, sequence: int, timestamp: int, 
                              value: int, signature: str, suspicious_score: int, 
                              reasons: List[str]) -> Optional[str]:
        """Store meter reading on blockchain"""
        try:
            # Convert meter_id to address if it's a string
            if isinstance(meter_id, str):
                meter_address = self.w3.to_checksum_address(meter_id)
            else:
                meter_address = meter_id
            
            # Convert signature to bytes32 (32 bytes exactly)
            if signature.startswith('0x'):
                signature = signature[2:]
            
            # Convert hex string to bytes
            sig_bytes = bytes.fromhex(signature)
            
            # Ensure exactly 32 bytes for bytes32 type
            if len(sig_bytes) > 32:
                # Take first 32 bytes (truncate)
                sig_bytes = sig_bytes[:32]
            elif len(sig_bytes) < 32:
                # Pad with zeros to reach 32 bytes
                sig_bytes = sig_bytes + b'\x00' * (32 - len(sig_bytes))
            
            # Convert to hex string with 0x prefix for Web3
            signature_bytes32 = '0x' + sig_bytes.hex()
            
            # Build transaction
            tx = self.meter_store.functions.storeReading(
                meter_address,
                sequence,
                timestamp,
                value,
                signature_bytes32,  # Now properly formatted as bytes32
                suspicious_score,
                reasons
            ).build_transaction({
                'from': self.account.address,
                'gas': 500000,
                'gasPrice': self.get_gas_price(),
                'nonce': self.get_nonce(),
                'chainId': self.w3.eth.chain_id
            })
            
            # Sign and send transaction
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            tx_hash_hex = tx_hash.hex()
            
            # Track transaction
            self.pending_transactions[tx_hash_hex] = {
                'timestamp': time.time(),
                'meter_id': meter_id,
                'sequence': sequence,
                'type': 'store_reading'
            }
            
            logging.info(f"Transaction submitted: {tx_hash_hex}")
            return tx_hash_hex
            
        except Exception as e:
            logging.error(f"Failed to store reading on chain: {e}")
            self.failed_transactions.append({
                'timestamp': time.time(),
                'meter_id': meter_id,
                'sequence': sequence,
                'error': str(e)
            })
            return None
    
    def verify_reading(self, meter_id: str, sequence: int, verified: bool = True) -> Optional[str]:
        """Verify a reading on blockchain"""
        try:
            if isinstance(meter_id, str):
                meter_address = self.w3.to_checksum_address(meter_id)
            else:
                meter_address = meter_id
            
            tx = self.meter_store.functions.verifyReading(
                meter_address,
                sequence,
                verified
            ).build_transaction({
                'from': self.account.address,
                'gas': 200000,
                'gasPrice': self.get_gas_price(),
                'nonce': self.get_nonce()
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            tx_hash_hex = tx_hash.hex()
            
            # Track transaction
            self.pending_transactions[tx_hash_hex] = {
                'timestamp': time.time(),
                'meter_id': meter_id,
                'sequence': sequence,
                'type': 'verify_reading'
            }
            
            logging.info(f"Verification transaction submitted: {tx_hash_hex}")
            return tx_hash_hex
            
        except Exception as e:
            logging.error(f"Failed to verify reading: {e}")
            return None
    
    def get_reading_from_chain(self, meter_id: str, sequence: int) -> Optional[Dict[str, Any]]:
        """Get reading details from blockchain"""
        try:
            if isinstance(meter_id, str):
                meter_address = self.w3.to_checksum_address(meter_id)
            else:
                meter_address = meter_id
            
            result = self.meter_store.functions.getReading(meter_address, sequence).call()
            
            return {
                'timestamp': result[0],
                'value': result[1],
                'signature': result[2].hex(),
                'suspicious_score': result[3],
                'verified': result[4],
                'consensus_reached': result[5],
                'validator': result[6],
                'block_number': result[7],
                'verification_count': result[8]
            }
            
        except Exception as e:
            logging.error(f"Failed to get reading from chain: {e}")
            return None
    
    def check_consensus(self, meter_id: str, sequence: int) -> bool:
        """Check if consensus is reached for a reading"""
        try:
            if isinstance(meter_id, str):
                meter_address = self.w3.to_checksum_address(meter_id)
            else:
                meter_address = meter_id
            
            return self.consensus.functions.checkConsensus(meter_address, sequence).call()
            
        except Exception as e:
            logging.error(f"Failed to check consensus: {e}")
            return False
    
    def register_meter(self, meter_id: str, meter_type: str, location: str) -> Optional[str]:
        """Register a new meter on blockchain"""
        try:
            if isinstance(meter_id, str):
                meter_address = self.w3.to_checksum_address(meter_id)
            else:
                meter_address = meter_id
            
            tx = self.meter_registry.functions.registerMeter(
                meter_address,
                meter_type,
                location
            ).build_transaction({
                'from': self.account.address,
                'gas': 300000,
                'gasPrice': self.get_gas_price(),
                'nonce': self.get_nonce(),
                'value': self.w3.to_wei(0.01, 'ether')  # Registration fee
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            tx_hash_hex = tx_hash.hex()
            
            # Track transaction
            self.pending_transactions[tx_hash_hex] = {
                'timestamp': time.time(),
                'meter_id': meter_id,
                'type': 'register_meter'
            }
            
            logging.info(f"Meter registration transaction submitted: {tx_hash_hex}")
            return tx_hash_hex
            
        except Exception as e:
            logging.error(f"Failed to register meter: {e}")
            return None
    
    def get_transaction_status(self, tx_hash: str) -> Dict[str, Any]:
        """Get transaction status"""
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            
            if receipt:
                return {
                    'status': 'confirmed',
                    'block_number': receipt.blockNumber,
                    'gas_used': receipt.gasUsed,
                    'success': receipt.status == 1
                }
            else:
                return {
                    'status': 'pending',
                    'block_number': None,
                    'gas_used': None,
                    'success': None
                }
                
        except Exception as e:
            logging.error(f"Failed to get transaction status: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def get_pending_transactions(self) -> Dict[str, Any]:
        """Get all pending transactions"""
        return self.pending_transactions.copy()
    
    def get_failed_transactions(self) -> List[Dict[str, Any]]:
        """Get all failed transactions"""
        return self.failed_transactions.copy()
    
    def cleanup_old_transactions(self, max_age_hours: int = 24):
        """Clean up old transaction records"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        # Clean pending transactions
        expired_txs = [
            tx_hash for tx_hash, tx_data in self.pending_transactions.items()
            if current_time - tx_data['timestamp'] > max_age_seconds
        ]
        
        for tx_hash in expired_txs:
            del self.pending_transactions[tx_hash]
        
        # Clean failed transactions
        self.failed_transactions = [
            tx for tx in self.failed_transactions
            if current_time - tx['timestamp'] <= max_age_seconds
        ]
        
        logging.info(f"Cleaned up {len(expired_txs)} expired transactions")
    
    def get_account_balance(self) -> float:
        """Get account balance in ETH"""
        try:
            balance_wei = self.w3.eth.get_balance(self.account.address)
            return self.w3.from_wei(balance_wei, 'ether')
        except Exception as e:
            logging.error(f"Failed to get account balance: {e}")
            return 0.0
    
    def estimate_gas(self, meter_id: str, sequence: int, timestamp: int, 
                    value: int, signature: str, suspicious_score: int, 
                    reasons: List[str]) -> int:
        """Estimate gas for storing a reading"""
        try:
            if isinstance(meter_id, str):
                meter_address = self.w3.to_checksum_address(meter_id)
            else:
                meter_address = meter_id
            
            signature_bytes = self.w3.to_bytes(hexstr=signature) if signature.startswith('0x') else signature.encode()
            
            gas_estimate = self.meter_store.functions.storeReading(
                meter_address,
                sequence,
                timestamp,
                value,
                signature_bytes,
                suspicious_score,
                reasons
            ).estimate_gas({'from': self.account.address})
            
            return gas_estimate
            
        except Exception as e:
            logging.error(f"Failed to estimate gas: {e}")
            return 500000  # Fallback estimate
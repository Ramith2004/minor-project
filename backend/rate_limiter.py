#!/usr/bin/env python3
"""
Rate Limiter Module
Implements advanced rate limiting with multiple algorithms and adaptive behavior
"""

import time
import threading
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass
import logging

@dataclass
class RateLimitRule:
    """Rate limiting rule configuration"""
    requests_per_minute: int
    burst_size: int
    window_size: int  # seconds
    penalty_duration: int  # seconds
    enabled: bool = True

@dataclass
class ClientInfo:
    """Client information for rate limiting"""
    ip_address: str
    request_count: int
    last_request: float
    penalty_until: float
    burst_tokens: int
    request_history: deque
    violation_count: int
    last_violation: float

class RateLimiter:
    def __init__(self, default_rule: Optional[RateLimitRule] = None):
        self.default_rule = default_rule or RateLimitRule(
            requests_per_minute=60,
            burst_size=10,
            window_size=60,
            penalty_duration=300
        )
        
        # Client tracking
        self.clients: Dict[str, ClientInfo] = {}
        
        # Custom rules per client/IP
        self.custom_rules: Dict[str, RateLimitRule] = {}
        
        # Whitelist and blacklist
        self.whitelist: set = set()
        self.blacklist: set = set()
        
        # Statistics
        self.stats = {
            'total_requests': 0,
            'allowed_requests': 0,
            'blocked_requests': 0,
            'penalty_applied': 0,
            'whitelist_hits': 0,
            'blacklist_hits': 0
        }
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
        
        logging.info("Rate limiter initialized")
    
    def is_allowed(self, client_ip: str, custom_rule: Optional[RateLimitRule] = None) -> bool:
        """Check if request is allowed for client"""
        with self.lock:
            self.stats['total_requests'] += 1
            
            # Check blacklist
            if client_ip in self.blacklist:
                self.stats['blacklist_hits'] += 1
                return False
            
            # Check whitelist
            if client_ip in self.whitelist:
                self.stats['whitelist_hits'] += 1
                self.stats['allowed_requests'] += 1
                return True
            
            # Get client info
            client_info = self._get_or_create_client(client_ip)
            
            # Check if client is under penalty
            if time.time() < client_info.penalty_until:
                self.stats['blocked_requests'] += 1
                return False
            
            # Get applicable rule
            rule = custom_rule or self.custom_rules.get(client_ip) or self.default_rule
            
            if not rule.enabled:
                self.stats['allowed_requests'] += 1
                return True
            
            # Check rate limit
            current_time = time.time()
            
            # Clean old requests from history
            self._cleanup_request_history(client_info, current_time, rule.window_size)
            
            # Check if within limits
            if len(client_info.request_history) >= rule.requests_per_minute:
                # Rate limit exceeded
                self._apply_penalty(client_info, rule.penalty_duration)
                self.stats['blocked_requests'] += 1
                return False
            
            # Check burst limit
            if client_info.burst_tokens <= 0:
                # Refill burst tokens
                client_info.burst_tokens = rule.burst_size
            
            if client_info.burst_tokens <= 0:
                self.stats['blocked_requests'] += 1
                return False
            
            # Allow request
            client_info.burst_tokens -= 1
            client_info.request_history.append(current_time)
            client_info.last_request = current_time
            client_info.request_count += 1
            
            self.stats['allowed_requests'] += 1
            return True
    
    def _get_or_create_client(self, client_ip: str) -> ClientInfo:
        """Get or create client information"""
        if client_ip not in self.clients:
            self.clients[client_ip] = ClientInfo(
                ip_address=client_ip,
                request_count=0,
                last_request=0,
                penalty_until=0,
                burst_tokens=self.default_rule.burst_size,
                request_history=deque(),
                violation_count=0,
                last_violation=0
            )
        return self.clients[client_ip]
    
    def _cleanup_request_history(self, client_info: ClientInfo, current_time: float, window_size: int):
        """Clean up old requests from history"""
        cutoff_time = current_time - window_size
        
        while client_info.request_history and client_info.request_history[0] < cutoff_time:
            client_info.request_history.popleft()
    
    def _apply_penalty(self, client_info: ClientInfo, penalty_duration: int):
        """Apply penalty to client"""
        client_info.penalty_until = time.time() + penalty_duration
        client_info.violation_count += 1
        client_info.last_violation = time.time()
        client_info.burst_tokens = 0  # Reset burst tokens
        
        self.stats['penalty_applied'] += 1
        
        logging.warning(f"Rate limit penalty applied to {client_info.ip_address} for {penalty_duration}s")
    
    def get_retry_after(self, client_ip: str) -> int:
        """Get retry after time for client"""
        with self.lock:
            if client_ip in self.clients:
                client_info = self.clients[client_ip]
                if time.time() < client_info.penalty_until:
                    return int(client_info.penalty_until - time.time())
            
            # Default retry after
            rule = self.custom_rules.get(client_ip) or self.default_rule
            return rule.window_size
    
    def add_custom_rule(self, client_ip: str, rule: RateLimitRule):
        """Add custom rate limiting rule for client"""
        with self.lock:
            self.custom_rules[client_ip] = rule
            logging.info(f"Custom rate limit rule added for {client_ip}")
    
    def remove_custom_rule(self, client_ip: str):
        """Remove custom rate limiting rule for client"""
        with self.lock:
            if client_ip in self.custom_rules:
                del self.custom_rules[client_ip]
                logging.info(f"Custom rate limit rule removed for {client_ip}")
    
    def add_to_whitelist(self, client_ip: str):
        """Add client to whitelist"""
        with self.lock:
            self.whitelist.add(client_ip)
            logging.info(f"Added {client_ip} to whitelist")
    
    def remove_from_whitelist(self, client_ip: str):
        """Remove client from whitelist"""
        with self.lock:
            self.whitelist.discard(client_ip)
            logging.info(f"Removed {client_ip} from whitelist")
    
    def add_to_blacklist(self, client_ip: str):
        """Add client to blacklist"""
        with self.lock:
            self.blacklist.add(client_ip)
            logging.info(f"Added {client_ip} to blacklist")
    
    def remove_from_blacklist(self, client_ip: str):
        """Remove client from blacklist"""
        with self.lock:
            self.blacklist.discard(client_ip)
            logging.info(f"Removed {client_ip} from blacklist")
    
    def get_client_info(self, client_ip: str) -> Optional[Dict]:
        """Get client information"""
        with self.lock:
            if client_ip not in self.clients:
                return None
            
            client_info = self.clients[client_ip]
            current_time = time.time()
            
            return {
                'ip_address': client_info.ip_address,
                'request_count': client_info.request_count,
                'last_request': client_info.last_request,
                'penalty_until': client_info.penalty_until,
                'burst_tokens': client_info.burst_tokens,
                'recent_requests': len(client_info.request_history),
                'violation_count': client_info.violation_count,
                'last_violation': client_info.last_violation,
                'is_penalized': current_time < client_info.penalty_until,
                'is_whitelisted': client_ip in self.whitelist,
                'is_blacklisted': client_ip in self.blacklist
            }
    
    def get_stats(self) -> Dict:
        """Get rate limiter statistics"""
        with self.lock:
            stats = self.stats.copy()
            stats['active_clients'] = len(self.clients)
            stats['custom_rules'] = len(self.custom_rules)
            stats['whitelist_size'] = len(self.whitelist)
            stats['blacklist_size'] = len(self.blacklist)
            
            # Calculate success rate
            if stats['total_requests'] > 0:
                stats['success_rate'] = stats['allowed_requests'] / stats['total_requests']
            else:
                stats['success_rate'] = 0
            
            return stats
    
    def reset_client(self, client_ip: str):
        """Reset client information"""
        with self.lock:
            if client_ip in self.clients:
                del self.clients[client_ip]
                logging.info(f"Reset client information for {client_ip}")
    
    def reset_all_clients(self):
        """Reset all client information"""
        with self.lock:
            self.clients.clear()
            logging.info("Reset all client information")
    
    def _cleanup_loop(self):
        """Background cleanup loop"""
        while True:
            try:
                time.sleep(300)  # Run every 5 minutes
                self._cleanup_expired_clients()
            except Exception as e:
                logging.error(f"Cleanup loop error: {e}")
    
    def _cleanup_expired_clients(self):
        """Clean up expired client information"""
        with self.lock:
            current_time = time.time()
            expired_clients = []
            
            for client_ip, client_info in self.clients.items():
                # Remove clients that haven't made requests in 1 hour
                if current_time - client_info.last_request > 3600:
                    expired_clients.append(client_ip)
            
            for client_ip in expired_clients:
                del self.clients[client_ip]
            
            if expired_clients:
                logging.info(f"Cleaned up {len(expired_clients)} expired clients")
    
    def get_top_clients(self, limit: int = 10) -> List[Dict]:
        """Get top clients by request count"""
        with self.lock:
            sorted_clients = sorted(
                self.clients.items(),
                key=lambda x: x[1].request_count,
                reverse=True
            )
            
            return [
                {
                    'ip_address': client_ip,
                    'request_count': client_info.request_count,
                    'violation_count': client_info.violation_count,
                    'last_request': client_info.last_request
                }
                for client_ip, client_info in sorted_clients[:limit]
            ]
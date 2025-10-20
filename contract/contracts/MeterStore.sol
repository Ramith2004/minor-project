// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./MeterRegistry.sol";
import "./Consensus.sol";

/**
 * @title MeterStore
 * @dev Main contract for storing and managing smart meter readings with blockchain verification
 * @notice This contract handles the storage of verified meter readings with IDS scores and consensus mechanisms
 */
contract MeterStore {
    // Events
    event ReadingStored(
        address indexed meterId,
        uint256 indexed sequence,
        uint256 timestamp,
        uint256 value,
        bytes32 signature,
        uint256 suspiciousScore,
        bool verified,
        address indexed validator
    );
    
    event ReadingVerified(
        address indexed meterId,
        uint256 indexed sequence,
        bool verified,
        address indexed verifier
    );
    
    event ConsensusReached(
        address indexed meterId,
        uint256 indexed sequence,
        bool consensus,
        uint256 voteCount
    );
    
    event SuspiciousReadingFlagged(
        address indexed meterId,
        uint256 indexed sequence,
        uint256 suspiciousScore,
        string[] reasons
    );

    // Structs
    struct MeterReading {
        uint256 sequence;
        uint256 timestamp;
        uint256 value;
        bytes32 signature;
        uint256 suspiciousScore;
        bool verified;
        bool consensusReached;
        address validator;
        uint256 blockNumber;
        uint256 gasUsed;
        string[] reasons;
        mapping(address => bool) verifiers;
        uint256 verificationCount;
    }

    struct MeterStats {
        uint256 totalReadings;
        uint256 verifiedReadings;
        uint256 suspiciousReadings;
        uint256 lastSequence;
        uint256 lastUpdate;
        uint256 averageValue;
        uint256 totalValue;
    }

    // State variables
    MeterRegistry public meterRegistry;
    Consensus public consensus;
    address public owner;
    address public idsService;
    
    // Mappings
    mapping(address => mapping(uint256 => MeterReading)) public readings;
    mapping(address => MeterStats) public meterStats;
    mapping(address => uint256) public lastSequences;
    mapping(bytes32 => bool) public signatureUsed;
    
    // Constants
    uint256 public constant MAX_SUSPICIOUS_SCORE = 1000;
    uint256 public constant MIN_VERIFICATION_COUNT = 3;
    uint256 public constant MAX_TIMESTAMP_DRIFT = 300; // 5 minutes
    uint256 public constant MAX_SEQUENCE_GAP = 100;
    
    // Modifiers
    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }
    
    modifier onlyRegisteredMeter(address meterId) {
        require(meterRegistry.isRegistered(meterId), "Meter not registered");
        _;
    }
    
    modifier onlyIDS() {
        require(msg.sender == idsService, "Only IDS service can call this function");
        _;
    }
    
    modifier validSequence(address meterId, uint256 sequence) {
        require(sequence > lastSequences[meterId], "Sequence number must be increasing");
        _;
    }
    
    modifier validTimestamp(uint256 timestamp) {
        require(
            timestamp <= block.timestamp + MAX_TIMESTAMP_DRIFT &&
            timestamp >= block.timestamp - MAX_TIMESTAMP_DRIFT,
            "Timestamp out of valid range"
        );
        _;
    }

    constructor(address _meterRegistry, address _consensus, address _idsService) {
        meterRegistry = MeterRegistry(_meterRegistry);
        consensus = Consensus(_consensus);
        idsService = _idsService;
        owner = msg.sender;
    }

    /**
     * @dev Store a new meter reading
     * @param meterId Address of the meter
     * @param sequence Sequence number
     * @param timestamp Timestamp of the reading
     * @param value Value of the reading
     * @param signature Signature of the reading
     * @param suspiciousScore IDS suspicious score (0-1000)
     * @param reasons Array of reasons for suspicious score
     */
    function storeReading(
        address meterId,
        uint256 sequence,
        uint256 timestamp,
        uint256 value,
        bytes32 signature,
        uint256 suspiciousScore,
        string[] memory reasons
    ) 
        external 
        onlyIDS
        onlyRegisteredMeter(meterId)
        validSequence(meterId, sequence)
        validTimestamp(timestamp)
        returns (bool)
    {
        // Check if signature already used
        require(!signatureUsed[signature], "Signature already used");
        
        // Validate suspicious score
        require(suspiciousScore <= MAX_SUSPICIOUS_SCORE, "Invalid suspicious score");
        
        // Create new reading
        MeterReading storage reading = readings[meterId][sequence];
        reading.sequence = sequence;
        reading.timestamp = timestamp;
        reading.value = value;
        reading.signature = signature;
        reading.suspiciousScore = suspiciousScore;
        reading.verified = false;
        reading.consensusReached = false;
        reading.validator = msg.sender;
        reading.blockNumber = block.number;
        reading.gasUsed = gasleft();
        
        // Store reasons
        for (uint256 i = 0; i < reasons.length; i++) {
            reading.reasons.push(reasons[i]);
        }
        
        // Mark signature as used
        signatureUsed[signature] = true;
        
        // Update meter stats
        _updateMeterStats(meterId, sequence, value, suspiciousScore);
        
        // Update last sequence
        lastSequences[meterId] = sequence;
        
        // Emit event
        emit ReadingStored(
            meterId,
            sequence,
            timestamp,
            value,
            signature,
            suspiciousScore,
            false,
            msg.sender
        );
        
        // If suspicious score is high, flag for review
        if (suspiciousScore > 700) {
            emit SuspiciousReadingFlagged(meterId, sequence, suspiciousScore, reasons);
        }
        
        return true;
    }

    /**
     * @dev Verify a reading (can be called by multiple verifiers)
     * @param meterId Address of the meter
     * @param sequence Sequence number
     * @param verified Whether the reading is verified
     */
    function verifyReading(
        address meterId,
        uint256 sequence,
        bool verified
    ) external onlyRegisteredMeter(meterId) {
        MeterReading storage reading = readings[meterId][sequence];
        require(reading.sequence == sequence, "Reading does not exist");
        require(!reading.verifiers[msg.sender], "Already verified by this address");
        
        // Add verifier
        reading.verifiers[msg.sender] = true;
        reading.verificationCount++;
        
        // Emit verification event
        emit ReadingVerified(meterId, sequence, verified, msg.sender);
        
        // Check if consensus reached
        if (reading.verificationCount >= MIN_VERIFICATION_COUNT) {
            bool consensusResult = consensus.checkConsensus(meterId, sequence);
            reading.consensusReached = consensusResult;
            
            if (consensusResult) {
                reading.verified = true;
                emit ConsensusReached(meterId, sequence, true, reading.verificationCount);
            }
        }
    }

    /**
     * @dev Get reading details
     * @param meterId Address of the meter
     * @param sequence Sequence number
     * @return reading details
     */
    function getReading(address meterId, uint256 sequence) 
        external 
        view 
        returns (
            uint256 timestamp,
            uint256 value,
            bytes32 signature,
            uint256 suspiciousScore,
            bool verified,
            bool consensusReached,
            address validator,
            uint256 blockNumber,
            uint256 verificationCount
        )
    {
        MeterReading storage reading = readings[meterId][sequence];
        require(reading.sequence == sequence, "Reading does not exist");
        
        return (
            reading.timestamp,
            reading.value,
            reading.signature,
            reading.suspiciousScore,
            reading.verified,
            reading.consensusReached,
            reading.validator,
            reading.blockNumber,
            reading.verificationCount
        );
    }

    /**
     * @dev Get reading reasons
     * @param meterId Address of the meter
     * @param sequence Sequence number
     * @return reasons array
     */
    function getReadingReasons(address meterId, uint256 sequence) 
        external 
        view 
        returns (string[] memory)
    {
        MeterReading storage reading = readings[meterId][sequence];
        require(reading.sequence == sequence, "Reading does not exist");
        
        return reading.reasons;
    }

    /**
     * @dev Get meter statistics
     * @param meterId Address of the meter
     * @return stats Meter statistics
     */
    function getMeterStats(address meterId) 
        external 
        view 
        returns (
            uint256 totalReadings,
            uint256 verifiedReadings,
            uint256 suspiciousReadings,
            uint256 lastSequence,
            uint256 lastUpdate,
            uint256 averageValue,
            uint256 totalValue
        )
    {
        MeterStats storage stats = meterStats[meterId];
        
        return (
            stats.totalReadings,
            stats.verifiedReadings,
            stats.suspiciousReadings,
            stats.lastSequence,
            stats.lastUpdate,
            stats.averageValue,
            stats.totalValue
        );
    }

    /**
     * @dev Check if a reading exists
     * @param meterId Address of the meter
     * @param sequence Sequence number
     * @return exists Whether the reading exists
     */
    function readingExists(address meterId, uint256 sequence) 
        external 
        view 
        returns (bool)
    {
        return readings[meterId][sequence].sequence == sequence;
    }

    /**
     * @dev Get last sequence number for a meter
     * @param meterId Address of the meter
     * @return sequence Last sequence number
     */
    function getLastSequence(address meterId) external view returns (uint256) {
        return lastSequences[meterId];
    }

    /**
     * @dev Update meter statistics
     * @param meterId Address of the meter
     * @param sequence Sequence number
     * @param value Value of the reading
     * @param suspiciousScore Suspicious score
     */
    function _updateMeterStats(
        address meterId,
        uint256 sequence,
        uint256 value,
        uint256 suspiciousScore
    ) internal {
        MeterStats storage stats = meterStats[meterId];
        
        stats.totalReadings++;
        stats.lastSequence = sequence;
        stats.lastUpdate = block.timestamp;
        stats.totalValue += value;
        stats.averageValue = stats.totalValue / stats.totalReadings;
        
        if (suspiciousScore > 500) {
            stats.suspiciousReadings++;
        }
        
        if (suspiciousScore < 200) {
            stats.verifiedReadings++;
        }
    }

    /**
     * @dev Update IDS service address
     * @param newIDS New IDS service address
     */
    function updateIDSService(address newIDS) external onlyOwner {
        require(newIDS != address(0), "Invalid IDS service address");
        idsService = newIDS;
    }

    /**
     * @dev Emergency function to pause contract
     */
    function emergencyPause() external onlyOwner {
        // Implementation for emergency pause
        // This would require additional state management
    }

    /**
     * @dev Get contract version
     * @return version Contract version
     */
    function getVersion() external pure returns (string memory) {
        return "1.0.0";
    }
}
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title Consensus
 * @dev Consensus mechanism for verifying meter readings
 * @notice This contract implements various consensus mechanisms for validating meter readings
 */
contract Consensus {
    // Events
    event VoteCast(
        address indexed meterId,
        uint256 indexed sequence,
        address indexed voter,
        bool vote,
        uint256 weight
    );
    
    event ConsensusReached(
        address indexed meterId,
        uint256 indexed sequence,
        bool consensus,
        uint256 totalWeight,
        uint256 requiredWeight
    );
    
    event ValidatorAdded(
        address indexed validator,
        uint256 weight,
        string description
    );
    
    event ValidatorRemoved(
        address indexed validator,
        string reason
    );
    
    event ValidatorWeightUpdated(
        address indexed validator,
        uint256 oldWeight,
        uint256 newWeight
    );

    // Structs
    struct Vote {
        address voter;
        bool vote;
        uint256 weight;
        uint256 timestamp;
        string reason;
    }

    struct ConsensusSession {
        address meterId;
        uint256 sequence;
        uint256 startTime;
        uint256 endTime;
        uint256 totalWeight;
        uint256 requiredWeight;
        bool consensusReached;
        bool finalResult;
        mapping(address => Vote) votes;
        address[] voters;
        uint256 yesWeight;
        uint256 noWeight;
    }

    struct Validator {
        address validator;
        uint256 weight;
        bool isActive;
        string description;
        uint256 registrationTime;
        uint256 totalVotes;
        uint256 correctVotes;
    }

    // State variables
    address public owner;
    address public admin;
    
    // Mappings
    mapping(bytes32 => ConsensusSession) public consensusSessions;
    mapping(address => Validator) public validators;
    mapping(address => bool) public isValidator;
    mapping(address => uint256) public validatorPerformance;
    
    // Arrays
    address[] public allValidators;
    
    // Constants
    uint256 public constant MIN_VALIDATORS = 3;
    uint256 public constant MAX_VALIDATORS = 50;
    uint256 public constant CONSENSUS_TIMEOUT = 300; // 5 minutes
    uint256 public constant MIN_CONSENSUS_THRESHOLD = 51; // 51%
    uint256 public constant MAX_CONSENSUS_THRESHOLD = 75; // 75%
    
    // State
    uint256 public totalValidatorWeight;
    uint256 public consensusThreshold = 66; // 66% default threshold
    
    // Modifiers
    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }
    
    modifier onlyAdmin() {
        require(msg.sender == admin || msg.sender == owner, "Only admin can call this function");
        _;
    }
    
    modifier onlyValidator() {
        require(isValidator[msg.sender], "Only validators can call this function");
        require(validators[msg.sender].isActive, "Validator not active");
        _;
    }

    constructor() {
        owner = msg.sender;
        admin = msg.sender;
    }

    /**
     * @dev Add a new validator
     * @param validator Address of the validator
     * @param weight Weight of the validator
     * @param description Description of the validator
     */
    function addValidator(
        address validator,
        uint256 weight,
        string memory description
    ) external onlyAdmin {
        require(validator != address(0), "Invalid validator address");
        require(!isValidator[validator], "Validator already exists");
        require(weight > 0, "Weight must be greater than 0");
        require(allValidators.length < MAX_VALIDATORS, "Maximum validators reached");
        require(bytes(description).length > 0, "Description cannot be empty");
        
        validators[validator] = Validator({
            validator: validator,
            weight: weight,
            isActive: true,
            description: description,
            registrationTime: block.timestamp,
            totalVotes: 0,
            correctVotes: 0
        });
        
        isValidator[validator] = true;
        allValidators.push(validator);
        totalValidatorWeight += weight;
        
        emit ValidatorAdded(validator, weight, description);
    }

    /**
     * @dev Remove a validator
     * @param validator Address of the validator
     * @param reason Reason for removal
     */
    function removeValidator(
        address validator,
        string memory reason
    ) external onlyAdmin {
        require(isValidator[validator], "Validator does not exist");
        require(bytes(reason).length > 0, "Reason cannot be empty");
        
        totalValidatorWeight -= validators[validator].weight;
        validators[validator].isActive = false;
        
        // Remove from array
        for (uint256 i = 0; i < allValidators.length; i++) {
            if (allValidators[i] == validator) {
                allValidators[i] = allValidators[allValidators.length - 1];
                allValidators.pop();
                break;
            }
        }
        
        isValidator[validator] = false;
        
        emit ValidatorRemoved(validator, reason);
    }

    /**
     * @dev Update validator weight
     * @param validator Address of the validator
     * @param newWeight New weight
     */
    function updateValidatorWeight(
        address validator,
        uint256 newWeight
    ) external onlyAdmin {
        require(isValidator[validator], "Validator does not exist");
        require(newWeight > 0, "Weight must be greater than 0");
        
        uint256 oldWeight = validators[validator].weight;
        totalValidatorWeight = totalValidatorWeight - oldWeight + newWeight;
        validators[validator].weight = newWeight;
        
        emit ValidatorWeightUpdated(validator, oldWeight, newWeight);
    }

    /**
     * @dev Start a consensus session
     * @param meterId Address of the meter
     * @param sequence Sequence number
     * @return sessionId Session ID
     */
    function startConsensus(
        address meterId,
        uint256 sequence
    ) external onlyValidator returns (bytes32) {
        bytes32 sessionId = keccak256(abi.encodePacked(meterId, sequence, block.timestamp));
        
        require(consensusSessions[sessionId].meterId == address(0), "Session already exists");
        require(allValidators.length >= MIN_VALIDATORS, "Insufficient validators");
        
        ConsensusSession storage session = consensusSessions[sessionId];
        session.meterId = meterId;
        session.sequence = sequence;
        session.startTime = block.timestamp;
        session.endTime = block.timestamp + CONSENSUS_TIMEOUT;
        session.totalWeight = totalValidatorWeight;
        session.requiredWeight = (totalValidatorWeight * consensusThreshold) / 100;
        session.consensusReached = false;
        session.finalResult = false;
        session.yesWeight = 0;
        session.noWeight = 0;
        
        return sessionId;
    }

    /**
     * @dev Cast a vote in consensus session
     * @param sessionId Session ID
     * @param vote Vote (true for yes, false for no)
     * @param reason Reason for the vote
     */
    function castVote(
        bytes32 sessionId,
        bool vote,
        string memory reason
    ) external onlyValidator {
        ConsensusSession storage session = consensusSessions[sessionId];
        require(session.meterId != address(0), "Session does not exist");
        require(block.timestamp <= session.endTime, "Consensus session expired");
        require(session.votes[msg.sender].voter == address(0), "Already voted");
        
        uint256 weight = validators[msg.sender].weight;
        
        session.votes[msg.sender] = Vote({
            voter: msg.sender,
            vote: vote,
            weight: weight,
            timestamp: block.timestamp,
            reason: reason
        });
        
        session.voters.push(msg.sender);
        
        if (vote) {
            session.yesWeight += weight;
        } else {
            session.noWeight += weight;
        }
        
        // Update validator stats
        validators[msg.sender].totalVotes++;
        
        emit VoteCast(session.meterId, session.sequence, msg.sender, vote, weight);
        
        // Check if consensus reached
        _checkConsensus(sessionId);
    }

    /**
     * @dev Check if consensus is reached
     * @param sessionId Session ID
     */
    function _checkConsensus(bytes32 sessionId) internal {
        ConsensusSession storage session = consensusSessions[sessionId];
        
        uint256 totalVotedWeight = session.yesWeight + session.noWeight;
        
        if (totalVotedWeight >= session.requiredWeight) {
            session.consensusReached = true;
            session.finalResult = session.yesWeight > session.noWeight;
            
            emit ConsensusReached(
                session.meterId,
                session.sequence,
                session.finalResult,
                totalVotedWeight,
                session.requiredWeight
            );
        }
    }

    /**
     * @dev Check consensus for a specific meter and sequence
     * @param meterId Address of the meter
     * @param sequence Sequence number
     * @return consensus Whether consensus is reached
     */
    function checkConsensus(
        address meterId,
        uint256 sequence
    ) external view returns (bool) {
        // Find the most recent consensus session for this meter and sequence
        for (uint256 i = 0; i < allValidators.length; i++) {
            bytes32 sessionId = keccak256(abi.encodePacked(meterId, sequence, i));
            ConsensusSession storage session = consensusSessions[sessionId];
            
            if (session.meterId == meterId && session.sequence == sequence) {
                return session.consensusReached && session.finalResult;
            }
        }
        
        return false;
    }

    /**
     * @dev Get consensus session details
     * @param sessionId Session ID
     * @return meterId Address of the meter
     * @return sequence Sequence number
     * @return startTime Start time
     * @return endTime End time
     * @return consensusReached Whether consensus is reached
     * @return finalResult Final consensus result
     * @return yesWeight Weight of yes votes
     * @return noWeight Weight of no votes
     * @return requiredWeight Required weight for consensus
     */
    function getConsensusSession(bytes32 sessionId) 
        external 
        view 
        returns (
            address meterId,
            uint256 sequence,
            uint256 startTime,
            uint256 endTime,
            bool consensusReached,
            bool finalResult,
            uint256 yesWeight,
            uint256 noWeight,
            uint256 requiredWeight
        )
    {
        ConsensusSession storage session = consensusSessions[sessionId];
        require(session.meterId != address(0), "Session does not exist");
        
        return (
            session.meterId,
            session.sequence,
            session.startTime,
            session.endTime,
            session.consensusReached,
            session.finalResult,
            session.yesWeight,
            session.noWeight,
            session.requiredWeight
        );
    }

    /**
     * @dev Get vote details for a session
     * @param sessionId Session ID
     * @param voter Address of the voter
     * @return vote Vote details
     */
    function getVote(bytes32 sessionId, address voter) 
        external 
        view 
        returns (
            bool vote,
            uint256 weight,
            uint256 timestamp,
            string memory reason
        )
    {
        ConsensusSession storage session = consensusSessions[sessionId];
        require(session.meterId != address(0), "Session does not exist");
        
        Vote storage voteData = session.votes[voter];
        require(voteData.voter != address(0), "Vote does not exist");
        
        return (
            voteData.vote,
            voteData.weight,
            voteData.timestamp,
            voteData.reason
        );
    }

    /**
     * @dev Get validator information
     * @param validator Address of the validator
     * @return weight Weight of the validator
     * @return isActive Whether the validator is active
     * @return description Description of the validator
     * @return registrationTime Registration timestamp
     * @return totalVotes Total votes cast
     * @return correctVotes Correct votes
     */
    function getValidatorInfo(address validator) 
        external 
        view 
        returns (
            uint256 weight,
            bool isActive,
            string memory description,
            uint256 registrationTime,
            uint256 totalVotes,
            uint256 correctVotes
        )
    {
        require(isValidator[validator], "Validator does not exist");
        
        Validator storage val = validators[validator];
        return (
            val.weight,
            val.isActive,
            val.description,
            val.registrationTime,
            val.totalVotes,
            val.correctVotes
        );
    }

    /**
     * @dev Get all validators
     * @return validators Array of validator addresses
     */
    function getAllValidators() external view returns (address[] memory) {
        return allValidators;
    }

    /**
     * @dev Get validator performance
     * @param validator Address of the validator
     * @return performance Performance score (0-100)
     */
    function getValidatorPerformance(address validator) 
        external 
        view 
        returns (uint256) 
    {
        require(isValidator[validator], "Validator does not exist");
        
        Validator storage val = validators[validator];
        if (val.totalVotes == 0) {
            return 0;
        }
        
        return (val.correctVotes * 100) / val.totalVotes;
    }

    /**
     * @dev Update consensus threshold
     * @param newThreshold New threshold percentage
     */
    function updateConsensusThreshold(uint256 newThreshold) external onlyAdmin {
        require(
            newThreshold >= MIN_CONSENSUS_THRESHOLD && 
            newThreshold <= MAX_CONSENSUS_THRESHOLD,
            "Invalid threshold"
        );
        
        consensusThreshold = newThreshold;
    }

    /**
     * @dev Update admin address
     * @param newAdmin New admin address
     */
    function updateAdmin(address newAdmin) external onlyOwner {
        require(newAdmin != address(0), "Invalid admin address");
        admin = newAdmin;
    }

    /**
     * @dev Get contract version
     * @return version Contract version
     */
    function getVersion() external pure returns (string memory) {
        return "1.0.0";
    }
}
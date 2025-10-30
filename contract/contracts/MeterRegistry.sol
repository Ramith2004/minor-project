// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title MeterRegistry
 * @dev Contract for registering and managing smart meters
 * @notice This contract handles the registration, validation, and management of smart meters
 */
contract MeterRegistry {
    // Events
    event MeterRegistered(
        address indexed meterId,
        string meterType,
        string location,
        address indexed owner,
        uint256 registrationTime
    );
    
    event MeterUpdated(
        address indexed meterId,
        string meterType,
        string location,
        address indexed owner
    );
    
    event MeterSuspended(
        address indexed meterId,
        address indexed admin,
        string reason
    );
    
    event MeterReactivated(
        address indexed meterId,
        address indexed admin,
        string reason
    );
    
    event MeterOwnershipTransferred(
        address indexed meterId,
        address indexed oldOwner,
        address indexed newOwner
    );

    // Structs
    struct MeterInfo {
        address meterId;
        string meterType;
        string location;
        address owner;
        uint256 registrationTime;
        bool isActive;
        bool isSuspended;
        string suspensionReason;
        address suspendedBy;
        uint256 suspensionTime;
        mapping(address => bool) authorizedUsers;
        uint256 authorizedUserCount;
    }

    struct MeterType {
        string name;
        string description;
        uint256 maxValue;
        uint256 minValue;
        bool isActive;
    }

    // State variables
    address public owner;
    address public admin;
    
    // Mappings
    mapping(address => MeterInfo) public meters;
    mapping(string => MeterType) public meterTypes;
    mapping(address => bool) public registeredMeters;
    mapping(address => uint256) public meterCount;
    
    // Arrays
    address[] public allMeters;
    string[] public allMeterTypes;
    
    // Constants
    uint256 public constant MAX_METERS_PER_OWNER = 100;
    uint256 public constant REGISTRATION_FEE = 0.01 ether;
    
    // Modifiers
    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }
    
    modifier onlyAdmin() {
        require(msg.sender == admin || msg.sender == owner, "Only admin can call this function");
        _;
    }
    
    modifier onlyMeterOwner(address meterId) {
        require(meters[meterId].owner == msg.sender, "Only meter owner can call this function");
        _;
    }
    
    modifier onlyRegisteredMeter(address meterId) {
        require(registeredMeters[meterId], "Meter not registered");
        _;
    }
    
    modifier onlyActiveMeter(address meterId) {
        require(registeredMeters[meterId] && meters[meterId].isActive && !meters[meterId].isSuspended, "Meter not active");
        _;
    }

    constructor() {
        owner = msg.sender;
        admin = msg.sender;
        
        // Initialize default meter types
        _addMeterType("residential", "Residential Smart Meter", 10000, 0, true);
        _addMeterType("commercial", "Commercial Smart Meter", 100000, 0, true);
        _addMeterType("industrial", "Industrial Smart Meter", 1000000, 0, true);
    }

    /**
     * @dev Register a new meter
     * @param meterId Address of the meter
     * @param meterType Type of the meter
     * @param location Location of the meter
     */
    function registerMeter(
        address meterId,
        string memory meterType,
        string memory location
    ) external payable {
        require(!registeredMeters[meterId], "Meter already registered");
        require(meterId != address(0), "Invalid meter address");
        require(bytes(meterType).length > 0, "Meter type cannot be empty");
        require(bytes(location).length > 0, "Location cannot be empty");
        require(msg.value >= REGISTRATION_FEE, "Insufficient registration fee");
        
        // Check meter type exists
        require(bytes(meterTypes[meterType].name).length > 0, "Invalid meter type");
        require(meterTypes[meterType].isActive, "Meter type not active");
        
        // Check owner meter limit
        require(meterCount[msg.sender] < MAX_METERS_PER_OWNER, "Maximum meters per owner exceeded");
        
        // Create meter info
        MeterInfo storage meter = meters[meterId];
        meter.meterId = meterId;
        meter.meterType = meterType;
        meter.location = location;
        meter.owner = msg.sender;
        meter.registrationTime = block.timestamp;
        meter.isActive = true;
        meter.isSuspended = false;
        meter.authorizedUsers[msg.sender] = true;
        meter.authorizedUserCount = 1;
        
        // Update mappings
        registeredMeters[meterId] = true;
        meterCount[msg.sender]++;
        allMeters.push(meterId);
        
        // Emit event
        emit MeterRegistered(meterId, meterType, location, msg.sender, block.timestamp);
        
        // Refund excess payment
        if (msg.value > REGISTRATION_FEE) {
            payable(msg.sender).transfer(msg.value - REGISTRATION_FEE);
        }
    }

    /**
     * @dev Update meter information
     * @param meterId Address of the meter
     * @param meterType New meter type
     * @param location New location
     */
    function updateMeter(
        address meterId,
        string memory meterType,
        string memory location
    ) external onlyMeterOwner(meterId) onlyRegisteredMeter(meterId) {
        require(bytes(meterType).length > 0, "Meter type cannot be empty");
        require(bytes(location).length > 0, "Location cannot be empty");
        require(bytes(meterTypes[meterType].name).length > 0, "Invalid meter type");
        require(meterTypes[meterType].isActive, "Meter type not active");
        
        MeterInfo storage meter = meters[meterId];
        meter.meterType = meterType;
        meter.location = location;
        
        emit MeterUpdated(meterId, meterType, location, msg.sender);
    }

    /**
     * @dev Suspend a meter
     * @param meterId Address of the meter
     * @param reason Reason for suspension
     */
    function suspendMeter(
        address meterId,
        string memory reason
    ) external onlyAdmin onlyRegisteredMeter(meterId) {
        require(!meters[meterId].isSuspended, "Meter already suspended");
        require(bytes(reason).length > 0, "Suspension reason cannot be empty");
        
        MeterInfo storage meter = meters[meterId];
        meter.isSuspended = true;
        meter.suspensionReason = reason;
        meter.suspendedBy = msg.sender;
        meter.suspensionTime = block.timestamp;
        
        emit MeterSuspended(meterId, msg.sender, reason);
    }

    /**
     * @dev Reactivate a suspended meter
     * @param meterId Address of the meter
     * @param reason Reason for reactivation
     */
    function reactivateMeter(
        address meterId,
        string memory reason
    ) external onlyAdmin onlyRegisteredMeter(meterId) {
        require(meters[meterId].isSuspended, "Meter not suspended");
        require(bytes(reason).length > 0, "Reactivation reason cannot be empty");
        
        MeterInfo storage meter = meters[meterId];
        meter.isSuspended = false;
        meter.suspensionReason = "";
        meter.suspendedBy = address(0);
        meter.suspensionTime = 0;
        
        emit MeterReactivated(meterId, msg.sender, reason);
    }

    /**
     * @dev Transfer meter ownership
     * @param meterId Address of the meter
     * @param newOwner New owner address
     */
    function transferMeterOwnership(
        address meterId,
        address newOwner
    ) external onlyMeterOwner(meterId) onlyRegisteredMeter(meterId) {
        require(newOwner != address(0), "Invalid new owner address");
        require(newOwner != msg.sender, "New owner cannot be current owner");
        
        MeterInfo storage meter = meters[meterId];
        address oldOwner = meter.owner;
        
        // Update ownership
        meter.owner = newOwner;
        meter.authorizedUsers[oldOwner] = false;
        meter.authorizedUsers[newOwner] = true;
        
        // Update meter counts
        meterCount[oldOwner]--;
        meterCount[newOwner]++;
        
        emit MeterOwnershipTransferred(meterId, oldOwner, newOwner);
    }

    /**
     * @dev Add authorized user to meter
     * @param meterId Address of the meter
     * @param user Address of the user to authorize
     */
    function addAuthorizedUser(
        address meterId,
        address user
    ) external onlyMeterOwner(meterId) onlyRegisteredMeter(meterId) {
        require(user != address(0), "Invalid user address");
        require(!meters[meterId].authorizedUsers[user], "User already authorized");
        
        meters[meterId].authorizedUsers[user] = true;
        meters[meterId].authorizedUserCount++;
    }

    /**
     * @dev Remove authorized user from meter
     * @param meterId Address of the meter
     * @param user Address of the user to remove
     */
    function removeAuthorizedUser(
        address meterId,
        address user
    ) external onlyMeterOwner(meterId) onlyRegisteredMeter(meterId) {
        require(meters[meterId].authorizedUsers[user], "User not authorized");
        require(user != meters[meterId].owner, "Cannot remove owner");
        
        meters[meterId].authorizedUsers[user] = false;
        meters[meterId].authorizedUserCount--;
    }

    /**
     * @dev Add new meter type
     * @param name Name of the meter type
     * @param description Description of the meter type
     * @param maxValue Maximum value for this meter type
     * @param minValue Minimum value for this meter type
     * @param isActive Whether the meter type is active
     */
    function addMeterType(
        string memory name,
        string memory description,
        uint256 maxValue,
        uint256 minValue,
        bool isActive
    ) external onlyAdmin {
        _addMeterType(name, description, maxValue, minValue, isActive);
    }

    /**
     * @dev Internal function to add meter type
     */
    function _addMeterType(
        string memory name,
        string memory description,
        uint256 maxValue,
        uint256 minValue,
        bool isActive
    ) internal {
        require(bytes(name).length > 0, "Meter type name cannot be empty");
        require(maxValue > minValue, "Max value must be greater than min value");
        
        MeterType storage meterType = meterTypes[name];
        meterType.name = name;
        meterType.description = description;
        meterType.maxValue = maxValue;
        meterType.minValue = minValue;
        meterType.isActive = isActive;
        
        allMeterTypes.push(name);
    }

    /**
     * @dev Update meter type
     * @param name Name of the meter type
     * @param description New description
     * @param maxValue New maximum value
     * @param minValue New minimum value
     * @param isActive New active status
     */
    function updateMeterType(
        string memory name,
        string memory description,
        uint256 maxValue,
        uint256 minValue,
        bool isActive
    ) external onlyAdmin {
        require(bytes(meterTypes[name].name).length > 0, "Meter type does not exist");
        require(maxValue > minValue, "Max value must be greater than min value");
        
        MeterType storage meterType = meterTypes[name];
        meterType.description = description;
        meterType.maxValue = maxValue;
        meterType.minValue = minValue;
        meterType.isActive = isActive;
    }

    /**
     * @dev Check if meter is registered
     * @param meterId Address of the meter
     * @return isRegistered Whether the meter is registered
     */
    function isRegistered(address meterId) external view returns (bool) {
        return registeredMeters[meterId];
    }

    /**
     * @dev Check if meter is active
     * @param meterId Address of the meter
     * @return isActive Whether the meter is active
     */
    function isActive(address meterId) external view returns (bool) {
        return registeredMeters[meterId] && meters[meterId].isActive && !meters[meterId].isSuspended;
    }

    /**
     * @dev Get meter information
     * @param meterId Address of the meter
     * @return meterType Type of the meter
     * @return location Location of the meter
     * @return owner Owner of the meter
     * @return registrationTime Registration timestamp
     * @return isActive Whether the meter is active
     * @return isSuspended Whether the meter is suspended
     */
    function getMeterInfo(address meterId) 
        external 
        view 
        returns (
            string memory meterType,
            string memory location,
            address owner,
            uint256 registrationTime,
            bool isActive,
            bool isSuspended
        )
    {
        require(registeredMeters[meterId], "Meter not registered");
        
        MeterInfo storage meter = meters[meterId];
        return (
            meter.meterType,
            meter.location,
            meter.owner,
            meter.registrationTime,
            meter.isActive,
            meter.isSuspended
        );
    }

    /**
     * @dev Get meter type information
     * @param name Name of the meter type
     * @return description Description of the meter type
     * @return maxValue Maximum value
     * @return minValue Minimum value
     * @return isActive Whether the meter type is active
     */
    function getMeterType(string memory name) 
        external 
        view 
        returns (
            string memory description,
            uint256 maxValue,
            uint256 minValue,
            bool isActive
        )
    {
        require(bytes(meterTypes[name].name).length > 0, "Meter type does not exist");
        
        MeterType storage meterType = meterTypes[name];
        return (
            meterType.description,
            meterType.maxValue,
            meterType.minValue,
            meterType.isActive
        );
    }

    /**
     * @dev Get all registered meters
     * @return meters Array of all meter addresses
     */
    function getAllMeters() external view returns (address[] memory) {
        return allMeters;
    }

    /**
     * @dev Get all meter types
     * @return types Array of all meter type names
     */
    function getAllMeterTypes() external view returns (string[] memory) {
        return allMeterTypes;
    }

    /**
     * @dev Get total number of registered meters
     * @return count Total number of meters
     */
    function getTotalMeterCount() external view returns (uint256) {
        return allMeters.length;
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
     * @dev Withdraw contract balance
     */
    function withdraw() external onlyOwner {
        uint256 balance = address(this).balance;
        require(balance > 0, "No balance to withdraw");
        
        payable(owner).transfer(balance);
    }

    /**
     * @dev Get contract version
     * @return version Contract version
     */
    function getVersion() external pure returns (string memory) {
        return "1.0.0";
    }
}
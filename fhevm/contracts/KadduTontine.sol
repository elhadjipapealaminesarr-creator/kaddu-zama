// SPDX-License-Identifier: BSD-3-Clause-Clear
pragma solidity ^0.8.24;

import {FHE, euint64, externalEuint8} from "@fhevm/solidity/lib/FHE.sol";
import {ZamaEthereumConfig} from "@fhevm/solidity/config/ZamaConfig.sol";

/// @title KadduTontine — a tamper-proof rotating savings group (tontine) whose
///        GOVERNANCE is decided by confidential on-chain voting (Zama fhEVM).
/// @notice What makes this different from a generic "confidential savings vault":
///         1. Rotating turns — at each cycle, the member at that position is the
///            beneficiary who receives the pot.
///         2. Two-party validation — a contribution counts for a cycle only if the
///            PAYER confirms they paid AND the BENEFICIARY confirms they received.
///            The admin can never validate a payment alone, so no single manager
///            can fake the books.
///         3. Confidential governance — when a member asks to move up in the queue
///            ("main levee" / early turn), the other members vote SECRETLY. Votes
///            are encrypted; the contract tallies them on ciphertext and only the
///            aggregate (yes-count) is ever revealed. No one learns who voted how.
///         The money itself never touches the contract — Kaddu is the impartial,
///         tamper-evident referee; mobile-money settlement stays off-chain.
contract KadduTontine is ZamaEthereumConfig {
    // ----------------------------------------------------------------- types
    struct Member {
        address wallet;
        string name;
        bool active;
    }

    struct Core {
        address admin;
        string name;
        uint64 amount;        // fixed contribution per cycle (a public group rule)
        uint32 memberCount;   // number of positions (1..memberCount)
        uint32 currentCycle;  // 1-based; beneficiary = member at position currentCycle
        bool started;
    }

    struct Request {
        uint256 tontineId;
        address requester;
        bool open;
        uint32 voterCount;    // public: how many members voted
        euint64 yesTally;     // encrypted: number of "yes" votes
    }

    // --------------------------------------------------------------- storage
    uint256 public tontineCount;
    mapping(uint256 => Core) private cores;
    // tontineId => position(1..n) => Member
    mapping(uint256 => mapping(uint256 => Member)) private members;
    // tontineId => wallet => position (0 = not a member)
    mapping(uint256 => mapping(address => uint256)) private positionOf;
    // tontineId => cycle => position => payer confirmed
    mapping(uint256 => mapping(uint32 => mapping(uint256 => bool))) public payerConfirmed;
    // tontineId => cycle => beneficiary confirmed receipt
    mapping(uint256 => mapping(uint32 => bool)) public receiptConfirmed;

    uint256 public requestCount;
    mapping(uint256 => Request) private requests;
    mapping(uint256 => mapping(address => bool)) public requestVoted;

    // ---------------------------------------------------------------- events
    event TontineCreated(uint256 indexed tontineId, address indexed admin, string name);
    event Started(uint256 indexed tontineId);
    event PaymentConfirmed(uint256 indexed tontineId, uint32 indexed cycle, uint256 position);
    event ReceiptConfirmed(uint256 indexed tontineId, uint32 indexed cycle, uint256 position);
    event CycleAdvanced(uint256 indexed tontineId, uint32 newCycle);
    event EarlyTurnRequested(uint256 indexed requestId, uint256 indexed tontineId, address indexed requester);
    event RequestVoted(uint256 indexed requestId, address indexed voter);
    event RequestClosed(uint256 indexed requestId);

    // ------------------------------------------------------------ management
    /// @notice Create a tontine. `names[i]` is seated at position i+1.
    function createTontine(
        string calldata name,
        uint64 amount,
        string[] calldata names,
        address[] calldata wallets
    ) external returns (uint256 tontineId) {
        require(names.length == wallets.length, "len mismatch");
        require(names.length >= 2 && names.length <= 50, "2-50 members");

        tontineId = tontineCount++;
        Core storage c = cores[tontineId];
        c.admin = msg.sender;
        c.name = name;
        c.amount = amount;
        c.memberCount = uint32(names.length);
        c.currentCycle = 1;

        for (uint256 i = 0; i < names.length; i++) {
            uint256 pos = i + 1;
            require(positionOf[tontineId][wallets[i]] == 0, "dup wallet");
            members[tontineId][pos] = Member({wallet: wallets[i], name: names[i], active: true});
            positionOf[tontineId][wallets[i]] = pos;
        }
        emit TontineCreated(tontineId, msg.sender, name);
    }

    function start(uint256 tontineId) external {
        Core storage c = cores[tontineId];
        require(msg.sender == c.admin, "not admin");
        require(!c.started, "started");
        c.started = true;
        emit Started(tontineId);
    }

    // ----------------------------------------------- two-party confirmation
    /// @notice A member confirms they have paid their contribution for the current cycle.
    function confirmPayment(uint256 tontineId) external {
        Core storage c = cores[tontineId];
        require(c.started, "not started");
        uint256 pos = positionOf[tontineId][msg.sender];
        require(pos != 0, "not a member");
        payerConfirmed[tontineId][c.currentCycle][pos] = true;
        emit PaymentConfirmed(tontineId, c.currentCycle, pos);
    }

    /// @notice The current beneficiary confirms they received the pot for this cycle.
    function confirmReceipt(uint256 tontineId) external {
        Core storage c = cores[tontineId];
        require(c.started, "not started");
        uint256 pos = positionOf[tontineId][msg.sender];
        require(pos == c.currentCycle, "not the beneficiary");
        receiptConfirmed[tontineId][c.currentCycle] = true;
        emit ReceiptConfirmed(tontineId, c.currentCycle, pos);
    }

    /// @notice Advance to the next cycle. Only possible when every active member has
    ///         confirmed payment AND the beneficiary has confirmed receipt — so the
    ///         admin cannot skip a step or fake a cycle.
    function advanceCycle(uint256 tontineId) external {
        Core storage c = cores[tontineId];
        require(msg.sender == c.admin, "not admin");
        require(c.started, "not started");
        require(c.currentCycle <= c.memberCount, "tontine complete");
        require(receiptConfirmed[tontineId][c.currentCycle], "receipt pending");
        for (uint256 p = 1; p <= c.memberCount; p++) {
            if (members[tontineId][p].active) {
                require(payerConfirmed[tontineId][c.currentCycle][p], "payment pending");
            }
        }
        c.currentCycle += 1;
        emit CycleAdvanced(tontineId, c.currentCycle);
    }

    // -------------------------------------------- confidential governance
    /// @notice A member requests to move up in the queue (an "early turn").
    ///         This opens a confidential vote among the members.
    function requestEarlyTurn(uint256 tontineId) external returns (uint256 requestId) {
        Core storage c = cores[tontineId];
        require(c.started, "not started");
        require(positionOf[tontineId][msg.sender] != 0, "not a member");

        requestId = requestCount++;
        Request storage r = requests[requestId];
        r.tontineId = tontineId;
        r.requester = msg.sender;
        r.open = true;
        r.yesTally = FHE.asEuint64(0);
        FHE.allowThis(r.yesTally);
        emit EarlyTurnRequested(requestId, tontineId, msg.sender);
    }

    /// @notice Vote SECRETLY on a request. `encVote` is 0 (no) or 1 (yes), encrypted
    ///         client-side. The contract adds it to the encrypted tally without ever
    ///         seeing the individual vote.
    function voteOnRequest(
        uint256 requestId,
        externalEuint8 encVote,
        bytes calldata inputProof
    ) external {
        Request storage r = requests[requestId];
        require(r.open, "closed");
        require(positionOf[r.tontineId][msg.sender] != 0, "not a member");
        require(!requestVoted[requestId][msg.sender], "already voted");
        requestVoted[requestId][msg.sender] = true;

        // Convert the external ciphertext to euint64 and add it to the encrypted
        // yes-tally. A "no" vote contributes 0, a "yes" vote contributes 1.
        euint64 v = FHE.asEuint64(FHE.fromExternal(encVote, inputProof));
        r.yesTally = FHE.add(r.yesTally, v);
        FHE.allowThis(r.yesTally);
        r.voterCount += 1;
        emit RequestVoted(requestId, msg.sender);
    }

    /// @notice Close the vote and expose ONLY the aggregate yes-count for public
    ///         decryption. Individual votes stay encrypted forever. Off-chain, the
    ///         request is granted if yesTally * 2 > voterCount (simple majority).
    function closeRequest(uint256 requestId) external {
        Request storage r = requests[requestId];
        require(r.open, "closed");
        require(msg.sender == cores[r.tontineId].admin, "not admin");
        r.open = false;
        FHE.makePubliclyDecryptable(r.yesTally);
        emit RequestClosed(requestId);
    }

    // --------------------------------------------------------------- views
    function getTontine(uint256 tontineId)
        external
        view
        returns (
            address admin,
            string memory name,
            uint64 amount,
            uint32 memberCount,
            uint32 currentCycle,
            bool started
        )
    {
        Core storage c = cores[tontineId];
        return (c.admin, c.name, c.amount, c.memberCount, c.currentCycle, c.started);
    }

    function getMember(uint256 tontineId, uint256 position)
        external
        view
        returns (address wallet, string memory name, bool active)
    {
        Member storage m = members[tontineId][position];
        return (m.wallet, m.name, m.active);
    }

    /// @notice True when the current cycle is fully validated (all paid + received).
    function isCycleValidated(uint256 tontineId) external view returns (bool) {
        Core storage c = cores[tontineId];
        if (!c.started || !receiptConfirmed[tontineId][c.currentCycle]) return false;
        for (uint256 p = 1; p <= c.memberCount; p++) {
            if (members[tontineId][p].active && !payerConfirmed[tontineId][c.currentCycle][p]) {
                return false;
            }
        }
        return true;
    }

    function getRequest(uint256 requestId)
        external
        view
        returns (uint256 tontineId, address requester, bool open, uint32 voterCount)
    {
        Request storage r = requests[requestId];
        return (r.tontineId, r.requester, r.open, r.voterCount);
    }

    /// @notice The encrypted yes-tally handle. After closeRequest it can be decrypted
    ///         off-chain by anyone to check whether the request passed.
    function getEncryptedYesTally(uint256 requestId) external view returns (euint64) {
        return requests[requestId].yesTally;
    }
}

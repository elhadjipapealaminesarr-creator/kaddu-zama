// SPDX-License-Identifier: BSD-3-Clause-Clear
pragma solidity ^0.8.24;

import {FHE, euint8, euint64, externalEuint8, ebool} from "@fhevm/solidity/lib/FHE.sol";
import {ZamaEthereumConfig} from "@fhevm/solidity/config/ZamaConfig.sol";

/// @title Kaddu — Confidential on-chain voting powered by Zama fhEVM
/// @notice Each ballot is submitted encrypted. The contract tallies votes on
///         encrypted data (FHE) and never learns any individual choice. Only the
///         final per-option totals are made publicly decryptable after the poll closes.
contract KadduVote is ZamaEthereumConfig {
    struct Poll {
        address admin;
        string title;
        string question;
        string[] options;
        bool closed;
        uint64 createdAt;
        uint32 voterCount;
        mapping(uint256 => euint64) tally;   // encrypted running total per option
        mapping(address => bool) hasVoted;   // one vote per address
    }

    uint256 public pollCount;
    mapping(uint256 => Poll) private polls;

    event PollCreated(uint256 indexed pollId, address indexed admin, string title);
    event Voted(uint256 indexed pollId, address indexed voter);
    event PollClosed(uint256 indexed pollId);

    /// @notice Create a poll with 2 to 8 options.
    function createPoll(
        string calldata title,
        string calldata question,
        string[] calldata options
    ) external returns (uint256 pollId) {
        require(options.length >= 2 && options.length <= 8, "2-8 options");
        pollId = pollCount++;
        Poll storage p = polls[pollId];
        p.admin = msg.sender;
        p.title = title;
        p.question = question;
        p.createdAt = uint64(block.timestamp);
        for (uint256 i = 0; i < options.length; i++) {
            p.options.push(options[i]);
            p.tally[i] = FHE.asEuint64(uint64(0));
            FHE.allowThis(p.tally[i]);
        }
        emit PollCreated(pollId, msg.sender, title);
    }

    /// @notice Cast an encrypted ballot. `encryptedChoice` is the option index,
    ///         encrypted client-side; the contract never sees it in clear.
    function vote(
        uint256 pollId,
        externalEuint8 encryptedChoice,
        bytes calldata inputProof
    ) external {
        Poll storage p = polls[pollId];
        require(p.admin != address(0), "no poll");
        require(!p.closed, "closed");
        require(!p.hasVoted[msg.sender], "already voted");
        p.hasVoted[msg.sender] = true;

        euint8 choice = FHE.fromExternal(encryptedChoice, inputProof);
        uint256 n = p.options.length;
        for (uint256 i = 0; i < n; i++) {
            // isI = 1 (encrypted) if the voter picked option i, else 0
            ebool isI = FHE.eq(choice, uint8(i));
            euint64 inc = FHE.asEuint64(isI);
            p.tally[i] = FHE.add(p.tally[i], inc);
            FHE.allowThis(p.tally[i]);
        }
        p.voterCount += 1;
        emit Voted(pollId, msg.sender);
    }

    /// @notice Close the poll (admin only) and expose the encrypted totals for
    ///         public decryption, so anyone can verify the result.
    function closePoll(uint256 pollId) external {
        Poll storage p = polls[pollId];
        require(msg.sender == p.admin, "not admin");
        require(!p.closed, "closed");
        p.closed = true;
        for (uint256 i = 0; i < p.options.length; i++) {
            FHE.makePubliclyDecryptable(p.tally[i]);
        }
        emit PollClosed(pollId);
    }

    function getPollMeta(uint256 pollId)
        external
        view
        returns (
            address admin,
            string memory title,
            string memory question,
            string[] memory options,
            bool closed,
            uint32 voterCount
        )
    {
        Poll storage p = polls[pollId];
        return (p.admin, p.title, p.question, p.options, p.closed, p.voterCount);
    }

    /// @notice Returns the encrypted total for an option (a ciphertext handle).
    ///         After closePoll it can be decrypted off-chain by anyone.
    function getEncryptedTally(uint256 pollId, uint256 optionIndex) external view returns (euint64) {
        return polls[pollId].tally[optionIndex];
    }
}

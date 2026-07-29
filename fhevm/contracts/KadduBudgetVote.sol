// SPDX-License-Identifier: BSD-3-Clause-Clear
pragma solidity ^0.8.24;

import {FHE, euint8, euint32, externalEuint8, ebool} from "@fhevm/solidity/lib/FHE.sol";
import {ZamaEthereumConfig} from "@fhevm/solidity/config/ZamaConfig.sol";

/// @title Kaddu — Budget fixé par vote communautaire (brick 3)
/// @notice Before a public tender opens, the *community* — not the official —
///         approves the budget ceiling. Members cast an ENCRYPTED yes/no vote on a
///         proposed ceiling; only the boolean "approved by the community"
///         (yesVotes >= quorum) is ever made public. Individual votes and the exact
///         tally stay secret, so no one can be pressured or retaliated against.
///
///  This is the oracle-free version: the approval boolean is exposed via
///  `makePubliclyDecryptable`, so anyone can verify the community's decision
///  off-chain. The organizer then uses the approved `proposedCeiling` as the
///  `reservePrice` of the matching `KadduTender` — and because the proposal,
///  its ceiling and its approval are all public and auditable, the official
///  cannot secretly inflate the budget.
///
///  (A future upgrade can bind the result on-chain via the fhEVM decryption
///  oracle / Gateway, so the tender contract mechanically refuses to open unless
///  the linked proposal was approved.)
contract KadduBudgetVote is ZamaEthereumConfig {
    struct Proposal {
        address organizer;
        string refCode;        // links to the tender (same procurement refCode)
        uint64 proposedCeiling;  // public candidate budget ceiling being voted on
        uint64 deadline;         // unix ts; no votes after
        uint32 quorum;           // yes-votes required to approve
        uint32 voterCount;
        uint32 ballots;          // how many members have voted (public turnout)
        bool revealed;

        euint32 encYes;          // encrypted count of yes votes
        ebool encApproved;       // encrypted "encYes >= quorum" (public after reveal)

        mapping(address => bool) isVoter;
        mapping(address => bool) hasVoted;
    }

    uint256 public proposalCount;
    mapping(uint256 => Proposal) private proposals;

    event ProposalCreated(uint256 indexed proposalId, address indexed organizer, string refCode, uint64 proposedCeiling);
    event Voted(uint256 indexed proposalId, address indexed voter);
    event ResultRevealed(uint256 indexed proposalId);

    /// @notice Propose a budget ceiling for community approval.
    /// @param refCode       Procurement refCode, shared with the KadduTender.
    /// @param proposedCeiling Public candidate ceiling being voted on.
    /// @param votingDuration  Seconds the vote stays open.
    /// @param voters          Community members allowed to vote.
    /// @param quorum          Yes-votes required for the ceiling to be approved.
    function createProposal(
        string calldata refCode,
        uint64 proposedCeiling,
        uint64 votingDuration,
        address[] calldata voters,
        uint32 quorum
    ) external returns (uint256 proposalId) {
        require(proposedCeiling > 0, "no ceiling");
        require(votingDuration > 0, "no duration");
        require(voters.length > 0, "no voters");
        require(quorum > 0 && quorum <= voters.length, "bad quorum");

        proposalId = proposalCount++;
        Proposal storage p = proposals[proposalId];
        p.organizer = msg.sender;
        p.refCode = refCode;
        p.proposedCeiling = proposedCeiling;
        p.deadline = uint64(block.timestamp) + votingDuration;
        p.quorum = quorum;

        for (uint256 i = 0; i < voters.length; i++) {
            address v = voters[i];
            require(v != address(0), "bad voter");
            if (!p.isVoter[v]) {
                p.isVoter[v] = true;
                p.voterCount += 1;
            }
        }

        p.encYes = FHE.asEuint32(uint32(0));
        FHE.allowThis(p.encYes);

        emit ProposalCreated(proposalId, msg.sender, refCode, proposedCeiling);
    }

    /// @notice Cast an encrypted vote. Send an encrypted `1` to approve the ceiling;
    ///         anything else counts as a rejection. One vote per member. The
    ///         individual choice is never revealed.
    function vote(
        uint256 proposalId,
        externalEuint8 encApprove,
        bytes calldata inputProof
    ) external {
        Proposal storage p = proposals[proposalId];
        require(p.organizer != address(0), "no proposal");
        require(block.timestamp < p.deadline, "voting over");
        require(p.isVoter[msg.sender], "not a voter");
        require(!p.hasVoted[msg.sender], "already voted");
        p.hasVoted[msg.sender] = true;
        p.ballots += 1;

        euint8 choice = FHE.fromExternal(encApprove, inputProof);
        // Normalise to 0/1: only an explicit encrypted 1 counts as a yes.
        ebool isYes = FHE.eq(choice, uint8(1));
        p.encYes = FHE.add(p.encYes, FHE.asEuint32(isYes));
        FHE.allowThis(p.encYes);

        emit Voted(proposalId, msg.sender);
    }

    /// @notice Reveal ONLY the boolean "the community approved this ceiling"
    ///         (yesVotes >= quorum). The exact tally stays secret. Callable after
    ///         the deadline, or by the organizer once quorum turnout is possible.
    function revealResult(uint256 proposalId) external {
        Proposal storage p = proposals[proposalId];
        require(p.organizer != address(0), "no proposal");
        require(!p.revealed, "already revealed");
        require(block.timestamp >= p.deadline, "voting open");
        p.revealed = true;

        ebool approved = FHE.ge(p.encYes, p.quorum);
        FHE.allowThis(approved);
        FHE.makePubliclyDecryptable(approved);
        p.encApproved = approved;

        emit ResultRevealed(proposalId);
    }

    // ---------------------------------------------------------------------
    // Views
    // ---------------------------------------------------------------------

    function getProposalMeta(uint256 proposalId)
        external
        view
        returns (
            address organizer,
            string memory refCode,
            uint64 proposedCeiling,
            uint64 deadline,
            uint32 quorum,
            uint32 voterCount,
            uint32 ballots,
            bool revealed
        )
    {
        Proposal storage p = proposals[proposalId];
        return (
            p.organizer,
            p.refCode,
            p.proposedCeiling,
            p.deadline,
            p.quorum,
            p.voterCount,
            p.ballots,
            p.revealed
        );
    }

    /// @notice Encrypted approval flag. Publicly decryptable after `revealResult`.
    function getApproved(uint256 proposalId) external view returns (ebool) {
        return proposals[proposalId].encApproved;
    }

    function isVoter(uint256 proposalId, address who) external view returns (bool) {
        return proposals[proposalId].isVoter[who];
    }
}

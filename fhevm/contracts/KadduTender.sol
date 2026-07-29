// SPDX-License-Identifier: BSD-3-Clause-Clear
pragma solidity ^0.8.24;

import {FHE, euint8, euint32, euint64, externalEuint8, externalEuint64, ebool} from "@fhevm/solidity/lib/FHE.sol";
import {ZamaEthereumConfig} from "@fhevm/solidity/config/ZamaConfig.sol";
import {IConfidentialFungibleToken} from "./IConfidentialFungibleToken.sol";

/// @title Kaddu — L'appel d'offres public inviolable (confidential public tender)
/// @notice A tamper-proof public-procurement rail on Zama fhEVM.
///
///  What makes it unique (vs Zama's Confidential RFQ, which is finance-only):
///   1. SEALED BIDS — each supplier submits an *encrypted* price. The contract
///      computes the winner (lowest eligible bid) *on encrypted data*. Losing
///      prices are NEVER revealed, so no one can price-signal or collude later.
///   2. THE WINNER IS COMPUTED, NEVER CHOSEN — the organizer has zero discretion.
///      It is mathematically impossible for them to hand-pick a favourite.
///   3. THE PEOPLE RELEASE THE PAYMENT — the price is held in confidential-token
///      (ERC-7984) escrow and is only claimable once N independent community
///      validators confirm the work was delivered. The treasurer can neither
///      block, divert, nor pay for undelivered work.
///   4. THE DEPOSIT SELF-SLASHES — each bidder locks an encrypted caution. If the
///      winner is chosen but the community never confirms delivery within the
///      window, the winner's caution is forfeited to the organizer. Honest losers
///      always get their caution back. Non-performance is punished automatically.
///   5. THRESHOLD COLLUSION TRIPWIRE — bidders can flag pressure/collusion with an
///      encrypted bit. The signal only becomes public if ENOUGH bidders flag
///      independently: only the boolean "count >= threshold" is ever revealed, so
///      a lone whistleblower is never exposed, but real collusion becomes visible.
///
///  Confidentiality model:
///   - Every bid amount and every caution is encrypted end-to-end.
///   - Only the running minimum (the eventual winning price) and the winner's
///     index are ever made publicly decryptable — for public-procurement
///     transparency. Every losing bid stays secret forever.
///   - The winner claims payment by proving, homomorphically, that they are the
///     winner (`FHE.eq`). A non-winner who tries to claim receives an encrypted
///     zero and moves nothing. No decryption oracle is needed to pay out.
///
///  Scope: bricks 1 (escrow + community-threshold release), 2 (confidential
///  self-slashing caution) and 5 (threshold collusion tripwire) from the design
///  note. The community-set budget vote (brick 3) layers on later — it needs the
///  fhEVM decryption oracle to bind an encrypted vote result on-chain.
contract KadduTender is ZamaEthereumConfig {
    /// @dev Sentinel meaning "no eligible bid yet".
    uint32 private constant NO_WINNER = type(uint32).max;

    enum Phase {
        Open,       // accepting sealed bids
        Evaluated,  // bidding closed, winner computed & publicly decryptable
        Closed      // remainder refunded / archived
    }

    struct Tender {
        address organizer;                 // the public buyer running the tender
        string title;
        string refCode;                  // official procurement refCode
        IConfidentialFungibleToken token;  // ERC-7984 confidential settlement token
        uint64 reservePrice;               // public ceiling; bids must be strictly below to win
        uint64 biddingDeadline;            // unix ts; no bids accepted after
        uint64 deliveryWindow;             // seconds after close for the community to confirm
        uint64 deliveryDeadline;           // set at closeBidding = now + deliveryWindow
        Phase phase;
        uint32 validatorCount;
        uint32 threshold;                  // confirmations required to release payment
        uint32 confirmations;              // community delivery confirmations so far
        uint32 collusionThreshold;         // independent flags required to trip the tripwire
        bool cautionSlashed;               // winner caution already forfeited to organizer
        bool collusionRevealed;            // collusion signal already computed & exposed

        address[] bidders;                 // public list of who bid (amounts stay secret)
        euint64 encMinPrice;               // encrypted running minimum (winning price)
        euint32 encWinnerIndex;            // encrypted index of the current best bidder
        euint64 encWinnerCaution;          // encrypted caution of the current best bidder
        euint64 encBudget;                 // encrypted total payment budget funded by organizer
        euint32 encFlagCount;              // encrypted number of independent collusion flags
        ebool encCollusionTripped;         // encrypted "flagCount >= collusionThreshold"

        mapping(address => bool) hasBid;
        mapping(address => bool) hasClaimed;          // payment claimed
        mapping(address => bool) hasReclaimedCaution; // caution reclaimed
        mapping(address => euint64) caution;          // encrypted caution locked per bidder
        mapping(address => bool) isValidator;
        mapping(address => bool) hasConfirmed;
        mapping(address => bool) hasFlagged;          // collusion flag cast (one per bidder)
    }

    uint256 public tenderCount;
    mapping(uint256 => Tender) private tenders;

    event TenderCreated(uint256 indexed tenderId, address indexed organizer, string title);
    event EscrowFunded(uint256 indexed tenderId);
    event BidSubmitted(uint256 indexed tenderId, address indexed bidder, uint256 index);
    event BiddingClosed(uint256 indexed tenderId, uint256 bidderCount, uint64 deliveryDeadline);
    event DeliveryConfirmed(uint256 indexed tenderId, address indexed validator, uint32 confirmations);
    event PaymentClaimed(uint256 indexed tenderId, address indexed claimant);
    event CautionReclaimed(uint256 indexed tenderId, address indexed bidder);
    event CautionSlashed(uint256 indexed tenderId);
    event RemainderRefunded(uint256 indexed tenderId);
    event CollusionFlagged(uint256 indexed tenderId, address indexed bidder);
    event CollusionRevealed(uint256 indexed tenderId);

    // ---------------------------------------------------------------------
    // 1. Creation
    // ---------------------------------------------------------------------

    /// @notice Open a confidential tender.
    /// @param token          ERC-7984 confidential token used for payment & caution (e.g. cUSDC).
    /// @param reservePrice   Public ceiling. Only bids strictly below it can win.
    /// @param biddingDuration Seconds the tender accepts bids for.
    /// @param deliveryWindow Seconds after close for the community to confirm before slashing.
    /// @param validators     Community members allowed to confirm delivery.
    /// @param threshold      How many of them must confirm before payment unlocks.
    /// @param collusionThreshold How many bidders must flag independently to trip the collusion signal.
    function createTender(
        string calldata title,
        string calldata refCode,
        IConfidentialFungibleToken token,
        uint64 reservePrice,
        uint64 biddingDuration,
        uint64 deliveryWindow,
        address[] calldata validators,
        uint32 threshold,
        uint32 collusionThreshold
    ) external returns (uint256 tenderId) {
        require(address(token) != address(0), "no token");
        require(reservePrice > 0, "no reserve");
        require(biddingDuration > 0, "no duration");
        require(deliveryWindow > 0, "no delivery window");
        require(validators.length > 0, "no validators");
        require(threshold > 0 && threshold <= validators.length, "bad threshold");
        require(collusionThreshold > 0, "bad collusion threshold");

        tenderId = tenderCount++;
        Tender storage t = tenders[tenderId];
        t.organizer = msg.sender;
        t.title = title;
        t.refCode = refCode;
        t.token = token;
        t.reservePrice = reservePrice;
        t.biddingDeadline = uint64(block.timestamp) + biddingDuration;
        t.deliveryWindow = deliveryWindow;
        t.phase = Phase.Open;
        t.threshold = threshold;
        t.collusionThreshold = collusionThreshold;

        for (uint256 i = 0; i < validators.length; i++) {
            address v = validators[i];
            require(v != address(0), "bad validator");
            if (!t.isValidator[v]) {
                t.isValidator[v] = true;
                t.validatorCount += 1;
            }
        }

        // Running minimum starts at the reserve: any real bid below it becomes the
        // new minimum. Winner starts at the sentinel; caution & budget at zero.
        t.encMinPrice = FHE.asEuint64(reservePrice);
        t.encWinnerIndex = FHE.asEuint32(NO_WINNER);
        t.encWinnerCaution = FHE.asEuint64(uint64(0));
        t.encBudget = FHE.asEuint64(uint64(0));
        t.encFlagCount = FHE.asEuint32(uint32(0));
        FHE.allowThis(t.encMinPrice);
        FHE.allowThis(t.encWinnerIndex);
        FHE.allowThis(t.encWinnerCaution);
        FHE.allowThis(t.encBudget);
        FHE.allowThis(t.encFlagCount);

        emit TenderCreated(tenderId, msg.sender, title);
    }

    // ---------------------------------------------------------------------
    // 2. Escrow funding (organizer deposits the payment budget in cToken)
    // ---------------------------------------------------------------------

    /// @notice Organizer funds the payment escrow with confidential tokens.
    /// @dev    The organizer must have called `token.setOperator(thisContract, until)`
    ///         beforehand. Fund at least `reservePrice` so the winner can be paid.
    function fundEscrow(
        uint256 tenderId,
        externalEuint64 encAmount,
        bytes calldata inputProof
    ) external {
        Tender storage t = tenders[tenderId];
        require(msg.sender == t.organizer, "not organizer");
        require(t.phase == Phase.Open, "not open");

        // Track the actually-received amount so refunds are exact (budget and
        // cautions share the same token balance — never sweep the whole balance).
        euint64 got = t.token.confidentialTransferFrom(msg.sender, address(this), encAmount, inputProof);
        t.encBudget = FHE.add(t.encBudget, got);
        FHE.allowThis(t.encBudget);

        emit EscrowFunded(tenderId);
    }

    // ---------------------------------------------------------------------
    // 3. Sealed bidding (encrypted price + encrypted caution)
    // ---------------------------------------------------------------------

    /// @notice Submit an encrypted bid price together with an encrypted caution
    ///         deposit. Sealed: the contract never sees either in clear.
    /// @dev    The bidder must have called `token.setOperator(thisContract, until)`
    ///         so the caution can be pulled into escrow.
    function submitBid(
        uint256 tenderId,
        externalEuint64 encPrice,
        bytes calldata priceProof,
        externalEuint64 encCaution,
        bytes calldata cautionProof
    ) external {
        Tender storage t = tenders[tenderId];
        require(t.organizer != address(0), "no tender");
        require(t.phase == Phase.Open, "not open");
        require(block.timestamp < t.biddingDeadline, "bidding over");
        require(msg.sender != t.organizer, "organizer cannot bid");
        require(!t.hasBid[msg.sender], "already bid");

        uint32 index = uint32(t.bidders.length);
        t.hasBid[msg.sender] = true;
        t.bidders.push(msg.sender);

        // Pull the caution into escrow and record the actual amount locked.
        euint64 lockedCaution =
            t.token.confidentialTransferFrom(msg.sender, address(this), encCaution, cautionProof);
        t.caution[msg.sender] = lockedCaution;
        FHE.allowThis(t.caution[msg.sender]);

        euint64 price = FHE.fromExternal(encPrice, priceProof);

        // isLower = 1 (encrypted) iff this bid is strictly below the current min.
        // Because the min starts at the reserve, a bid >= reserve can never win.
        ebool isLower = FHE.lt(price, t.encMinPrice);
        t.encMinPrice = FHE.select(isLower, price, t.encMinPrice);
        t.encWinnerIndex = FHE.select(isLower, FHE.asEuint32(index), t.encWinnerIndex);
        t.encWinnerCaution = FHE.select(isLower, lockedCaution, t.encWinnerCaution);

        FHE.allowThis(t.encMinPrice);
        FHE.allowThis(t.encWinnerIndex);
        FHE.allowThis(t.encWinnerCaution);

        emit BidSubmitted(tenderId, msg.sender, index);
    }

    // ---------------------------------------------------------------------
    // 4. Close bidding & expose the (winner, winning price) for verification
    // ---------------------------------------------------------------------

    /// @notice Close bidding, start the delivery window, and make the winner index
    ///         and winning price publicly decryptable so anyone can verify the
    ///         outcome. Losing bids stay secret. Callable by the organizer, or by
    ///         anyone after the bidding deadline.
    function closeBidding(uint256 tenderId) external {
        Tender storage t = tenders[tenderId];
        require(t.phase == Phase.Open, "not open");
        require(
            msg.sender == t.organizer || block.timestamp >= t.biddingDeadline,
            "too early"
        );
        t.phase = Phase.Evaluated;
        t.deliveryDeadline = uint64(block.timestamp) + t.deliveryWindow;

        // Public verifiability: anyone can decrypt WHO won and at WHAT price.
        FHE.makePubliclyDecryptable(t.encWinnerIndex);
        FHE.makePubliclyDecryptable(t.encMinPrice);

        emit BiddingClosed(tenderId, t.bidders.length, t.deliveryDeadline);
    }

    // ---------------------------------------------------------------------
    // 5. Community delivery confirmation (the threshold gate)
    // ---------------------------------------------------------------------

    /// @notice A community validator independently confirms the work was delivered.
    ///         Payment only unlocks once `threshold` validators have confirmed.
    function confirmDelivery(uint256 tenderId) external {
        Tender storage t = tenders[tenderId];
        require(t.phase == Phase.Evaluated, "not evaluated");
        require(t.isValidator[msg.sender], "not a validator");
        require(!t.hasConfirmed[msg.sender], "already confirmed");
        t.hasConfirmed[msg.sender] = true;
        t.confirmations += 1;
        emit DeliveryConfirmed(tenderId, msg.sender, t.confirmations);
    }

    // ---------------------------------------------------------------------
    // 6. Payment claim (only the winner gets paid — and only after the gate)
    // ---------------------------------------------------------------------

    /// @notice A bidder claims payment. The contract pays the encrypted winning
    ///         price to the *real* winner and an encrypted zero to everyone else —
    ///         no decryption needed. Gated on the community threshold.
    function claimPayment(uint256 tenderId) external {
        Tender storage t = tenders[tenderId];
        require(t.phase == Phase.Evaluated, "not evaluated");
        require(t.confirmations >= t.threshold, "not released by community");
        require(t.hasBid[msg.sender], "not a bidder");
        require(!t.hasClaimed[msg.sender], "already claimed");
        t.hasClaimed[msg.sender] = true;

        uint32 index = _indexOf(t, msg.sender);

        // isWinner is true (encrypted) only for the computed winner.
        ebool isWinner = FHE.eq(t.encWinnerIndex, index);
        // Winner gets encMinPrice; everyone else gets an encrypted zero.
        euint64 payout = FHE.select(isWinner, t.encMinPrice, FHE.asEuint64(uint64(0)));

        FHE.allowTransient(payout, address(t.token));
        t.token.confidentialTransfer(msg.sender, payout);

        emit PaymentClaimed(tenderId, msg.sender);
    }

    // ---------------------------------------------------------------------
    // 7. Caution reclaim & self-slashing
    // ---------------------------------------------------------------------

    /// @notice Reclaim your caution. Honest losers always get it back. The winner
    ///         gets it back only if the community confirmed delivery; otherwise,
    ///         once the delivery window has elapsed, the winner's caution is
    ///         withheld (an encrypted zero is returned) and can be slashed to the
    ///         organizer via `slashWinnerCaution`.
    function reclaimCaution(uint256 tenderId) external {
        Tender storage t = tenders[tenderId];
        require(t.phase == Phase.Evaluated || t.phase == Phase.Closed, "not evaluated");
        require(t.hasBid[msg.sender], "not a bidder");
        require(!t.hasReclaimedCaution[msg.sender], "already reclaimed");

        bool delivered = t.confirmations >= t.threshold;
        require(delivered || block.timestamp >= t.deliveryDeadline, "delivery window open");
        t.hasReclaimedCaution[msg.sender] = true;

        euint64 refund;
        if (delivered) {
            // Everyone (winner included) gets their caution back.
            refund = t.caution[msg.sender];
        } else {
            // Non-delivery after the window: the winner is withheld (0), losers keep theirs.
            uint32 index = _indexOf(t, msg.sender);
            ebool isWinner = FHE.eq(t.encWinnerIndex, index);
            refund = FHE.select(isWinner, FHE.asEuint64(uint64(0)), t.caution[msg.sender]);
        }

        FHE.allowTransient(refund, address(t.token));
        t.token.confidentialTransfer(msg.sender, refund);

        emit CautionReclaimed(tenderId, msg.sender);
    }

    /// @notice If the winner failed to deliver (community did not reach threshold
    ///         before the delivery deadline), the organizer claims the forfeited
    ///         winner caution. The amount is the encrypted caution of the computed
    ///         winner — no one learns which loser paid what.
    function slashWinnerCaution(uint256 tenderId) external {
        Tender storage t = tenders[tenderId];
        require(msg.sender == t.organizer, "not organizer");
        require(t.phase == Phase.Evaluated, "not evaluated");
        require(t.confirmations < t.threshold, "delivery confirmed");
        require(block.timestamp >= t.deliveryDeadline, "delivery window open");
        require(!t.cautionSlashed, "already slashed");
        t.cautionSlashed = true;

        euint64 amount = t.encWinnerCaution;
        FHE.allowTransient(amount, address(t.token));
        t.token.confidentialTransfer(t.organizer, amount);

        emit CautionSlashed(tenderId);
    }

    // ---------------------------------------------------------------------
    // 8. Refund the organizer's unspent budget
    // ---------------------------------------------------------------------

    /// @notice Return the organizer's unspent payment budget.
    ///  - If delivered: budget minus the winning price (the winner keeps the price).
    ///  - If not delivered after the window: the full budget (nothing was paid).
    /// Marks the tender Closed. Cautions are handled separately and are never swept.
    function refundBudget(uint256 tenderId) external {
        Tender storage t = tenders[tenderId];
        require(msg.sender == t.organizer, "not organizer");
        require(t.phase == Phase.Evaluated, "not evaluated");

        bool delivered = t.confirmations >= t.threshold;
        require(delivered || block.timestamp >= t.deliveryDeadline, "delivery window open");
        t.phase = Phase.Closed;

        // If delivered, the winning price is owed to the winner, so refund the rest.
        // (Requires budget >= reservePrice >= winning price, which the organizer funds.)
        euint64 refund = delivered ? FHE.sub(t.encBudget, t.encMinPrice) : t.encBudget;

        FHE.allowTransient(refund, address(t.token));
        t.token.confidentialTransfer(t.organizer, refund);

        emit RemainderRefunded(tenderId);
    }

    // ---------------------------------------------------------------------
    // 9. Threshold collusion tripwire
    // ---------------------------------------------------------------------

    /// @notice A bidder confidentially flags collusion/pressure. Send an encrypted
    ///         `1` to flag, anything else counts as no flag. Only bidders can flag,
    ///         once each. The individual flag is never revealed.
    function flagCollusion(
        uint256 tenderId,
        externalEuint8 encFlag,
        bytes calldata inputProof
    ) external {
        Tender storage t = tenders[tenderId];
        require(t.phase == Phase.Open || t.phase == Phase.Evaluated, "closed");
        require(t.hasBid[msg.sender], "not a bidder");
        require(!t.hasFlagged[msg.sender], "already flagged");
        require(!t.collusionRevealed, "already revealed");
        t.hasFlagged[msg.sender] = true;

        euint8 flag = FHE.fromExternal(encFlag, inputProof);
        // Normalise to 0/1 so no single bidder can inflate the count.
        ebool isFlag = FHE.eq(flag, uint8(1));
        t.encFlagCount = FHE.add(t.encFlagCount, FHE.asEuint32(isFlag));
        FHE.allowThis(t.encFlagCount);

        emit CollusionFlagged(tenderId, msg.sender);
    }

    /// @notice Compute and expose ONLY the boolean "enough bidders flagged"
    ///         (`flagCount >= collusionThreshold`). Below the threshold the result
    ///         is simply `false`, indistinguishable from zero flags — so a lone
    ///         whistleblower is never exposed. Callable after bidding closes.
    function revealCollusion(uint256 tenderId) external {
        Tender storage t = tenders[tenderId];
        require(t.phase == Phase.Evaluated || t.phase == Phase.Closed, "not evaluated");
        require(!t.collusionRevealed, "already revealed");
        t.collusionRevealed = true;

        ebool tripped = FHE.ge(t.encFlagCount, t.collusionThreshold);
        FHE.allowThis(tripped);
        FHE.makePubliclyDecryptable(tripped);
        t.encCollusionTripped = tripped;

        emit CollusionRevealed(tenderId);
    }

    // ---------------------------------------------------------------------
    // Views
    // ---------------------------------------------------------------------

    function getTenderMeta(uint256 tenderId)
        external
        view
        returns (
            address organizer,
            string memory title,
            string memory refCode,
            address token,
            uint64 reservePrice,
            uint64 biddingDeadline,
            uint64 deliveryDeadline,
            Phase phase,
            uint32 validatorCount,
            uint32 threshold,
            uint32 confirmations,
            uint256 bidderCount
        )
    {
        Tender storage t = tenders[tenderId];
        return (
            t.organizer,
            t.title,
            t.refCode,
            address(t.token),
            t.reservePrice,
            t.biddingDeadline,
            t.deliveryDeadline,
            t.phase,
            t.validatorCount,
            t.threshold,
            t.confirmations,
            t.bidders.length
        );
    }

    function getBidders(uint256 tenderId) external view returns (address[] memory) {
        return tenders[tenderId].bidders;
    }

    /// @notice Encrypted winner index. Publicly decryptable after `closeBidding`.
    function getEncryptedWinnerIndex(uint256 tenderId) external view returns (euint32) {
        return tenders[tenderId].encWinnerIndex;
    }

    /// @notice Encrypted winning price. Publicly decryptable after `closeBidding`.
    function getEncryptedWinningPrice(uint256 tenderId) external view returns (euint64) {
        return tenders[tenderId].encMinPrice;
    }

    function isValidator(uint256 tenderId, address who) external view returns (bool) {
        return tenders[tenderId].isValidator[who];
    }

    /// @notice Encrypted collusion signal ("enough bidders flagged"). Publicly
    ///         decryptable after `revealCollusion`. The raw flag count is never exposed.
    function getCollusionTripped(uint256 tenderId) external view returns (ebool) {
        return tenders[tenderId].encCollusionTripped;
    }

    // ---------------------------------------------------------------------
    // Internal
    // ---------------------------------------------------------------------

    function _indexOf(Tender storage t, address who) private view returns (uint32) {
        uint256 n = t.bidders.length;
        for (uint256 i = 0; i < n; i++) {
            if (t.bidders[i] == who) return uint32(i);
        }
        revert("not a bidder");
    }
}

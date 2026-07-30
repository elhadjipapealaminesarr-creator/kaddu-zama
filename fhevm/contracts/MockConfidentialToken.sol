// SPDX-License-Identifier: BSD-3-Clause-Clear
pragma solidity ^0.8.24;

import {FHE, euint64, externalEuint64, ebool} from "@fhevm/solidity/lib/FHE.sol";
import {ZamaEthereumConfig} from "@fhevm/solidity/config/ZamaConfig.sol";
import {IConfidentialFungibleToken} from "./IConfidentialFungibleToken.sol";

/// @title MockConfidentialToken — TEST-ONLY confidential fungible token (ERC-7984-like)
/// @notice Minimal confidential token used ONLY by the Hardhat test suite to
///         exercise KadduTender's escrow flow (deposits, caution, payout).
///         Balances and transfer amounts are FHE ciphertexts (euint64).
/// @dev    NOT audited, NOT for production. It intentionally keeps the surface
///         tiny and permissive so tests can move funds around the escrow.
contract MockConfidentialToken is IConfidentialFungibleToken, ZamaEthereumConfig {
    mapping(address => euint64) private _bal;
    // holder => operator => expiry timestamp (uint48)
    mapping(address => mapping(address => uint48)) private _op;

    /// @notice TEST HELPER: mint an encrypted `amount` to `to`.
    function mint(address to, externalEuint64 encAmount, bytes calldata inputProof) external {
        euint64 amt = FHE.fromExternal(encAmount, inputProof);
        _credit(to, amt);
    }

    function confidentialBalanceOf(address account) external view returns (euint64) {
        return _bal[account];
    }

    function setOperator(address operator, uint48 until) external {
        _op[msg.sender][operator] = until;
    }

    function isOperator(address holder, address operator) public view returns (bool) {
        return _op[holder][operator] >= uint48(block.timestamp);
    }

    /// @notice Operator-pull transfer (used by the escrow contract).
    function confidentialTransferFrom(
        address from,
        address to,
        externalEuint64 amount,
        bytes calldata inputProof
    ) external returns (euint64 transferred) {
        require(from == msg.sender || isOperator(from, msg.sender), "not operator");
        euint64 amt = FHE.fromExternal(amount, inputProof);
        transferred = _move(from, to, amt);
    }

    /// @notice Send an already-encrypted `amount` held by the caller to `to`.
    function confidentialTransfer(address to, euint64 amount) external returns (euint64 transferred) {
        transferred = _move(msg.sender, to, amount);
    }

    // ---------------------------------------------------------------------
    // internals
    // ---------------------------------------------------------------------

    /// @dev Current balance, lazily initialised to an encrypted 0.
    function _current(address a) internal returns (euint64 cur) {
        euint64 stored = _bal[a];
        cur = (euint64.unwrap(stored) == bytes32(0)) ? FHE.asEuint64(0) : stored;
    }

    function _credit(address a, euint64 amt) internal {
        euint64 nb = FHE.add(_current(a), amt);
        _bal[a] = nb;
        FHE.allowThis(nb);
        FHE.allow(nb, a);
    }

    /// @dev Move `amt` from → to, clamped to the sender's balance. Returns the
    ///      amount actually moved (encrypted).
    function _move(address from, address to, euint64 amt) internal returns (euint64 sent) {
        euint64 fromBal = _current(from);
        ebool ok = FHE.le(amt, fromBal);
        sent = FHE.select(ok, amt, fromBal); // never move more than the balance

        euint64 nf = FHE.sub(fromBal, sent);
        euint64 nt = FHE.add(_current(to), sent);
        _bal[from] = nf;
        _bal[to] = nt;

        FHE.allowThis(nf);
        FHE.allow(nf, from);
        FHE.allowThis(nt);
        FHE.allow(nt, to);
        FHE.allowThis(sent);
        // let the caller (escrow) read the moved amount it received
        FHE.allow(sent, msg.sender);
    }
}
